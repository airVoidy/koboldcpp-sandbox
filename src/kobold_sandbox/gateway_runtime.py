"""
Gateway Queue Runtime for Workflow v3.

Job-based reactive execution: jobs → per-worker queues → events → handlers → chaining.
Workers always busy. Runtime fills gaps with assembly transforms.
"""
from __future__ import annotations

import logging
import threading
import time
import uuid
from collections import deque
from concurrent.futures import Future, ThreadPoolExecutor
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Callable, Literal

import httpx
import yaml

from .assembly_dsl import execute as asm_execute
from .workflow_dsl import WorkflowContext

log = logging.getLogger(__name__)


# ── Data types ────────────────────────────────────────────

class JobStatus(str, Enum):
    PENDING = "pending"
    ACTIVE = "active"
    DONE = "done"
    FAILED = "failed"
    CANCELLED = "cancelled"


@dataclass
class GatewayJob:
    id: str
    worker: str
    payload: Any
    priority: Literal["high", "normal", "low"] = "normal"
    timeout: float = 120.0
    retry: int = 0
    status: JobStatus = JobStatus.PENDING
    result: Any = None
    error: str | None = None
    started_at: float | None = None
    finished_at: float | None = None
    # LLM params
    messages: list[dict] | None = None
    mode: str = "prompt"
    temp: float = 0.6
    max_tokens: int = 2048
    grammar: str | None = None
    capture: Any = None
    coerce: str | None = None
    no_think: bool = False
    tags: list[str] = field(default_factory=list)
    # for_each context
    context: dict[str, Any] = field(default_factory=dict)
    _retries_left: int = 0

    def __post_init__(self):
        self._retries_left = self.retry


@dataclass
class Subscription:
    event: str  # "job_id.done", "job_id.failed", "all_done"
    handler_asm: str  # assembly code to run
    then: list[dict] = field(default_factory=list)  # chaining actions
    wait_for: list[str] = field(default_factory=list)  # for all_done
    context: dict[str, Any] = field(default_factory=dict)


@dataclass
class GatewayEvent:
    job_id: str
    event_type: str  # "done" | "failed" | "timeout" | "cancelled"
    result: Any = None
    error: str | None = None
    timestamp: float = 0.0

    def __post_init__(self):
        if not self.timestamp:
            self.timestamp = time.time()


# ── Gateway Runtime ───────────────────────────────────────

