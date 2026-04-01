"""
Gateway Queue Runtime for Workflow v3.

Job-based reactive execution: jobs → per-worker queues → events → handlers → chaining.
Workers always busy. Runtime fills gaps with assembly transforms.
"""
from __future__ import annotations

import logging
import re
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
    stop: list[str] | None = None
    # ComfyUI fields
    job_type: str = "llm"  # "llm" | "comfyui"
    comfyui_workflow: str = ""
    comfyui_node: str = "6"
    comfyui_field: str = "text"
    comfyui_server: str = "http://127.0.0.1:8188"
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


# ── Interpolation helpers ─────────────────────────────────

def _resolve_interp_path(path: str, state: dict[str, Any]) -> Any:
    parts = str(path or "").split(".")
    if not parts or not parts[0]:
        return None
    val = state.get(parts[0])
    for p in parts[1:]:
        if isinstance(val, dict):
            val = val.get(p)
        elif isinstance(val, list) and p.isdigit():
            idx = int(p)
            if idx < 0 or idx >= len(val):
                return None
            val = val[idx]
        else:
            return None
    return val


def _interpolate_text(text: Any, state: dict[str, Any]) -> Any:
    if not isinstance(text, str):
        return text

    # Braced dotted refs: {$path.to.value} and ${path.to.value}
    def _repl_braced(match):
        value = _resolve_interp_path(match.group(1), state)
        return str(value) if value is not None else ""

    text = re.sub(r'\{\$([a-zA-Z_][\w.]*)\}', _repl_braced, text)
    text = re.sub(r'\$\{([a-zA-Z_][\w.]*)\}', _repl_braced, text)

    # Bare refs: $name or $name.path
    def _repl_bare(match):
        value = _resolve_interp_path(match.group(1), state)
        return str(value) if value is not None else match.group(0)

    text = re.sub(r'(?<![\w{])\$([a-zA-Z_][\w.]*)', _repl_bare, text)
    return text


# ── Gateway Runtime ───────────────────────────────────────