class GatewayRuntime:
    """Job queue + reactive event dispatch for workflow v3."""

    def __init__(
        self,
        workers: dict[str, str],  # role → base_url
        settings: dict[str, Any] | None = None,
        on_event: Callable[[GatewayEvent], None] | None = None,
        on_thread: Callable | None = None,
    ):
        self.workers = workers
        self.settings = settings or {}
        self.on_event_cb = on_event or (lambda e: None)
        self.on_thread = on_thread or (lambda *a, **kw: None)

        # Job registry
        self._jobs: dict[str, GatewayJob] = {}
        self._jobs_lock = threading.Lock()

        # Per-worker queues (priority sorted)
        self._queues: dict[str, deque[str]] = {}  # worker → deque of job_ids
        self._queue_lock = threading.Lock()

        # Subscriptions
        self._subs: dict[str, list[Subscription]] = {}  # event → handlers
        self._all_done_subs: list[Subscription] = []  # wait for multiple

        # Job templates (from YAML)
        self._templates: dict[str, dict] = {}

        # Payload functions (claims, table, etc.)
        from .workflow_dsl import build_default_builtins
        self._payload_fns = build_default_builtins()

        # Shared state for assembly handlers
        self.state: dict[str, Any] = {}

        # Event log
        self.events: list[GatewayEvent] = []

        # HTTP + threading
        self._http = httpx.Client(timeout=180.0, trust_env=False)
        self._executor = ThreadPoolExecutor(max_workers=8)
        self._endpoint_locks: dict[str, threading.Lock] = {}
        self._lock_mu = threading.Lock()

        # Dispatch threads (one per worker)
        self._dispatch_threads: dict[str, threading.Thread] = {}
        self._running = True

        # WorkflowContext for assembly execution
        self._wf_ctx = WorkflowContext(
            workers=workers,
            settings=settings or {},
            on_thread=on_thread or (lambda *a, **kw: None),
        )

    # ── Public API ────────────────────────────────────────

    def enqueue(self, job: GatewayJob) -> str:
        """Add job to worker queue. Returns job_id."""
        with self._jobs_lock:
            self._jobs[job.id] = job

        worker = job.worker
        with self._queue_lock:
            if worker not in self._queues:
                self._queues[worker] = deque()
            q = self._queues[worker]
            # Priority insert: high → front, low → back, normal → after high
            if job.priority == "high":
                q.appendleft(job.id)
            else:
                q.append(job.id)

        # Start dispatch thread for this worker if not running
        self._ensure_dispatch_thread(worker)

        log.info("enqueued job %s → %s (priority=%s)", job.id, worker, job.priority)
        self.on_thread("system", "gateway", f"enqueued: {job.id} → {worker}", {"job_id": job.id})
        return job.id

    def subscribe(self, sub: Subscription):
        """Register event subscription."""
        if sub.wait_for:
            self._all_done_subs.append(sub)
        else:
            self._subs.setdefault(sub.event, []).append(sub)

    def cancel(self, job_id: str) -> bool:
        """Cancel a pending job."""
        with self._jobs_lock:
            job = self._jobs.get(job_id)
            if not job or job.status != JobStatus.PENDING:
                return False
            job.status = JobStatus.CANCELLED
        self._fire_event(GatewayEvent(job_id=job_id, event_type="cancelled"))
        return True

    def get_job(self, job_id: str) -> GatewayJob | None:
        return self._jobs.get(job_id)

    def get_status(self) -> dict:
        """Snapshot of runtime state for API."""
        queues = {}
        for worker, q in self._queues.items():
            queues[worker] = [
                {"id": jid, "status": self._jobs[jid].status.value, "priority": self._jobs[jid].priority}
                for jid in q if jid in self._jobs
            ]
        jobs = {
            jid: {
                "id": j.id, "worker": j.worker, "status": j.status.value,
                "priority": j.priority, "started_at": j.started_at,
                "finished_at": j.finished_at, "error": j.error,
                "result": j.result,
            }
            for jid, j in self._jobs.items()
        }
        return {
            "queues": queues,
            "jobs": jobs,
            "events": [{"job_id": e.job_id, "type": e.event_type, "ts": e.timestamp} for e in self.events[-50:]],
            "state": {k: v for k, v in self.state.items()},
        }

    def shutdown(self):
        """Stop all dispatch threads."""
        self._running = False
        self._executor.shutdown(wait=False)
        self._http.close()
        self._wf_ctx.close()

    # ── Worker Dispatch ───────────────────────────────────

    def _ensure_dispatch_thread(self, worker: str):
        if worker in self._dispatch_threads and self._dispatch_threads[worker].is_alive():
            return
        t = threading.Thread(target=self._dispatch_loop, args=(worker,), daemon=True)
        self._dispatch_threads[worker] = t
        t.start()

    def _get_endpoint_lock(self, url: str) -> threading.Lock:
        with self._lock_mu:
            if url not in self._endpoint_locks:
                self._endpoint_locks[url] = threading.Lock()
            return self._endpoint_locks[url]

    def _dispatch_loop(self, worker: str):
        """Per-worker dispatch loop: pop job, execute, fire event."""
        base_url = self.workers.get(worker, "").rstrip("/")
        if not base_url:
            log.error("no URL for worker %s", worker)
            return

        lock = self._get_endpoint_lock(base_url)

        while self._running:
            # Pop next job
            job_id = None
            with self._queue_lock:
                q = self._queues.get(worker, deque())
                while q:
                    candidate = q.popleft()
                    job = self._jobs.get(candidate)
                    if job and job.status == JobStatus.PENDING:
                        job_id = candidate
                        break

            if not job_id:
                time.sleep(0.1)
                continue

            job = self._jobs[job_id]
            job.status = JobStatus.ACTIVE
            job.started_at = time.time()
            self.on_thread("system", "gateway", f"active: {job.id}", {"job_id": job.id})

            try:
                with lock:
                    result = self._execute_job(job)
                job.result = result
                job.status = JobStatus.DONE
                job.finished_at = time.time()
                # Store result in shared state
                self.state[job.id] = result
                self._wf_ctx.vars[job.id] = result
                self._fire_event(GatewayEvent(job_id=job.id, event_type="done", result=result))

            except Exception as exc:
                job.error = str(exc)
                job.finished_at = time.time()
                if job._retries_left > 0:
                    job._retries_left -= 1
                    job.status = JobStatus.PENDING
                    with self._queue_lock:
                        self._queues[worker].appendleft(job.id)
                    log.warning("retrying job %s (%d left): %s", job.id, job._retries_left, exc)
                else:
                    job.status = JobStatus.FAILED
                    self._fire_event(GatewayEvent(job_id=job.id, event_type="failed", error=str(exc)))

    def _execute_job(self, job: GatewayJob) -> Any:
        """Execute a single job via LLM call."""
        # Build messages
        if job.messages:
            messages = []
            for m in job.messages:
                role = list(m.keys())[0] if isinstance(m, dict) and "role" not in m else m.get("role", "user")
                content = list(m.values())[0] if isinstance(m, dict) and "content" not in m else m.get("content", "")
                # Interpolate variables from state
                if isinstance(content, str):
                    for k, v in self.state.items():
                        content = content.replace(f"${{{k}}}", str(v) if v is not None else "")
                        content = content.replace(f"@{k}", str(v) if v is not None else "")
                messages.append({"role": role, "content": content})
        else:
            payload = job.payload
            if isinstance(payload, str):
                for k, v in self.state.items():
                    payload = payload.replace(f"${{{k}}}", str(v) if v is not None else "")
            messages = [{"role": "user", "content": str(payload)}]

        result = self._wf_ctx.llm_call(
            job.worker,
            messages=messages,
            mode=job.mode,
            temperature=job.temp,
            max_tokens=job.max_tokens,
            grammar=job.grammar,
            capture=job.capture,
            no_think=job.no_think,
            tag=job.id,
        )

        # Coerce if specified
        if job.coerce and isinstance(result, str):
            try:
                if job.coerce == "int":
                    result = int(result)
                elif job.coerce == "float":
                    result = float(result)
            except (ValueError, TypeError):
                pass

        return result

    # ── Event Dispatch ────────────────────────────────────

    def _fire_event(self, event: GatewayEvent):
        """Dispatch event to matching subscriptions."""
        self.events.append(event)
        self.on_event_cb(event)
        log.info("event: %s.%s", event.job_id, event.event_type)
        self.on_thread("system", "gateway", f"event: {event.job_id}.{event.event_type}", {
            "job_id": event.job_id, "event_type": event.event_type,
        })

        # Direct subscriptions: "job_id.done"
        event_key = f"{event.job_id}.{event.event_type}"
        for sub in self._subs.get(event_key, []):
            self._run_handler(sub, event)

        # Wildcard: "base_id.*.done" matches "base_id.entity_0.done"
        parts = event.job_id.rsplit(".", 1)
        if len(parts) == 2:
            wildcard_key = f"{parts[0]}.*.{event.event_type}"
            for sub in self._subs.get(wildcard_key, []):
                self._run_handler(sub, event)

        # all_done subscriptions
        for sub in self._all_done_subs:
            if self._check_all_done(sub):
                self._run_handler(sub, event)

    def _check_all_done(self, sub: Subscription) -> bool:
        """Check if all jobs in wait_for are done."""
        for pattern in sub.wait_for:
            if pattern.endswith(".*"):
                prefix = pattern[:-2]
                matching = [j for jid, j in self._jobs.items() if jid.startswith(prefix + ".")]
                if not matching or not all(j.status == JobStatus.DONE for j in matching):
                    return False
            else:
                job = self._jobs.get(pattern)
                if not job or job.status != JobStatus.DONE:
                    return False
        return True

    def _run_handler(self, sub: Subscription, event: GatewayEvent):
        """Execute handler assembly + process then-actions."""
        if not sub.handler_asm and not sub.then:
            return

        # Merge event context into vars
        self._wf_ctx.vars["_event"] = {
            "job_id": event.job_id, "type": event.event_type,
            "result": event.result, "error": event.error,
        }
        # Merge subscription context
        for k, v in sub.context.items():
            self._wf_ctx.vars[k] = v

        # Run assembly handler
        if sub.handler_asm:
            try:
                asm_result = asm_execute(sub.handler_asm, self._wf_ctx)
                # Merge asm output back to shared state
                merged_keys = []
                for k, v in asm_result.state.items():
                    self.state[k] = v
                    merged_keys.append(k)
                self.on_thread("system", "handler", f"{sub.event}: merged {merged_keys}", {"asm_error": asm_result.error})
                if asm_result.error:
                    log.error("handler asm error for %s: %s", sub.event, asm_result.error)
                    self.on_thread("system", "handler", f"ERROR: {asm_result.error}", {})
            except Exception as exc:
                log.error("handler failed for %s: %s", sub.event, exc)
                self.on_thread("system", "handler", f"EXCEPTION: {exc}", {})

        # Process then-actions
        for action in sub.then:
            self._process_then(action, event)

    def _process_then(self, action: dict, event: GatewayEvent):
        """Process a then-action: enqueue, for_each, etc."""
        if "enqueue" in action:
            template_name = action["enqueue"]
            with_ctx = action.get("with", {})
            # Resolve with-context variables
            resolved_ctx = {}
            for k, v in with_ctx.items():
                if isinstance(v, str) and v.startswith("$"):
                    resolved_ctx[k] = self.state.get(v[1:], v)
                else:
                    resolved_ctx[k] = v

            if "for_each" in action:
                items_key = action["for_each"]
                items = self.state.get(items_key, [])
                if not isinstance(items, list):
                    items = []
                for idx, item in enumerate(items):
                    job = self._instantiate_template(
                        template_name, f"{template_name}.{idx}",
                        {**resolved_ctx, "item": item, "index": idx, "item_idx": idx}
                    )
                    if job:
                        self.enqueue(job)
            else:
                job = self._instantiate_template(template_name, template_name, resolved_ctx)
                if job:
                    self.enqueue(job)

    def _instantiate_template(self, name: str, job_id: str, context: dict) -> GatewayJob | None:
        """Create a job from a template + context."""
        tpl = self._templates.get(name)
        if not tpl:
            log.warning("unknown job template: %s", name)
            return None

        # Interpolate template values with context
        def interp(val):
            if not isinstance(val, str):
                return val
            for k, v in {**self.state, **context}.items():
                val = val.replace(f"${{{k}}}", str(v) if v is not None else "")
                val = val.replace(f"${k}", str(v) if v is not None else "")
            return val

        messages = None
        if "messages" in tpl:
            messages = []
            for m in tpl["messages"]:
                if isinstance(m, dict):
                    for role, content in m.items():
                        messages.append({"role": role, "content": interp(str(content))})

        return GatewayJob(
            id=job_id,
            worker=tpl.get("worker", "generator"),
            payload=interp(tpl.get("payload", "")),
            mode=tpl.get("mode", "prompt"),
            temp=float(tpl.get("temp", 0.6)),
            max_tokens=int(tpl.get("max", 2048)),
            grammar=tpl.get("grammar"),
            capture=tpl.get("capture"),
            coerce=tpl.get("coerce"),
            no_think=bool(tpl.get("no_think", False)),
            messages=messages,
            context=context,
        )

    # ── v3 YAML Parser ────────────────────────────────────

    @classmethod
    def from_yaml(
        cls,
        yaml_text: str,
        workers: dict[str, str],
        settings: dict[str, Any] | None = None,
        on_event: Callable | None = None,
        on_thread: Callable | None = None,
    ) -> "GatewayRuntime":
        """Parse v3 YAML and create runtime with jobs + subscriptions."""
        spec = yaml.safe_load(yaml_text)
        runtime = cls(workers=workers, settings=settings, on_event=on_event, on_thread=on_thread)

        # Store config in state
        if "config" in spec:
            runtime.state["config"] = spec["config"]
            runtime._wf_ctx.vars["config"] = spec["config"]

        # Store input
        if "input" in spec:
            runtime.state["input"] = spec["input"]
            runtime._wf_ctx.vars["input"] = spec["input"]

        # Register job templates
        for name, tpl in spec.get("job_templates", {}).items():
            runtime._templates[name] = tpl

        # Parse subscriptions (on:) — YAML parses bare `on` as boolean True
        on_section = spec.get("on") or spec.get(True) or {}
        for event_key, handler_spec in on_section.items():
            asm_code = handler_spec.get("do", "")
            then_actions = handler_spec.get("then", [])
            context = handler_spec.get("context", {})

            # Parse "all_done: [a, b]" pattern
            if event_key.startswith("all_done"):
                # all_done: [claims, answer] → wait_for = ["claims", "answer"]
                # The key format: "all_done: [a, b]" or value has wait_for list
                wait_for = handler_spec.get("wait_for", [])
                if not wait_for:
                    # Try parsing from key: "all_done: [a, b]"
                    if ":" in event_key:
                        list_part = event_key.split(":", 1)[1].strip()
                        if list_part.startswith("["):
                            wait_for = [s.strip().strip("\"'") for s in list_part.strip("[]").split(",")]
                sub = Subscription(
                    event=event_key, handler_asm=asm_code,
                    then=then_actions, wait_for=wait_for, context=context,
                )
                runtime.subscribe(sub)
            else:
                sub = Subscription(
                    event=event_key, handler_asm=asm_code,
                    then=then_actions, context=context,
                )
                runtime.subscribe(sub)

        # Create initial jobs
        for job_spec in spec.get("jobs", []):
            payload = job_spec.get("payload", "")
            # Resolve payload functions: fn_name($var) or fn_name(literal)
            if isinstance(payload, str):
                import re
                fn_match = re.match(r'^(\w+)\((.+)\)$', payload.strip())
                if fn_match and fn_match.group(1) in runtime._payload_fns:
                    fn_name, arg_str = fn_match.group(1), fn_match.group(2).strip()
                    # Resolve arg: $input → state value, else literal
                    if arg_str.startswith("$"):
                        arg_val = runtime.state.get(arg_str[1:], arg_str)
                    else:
                        arg_val = arg_str
                    payload = runtime._payload_fns[fn_name](arg_val)
                elif "$input" in payload:
                    inp = runtime.state.get("input", "")
                    payload = payload.replace("$input", str(inp))

            job = GatewayJob(
                id=job_spec["id"],
                worker=job_spec.get("worker", "generator"),
                payload=payload,
                priority=job_spec.get("priority", "normal"),
                timeout=float(job_spec.get("timeout", "120").rstrip("s")),
                retry=int(job_spec.get("retry", 0)),
                temp=float(job_spec.get("temp", 0.6)),
                max_tokens=int(job_spec.get("max", 2048)),
                no_think=bool(job_spec.get("no_think", False)),
                tags=job_spec.get("tags", []),
            )
            runtime.enqueue(job)

        return runtime