def _parse_messages(raw_messages: list, state: dict) -> list[dict]:
    """Parse YAML messages list into [{role, content}] with variable interpolation."""

    result = []
    for m in raw_messages:
        if isinstance(m, dict):
            if "role" in m and "content" in m:
                role, content = m["role"], m["content"]
            else:
                role = list(m.keys())[0]
                content = m[role]
        elif isinstance(m, str):
            role, content = "user", m
        else:
            continue
        result.append({
            "role": str(_interpolate_text(str(role), state)),
            "content": _interpolate_text(str(content), state),
        })
    return result


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
        self._payload_templates: dict[str, dict] = {}

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
        """Add job to worker queue. Returns job_id. Skips if job ID already exists."""
        with self._jobs_lock:
            if job.id in self._jobs:
                log.debug("skip enqueue: job %s already exists (status=%s)", job.id, self._jobs[job.id].status.value)
                return job.id
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
        self.on_thread(
            "system",
            "gateway",
            f"enqueued: {job.id} → {worker}",
            {"job_id": job.id, "worker": worker, "worker_url": self.workers.get(worker, "")},
        )
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
                "worker_url": self.workers.get(j.worker, ""),
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
        # ComfyUI jobs have their own server URL, don't need worker mapping
        if not base_url and worker != "comfyui":
            log.error("no URL for worker %s", worker)
            return

        lock = self._get_endpoint_lock(base_url or worker)

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
            self.on_thread(
                "system",
                "gateway",
                f"active: {job.id}",
                {"job_id": job.id, "worker": worker, "worker_url": base_url},
            )

            try:
                with lock:
                    result = self._execute_job(job)
                job.result = result
                job.status = JobStatus.DONE
                job.finished_at = time.time()
                # Store result in shared state for both runtime snapshots and assembly handlers.
                self.state[job.id] = result
                self._wf_ctx.vars[job.id] = result
                self._wf_ctx.state[job.id] = result
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
        """Execute a single job — dispatch by job_type."""
        if job.job_type == "comfyui":
            return self._execute_comfyui(job)
        return self._execute_llm(job)

    def _execute_comfyui(self, job: GatewayJob) -> Any:
        """Execute a ComfyUI image generation job."""
        import json as _json
        from pathlib import Path

        extra = job.context
        value = self._interpolate(str(job.payload or ""), extra)
        server = job.comfyui_server
        wf_path = Path(job.comfyui_workflow)

        if not wf_path.exists():
            raise FileNotFoundError(f"ComfyUI workflow not found: {wf_path}")

        with open(wf_path, "r", encoding="utf-8") as f:
            workflow = _json.load(f)

        # Inject value into node
        node_id = job.comfyui_node
        field = job.comfyui_field
        if node_id in workflow and field in workflow[node_id].get("inputs", {}):
            workflow[node_id]["inputs"][field] = value

        # Submit to ComfyUI
        resp = self._http.post(f"{server}/prompt", json={"prompt": workflow}, timeout=30)
        resp.raise_for_status()
        result = resp.json()
        prompt_id = result.get("prompt_id", "")
        node_errors = result.get("node_errors", {})

        if node_errors:
            raise RuntimeError(f"ComfyUI node errors: {node_errors}")

        self.on_thread("system", "ComfyUI", f"Queued: {prompt_id}", {"prompt_id": prompt_id, "job_id": job.id})

        # Poll for completion
        max_wait = int(job.timeout)
        poll_interval = 3
        elapsed = 0
        image_url = None

        while elapsed < max_wait:
            time.sleep(poll_interval)
            elapsed += poll_interval
            try:
                hist_resp = self._http.get(f"{server}/history/{prompt_id}", timeout=10)
                hist_data = hist_resp.json()
                prompt_data = hist_data.get(prompt_id, {})
                status = prompt_data.get("status", {})
                if status.get("completed"):
                    outputs = prompt_data.get("outputs", {})
                    for nid, out in outputs.items():
                        if "images" in out:
                            for img in out["images"]:
                                fname = img.get("filename", "")
                                subfolder = img.get("subfolder", "")
                                img_type = img.get("type", "output")
                                image_url = f"{server}/view?filename={fname}&subfolder={subfolder}&type={img_type}"
                                break
                        if image_url:
                            break
                    break
            except Exception:
                pass

        if not image_url:
            raise TimeoutError(f"ComfyUI timeout waiting for {prompt_id} ({max_wait}s)")

        self.on_thread("system", "ComfyUI", f"Done: {image_url}", {"image_url": image_url, "job_id": job.id})
        return image_url

    def _execute_llm(self, job: GatewayJob) -> Any:
        """Execute a single LLM job."""
        extra = job.context  # per-job context (from for_each, with:, etc.)
        # Build messages
        if job.messages:
            messages = []
            for m in job.messages:
                role = m.get("role", "user")
                content = self._interpolate(m.get("content", ""), extra)
                messages.append({"role": role, "content": content})
        else:
            payload = self._interpolate(str(job.payload or ""), extra)
            messages = [{"role": "user", "content": payload}]

        is_probe = job.mode in ("probe", "probe_continue")
        try:
            result = self._wf_ctx.llm_call(
                job.worker,
                messages=messages,
                mode=job.mode,
                temperature=job.temp,
                max_tokens=job.max_tokens,
                grammar=job.grammar,
                capture=job.capture,
                no_think=job.no_think,
                stop=job.stop,
                max_continue=1 if is_probe else None,
                tag=job.id,
            )
        except Exception as exc:
            debug_payload = {
                "job_id": job.id,
                "worker": job.worker,
                "mode": job.mode,
                "is_probe": is_probe,
                "temperature": job.temp,
                "max_tokens": job.max_tokens,
                "stop": job.stop,
                "grammar": bool(job.grammar),
                "messages": messages,
            }
            log.error("LLM job failed: %s payload=%r error=%s", job.id, debug_payload, exc)
            self.on_thread("system", "llm-debug", f"failed {job.id}", {
                "job_id": job.id,
                "error": str(exc),
                "request": debug_payload,
            })
            raise

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
        direct_subs = self._subs.get(event_key, [])
        self.on_thread("system", "event-debug", f"direct {event_key}", {
            "event_key": event_key, "count": len(direct_subs),
        })
        for sub in direct_subs:
            self._run_handler(sub, event)

        # Wildcard: "base_id.*.done" matches "base_id.entity_0.done"
        parts = event.job_id.rsplit(".", 1)
        if len(parts) == 2:
            wildcard_key = f"{parts[0]}.*.{event.event_type}"
            wildcard_subs = self._subs.get(wildcard_key, [])
            self.on_thread("system", "event-debug", f"wildcard {wildcard_key}", {
                "event_key": wildcard_key, "count": len(wildcard_subs),
            })
            for sub in wildcard_subs:
                self._run_handler(sub, event)
        elif not direct_subs:
            self.on_thread("system", "event-debug", f"no-handler {event_key}", {
                "event_key": event_key, "count": 0,
            })

        # all_done subscriptions (fire once, then remove)
        fired = []
        for sub in self._all_done_subs:
            if self._check_all_done(sub):
                self._run_handler(sub, event)
                fired.append(sub)
        for sub in fired:
            self._all_done_subs.remove(sub)

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

        parent_job = self._jobs.get(event.job_id)
        # Merge event context into vars
        self._wf_ctx.vars["_event"] = {
            "job_id": event.job_id, "type": event.event_type,
            "result": event.result, "error": event.error,
        }
        # Parent job context is the main source for item/item_idx chains.
        if parent_job and parent_job.context:
            for k, v in parent_job.context.items():
                self._wf_ctx.vars[k] = v
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
                if "entity_nodes" in asm_result.state:
                    entity_nodes = asm_result.state.get("entity_nodes")
                    count = len(entity_nodes) if isinstance(entity_nodes, list) else None
                    self.on_thread(
                        "system",
                        "handler-debug",
                        f"{sub.event}: entity_nodes={count}",
                        {"event": sub.event, "entity_nodes_count": count},
                    )
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

            # Inherit explicit with-context from parent job (e.g. item_idx)
            parent_job = self._jobs.get(event.job_id)
            inherited_ctx = dict(parent_job.context) if parent_job and parent_job.context else {}

            # Resolve with-context variables (check parent context first, then state)
            resolved_ctx = {}
            for k, v in with_ctx.items():
                if isinstance(v, str) and v.startswith("$"):
                    ref = v[1:]
                    if ref in inherited_ctx:
                        resolved_ctx[k] = inherited_ctx[ref]
                    else:
                        resolved = self._resolve_path(ref)
                        resolved_ctx[k] = resolved if resolved is not None else v
                else:
                    resolved_ctx[k] = v

            # Derive entity index from parent job id (e.g. trim_probe.3 → .3)
            parent_suffix = ""
            if "." in event.job_id:
                parent_suffix = "." + event.job_id.rsplit(".", 1)[1]

            # Merge: inherited from parent → explicit with → for_each
            merged_ctx = {**inherited_ctx, **resolved_ctx}

            if "for_each" in action:
                items_key = action["for_each"]
                if isinstance(items_key, str):
                    if items_key in merged_ctx:
                        items = merged_ctx[items_key]
                    else:
                        items = self._resolve_path(items_key, merged_ctx)
                        if items is None and items_key.startswith(("@", "$")):
                            items = self._resolve_path(items_key[1:], merged_ctx)
                else:
                    items = items_key
                if not isinstance(items, list):
                    self.on_thread(
                        "system",
                        "then-debug",
                        f"for_each {template_name} <- {items_key} (not-list)",
                        {
                            "template": template_name,
                            "items_key": items_key,
                            "resolved_type": type(items).__name__,
                            "resolved_value": items,
                        },
                    )
                    items = []
                self.on_thread(
                    "system",
                    "then-debug",
                    f"for_each {template_name} <- {items_key} ({len(items)})",
                    {"template": template_name, "items_key": items_key, "count": len(items)},
                )
                for idx, item_val in enumerate(items):
                    # for_each: item = current element, index = position
                    # with: adds explicit params for chaining (e.g. item_idx)
                    job = self._instantiate_template(
                        template_name, f"{template_name}.{idx}",
                        {**merged_ctx, "item": item_val, "index": idx}
                    )
                    if job:
                        self.enqueue(job)
            else:
                if parent_suffix:
                    job_id = template_name + parent_suffix
                elif "item_idx" in merged_ctx:
                    job_id = f"{template_name}.{merged_ctx['item_idx']}"
                else:
                    job_id = template_name
                job = self._instantiate_template(template_name, job_id, merged_ctx)
                if job:
                    self.enqueue(job)

    def _instantiate_template(self, name: str, job_id: str, context: dict) -> GatewayJob | None:
        """Create a job from a template + context."""
        tpl = self._templates.get(name)
        if not tpl:
            log.warning("unknown job template: %s", name)
            return None

        context = dict(context or {})
        if "item" not in context and "item_idx" in context:
            try:
                item_idx = int(context["item_idx"])
            except Exception:
                item_idx = -1
            items = self.state.get("items", [])
            if isinstance(items, list) and 0 <= item_idx < len(items):
                context["item"] = items[item_idx]
            elif isinstance(items, list):
                log.info("skip template %s: item_idx %s out of range", name, context.get("item_idx"))
                return None

        # Resolve template field refs ($config.xxx)
        def tpl_resolve(val):
            if isinstance(val, str) and val.startswith("$"):
                resolved = self._resolve_path(val[1:], context)
                return resolved if resolved is not None else val
            return val

        payload = self._interpolate(tpl.get("payload", ""), context)
        messages = None
        payload_from = tpl.get("payload_from")
        if payload_from:
            payload_args = self._resolve_mapping_values(tpl.get("payload_args", {}), context)
            payload, messages = self._build_payload_from_template(str(payload_from), payload_args, context)
        elif "messages" in tpl:
            messages = _parse_messages(tpl["messages"], {**self.state, **context})

        if name == "table":
            self.on_thread(
                "system",
                "template-debug",
                "table payload built",
                {
                    "template": name,
                    "payload_from": payload_from,
                    "payload_preview": str(payload)[:400],
                    "messages": messages,
                    "context": context,
                },
            )

        # Parse capture
        capture = tpl_resolve(tpl.get("capture"))
        coerce = tpl.get("coerce")
        if isinstance(capture, dict):
            coerce = capture.get("coerce", coerce)
            capture = capture.get("regex", capture.get("pattern"))
        if isinstance(capture, str):
            capture = tpl_resolve(capture)

        grammar = tpl_resolve(tpl.get("grammar"))

        stop = tpl.get("stop")
        if isinstance(stop, str):
            stop = [stop]

        return GatewayJob(
            id=job_id,
            worker=tpl.get("worker", "generator"),
            payload=payload,
            mode=tpl.get("mode", "prompt"),
            temp=float(tpl.get("temp", tpl.get("temperature", 0.6))),
            max_tokens=int(tpl.get("max", tpl.get("max_tokens", 2048))),
            job_type="comfyui" if tpl.get("type") == "comfyui" else "llm",
            comfyui_workflow=tpl.get("workflow", ""),
            comfyui_node=str(tpl.get("node", "6")),
            comfyui_field=tpl.get("field", "text"),
            comfyui_server=tpl.get("server", "http://127.0.0.1:8188"),
            grammar=grammar,
            capture=capture,
            coerce=coerce,
            no_think=bool(tpl.get("no_think", False)),
            stop=stop,
            messages=messages,
            context=context,
        )

    # ── Helpers ────────────────────────────────────────────

    def _resolve_path(self, path: str, extra: dict | None = None) -> Any:
        """Resolve dotted path like 'item._title' from state + extra."""
        merged = {**self.state, **(extra or {})}
        parts = path.split(".")
        val = merged.get(parts[0])
        for p in parts[1:]:
            if val is None or not isinstance(val, dict):
                return None
            val = val.get(p)
        return val

    def _interpolate(self, text: str, extra: dict | None = None) -> str:
        """Replace {$path}, ${path}, and $path in text with state values."""
        merged = {**self.state, **(extra or {})}
        return str(_interpolate_text(text, merged))

    def _resolve_value(self, val: Any, extra: dict | None = None) -> Any:
        if isinstance(val, str):
            if val.startswith("$"):
                resolved = self._resolve_path(val[1:], extra)
                return resolved if resolved is not None else val
            fn_match = re.match(r'^(\w+)\((.+)\)$', val.strip())
            if fn_match and fn_match.group(1) in self._payload_fns:
                fn_name, arg_str = fn_match.group(1), fn_match.group(2).strip()
                arg_val = self._resolve_value(arg_str, extra)
                if isinstance(arg_val, str):
                    arg_val = self._interpolate(arg_val, extra)
                return self._payload_fns[fn_name](arg_val)
        return val

    def _resolve_mapping_values(self, data: Any, extra: dict | None = None) -> Any:
        if isinstance(data, dict):
            return {k: self._resolve_mapping_values(v, extra) for k, v in data.items()}
        if isinstance(data, list):
            return [self._resolve_mapping_values(v, extra) for v in data]
        return self._resolve_value(data, extra)

    def _build_payload_from_template(
        self,
        template_name: str,
        args: dict[str, Any] | None = None,
        extra: dict | None = None,
    ) -> tuple[str, list[dict] | None]:
        tpl = self._payload_templates.get(template_name)
        if not tpl:
            return "", None

        merged = {**self.state, **(extra or {})}
        if args:
            merged.update(args)

        mode = str(tpl.get("mode", "text") or "text").strip().lower()
        if mode == "chat":
            return "", _parse_messages(tpl.get("messages", []), merged)
        return str(_interpolate_text(str(tpl.get("template", "")), merged)), None

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

        if "context" in spec:
            runtime.state["context"] = spec["context"]
            runtime._wf_ctx.vars["context"] = spec["context"]

        # Store input
        if "input" in spec:
            runtime.state["input"] = spec["input"]
            runtime._wf_ctx.vars["input"] = spec["input"]

        # Register job templates
        for name, tpl in spec.get("job_templates", {}).items():
            runtime._templates[name] = tpl
        for name, tpl in spec.get("payload_templates", {}).items():
            runtime._payload_templates[name] = tpl

        # Parse subscriptions (on:)
        on_section = spec.get("on") or spec.get(True) or {}
        if isinstance(on_section, list):
            for handler_spec in on_section:
                if not isinstance(handler_spec, dict):
                    continue
                asm_code = str(handler_spec.get("do", "") or "")
                then_actions = handler_spec.get("then", [])
                context = handler_spec.get("context", {})

                if "all_done" in handler_spec:
                    wait_for = handler_spec.get("all_done", []) or handler_spec.get("wait_for", [])
                    if not isinstance(wait_for, list):
                        wait_for = [str(wait_for)]
                    sub = Subscription(
                        event="all_done",
                        handler_asm=asm_code,
                        then=then_actions,
                        wait_for=[str(x) for x in wait_for],
                        context=context,
                    )
                    runtime.subscribe(sub)
                    continue

                event_key = str(handler_spec.get("event", "") or "").strip()
                job_name = str(handler_spec.get("job", "") or "").strip()
                if job_name and event_key:
                    if job_name in runtime._templates:
                        wildcard_event_key = f"{job_name}.*.{event_key}"
                        direct_event_key = f"{job_name}.{event_key}"
                        runtime.subscribe(Subscription(
                            event=wildcard_event_key,
                            handler_asm=asm_code,
                            then=then_actions,
                            context=context,
                        ))
                        runtime.subscribe(Subscription(
                            event=direct_event_key,
                            handler_asm=asm_code,
                            then=then_actions,
                            context=context,
                        ))
                        continue
                    event_key = f"{job_name}.{event_key}"
                if not event_key:
                    continue
                sub = Subscription(
                    event=event_key,
                    handler_asm=asm_code,
                    then=then_actions,
                    context=context,
                )
                runtime.subscribe(sub)

        elif isinstance(on_section, dict):
            for event_key, handler_spec in on_section.items():
                asm_code = handler_spec.get("do", "")
                then_actions = handler_spec.get("then", [])
                context = handler_spec.get("context", {})

                # Legacy dict-form parsing
                if event_key.startswith("all_done"):
                    wait_for = handler_spec.get("wait_for", [])
                    if not wait_for and ":" in event_key:
                        list_part = event_key.split(":", 1)[1].strip()
                        if list_part.startswith("["):
                            wait_for = [s.strip().strip("\"'") for s in list_part.strip("[]").split(",")]
                    sub = Subscription(
                        event=event_key, handler_asm=asm_code,
                        then=then_actions, wait_for=wait_for, context=context,
                    )
                    runtime.subscribe(sub)
                else:
                    runtime.subscribe(Subscription(
                        event=event_key, handler_asm=asm_code,
                        then=then_actions, context=context,
                    ))
                    parts = event_key.rsplit(".", 1)
                    if len(parts) == 2 and parts[0] in runtime._templates:
                        runtime.subscribe(Subscription(
                            event=f"{parts[0]}.*.{parts[1]}",
                            handler_asm=asm_code,
                            then=then_actions,
                            context=context,
                        ))

        # Create initial jobs
        def job_resolve(val):
            return runtime._resolve_value(val)

        for job_spec in spec.get("jobs", []):
            payload = ""
            messages = None
            payload_from = job_spec.get("payload_from")
            if payload_from:
                payload_args = runtime._resolve_mapping_values(job_spec.get("payload_args", {}))
                payload, messages = runtime._build_payload_from_template(str(payload_from), payload_args)
            else:
                payload = job_spec.get("payload", "")
            # Resolve payload functions: fn_name($var) or fn_name(literal)
            if isinstance(payload, str):
                import re
                fn_match = re.match(r'^(\w+)\((.+)\)$', payload.strip())
                if fn_match and fn_match.group(1) in runtime._payload_fns:
                    fn_name, arg_str = fn_match.group(1), fn_match.group(2).strip()
                    # Resolve arg: $input → state value, else literal
                    if arg_str.startswith("$"):
                        arg_val = runtime._resolve_path(arg_str[1:])
                        if arg_val is None:
                            arg_val = arg_str
                    else:
                        arg_val = arg_str
                    payload = runtime._payload_fns[fn_name](arg_val)
                else:
                    payload = runtime._interpolate(payload)

            # Parse messages if present
            if messages is None and "messages" in job_spec:
                messages = _parse_messages(job_spec["messages"], runtime.state)

            # Parse capture: can be string or dict {regex, coerce}
            capture = job_resolve(job_spec.get("capture"))
            coerce = job_resolve(job_spec.get("coerce"))
            if isinstance(capture, dict):
                coerce = job_resolve(capture.get("coerce", coerce))
                capture = job_resolve(capture.get("regex", capture.get("pattern")))
            if isinstance(capture, str):
                capture = job_resolve(capture)

            # Parse stop: can be string or list
            stop = job_spec.get("stop")
            if isinstance(stop, str):
                stop = [job_resolve(stop)]
            elif isinstance(stop, list):
                stop = [job_resolve(x) if isinstance(x, str) else x for x in stop]

            grammar = job_resolve(job_spec.get("grammar"))

            job = GatewayJob(
                id=job_spec["id"],
                worker=job_spec.get("worker", "generator"),
                payload=payload,
                messages=messages,
                mode=job_spec.get("mode", "prompt"),
                priority=job_spec.get("priority", "normal"),
                timeout=float(str(job_spec.get("timeout", "120")).rstrip("s")),
                retry=int(job_spec.get("retry", 0)),
                temp=float(job_spec.get("temp", job_spec.get("temperature", 0.6))),
                max_tokens=int(job_spec.get("max", job_spec.get("max_tokens", 2048))),
                grammar=grammar,
                capture=capture,
                coerce=coerce,
                no_think=bool(job_spec.get("no_think", False)),
                stop=stop,
                tags=job_spec.get("tags", []),
            )
            runtime.enqueue(job)

        return runtime
