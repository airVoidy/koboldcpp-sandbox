"""Workflow DSL v2 Interpreter.

Reads YAML workflow spec, executes steps against LLM workers.
All calls visible in thread. No hidden prompts.

Modes:
  - prompt: standard LLM call
  - continue: continue assistant turn until EoT
  - probe_continue: inject into think, stop at tokens, read short answer
"""
from __future__ import annotations

import re
import yaml
import httpx
from typing import Any, Callable


def _is_token_limit_finish(finish_reason: str | None) -> bool:
    return str(finish_reason or "").strip().lower() in {"length", "max_tokens"}


_EXACT_CALL_RE = re.compile(r"^[A-Za-z_]\w*\((.*)\)$", re.DOTALL)


def _looks_like_expr(text: str) -> bool:
    text = str(text or "").strip()
    return text.startswith(("$", "@")) or bool(_EXACT_CALL_RE.match(text))


def _normalize_grammar(grammar: str | None) -> str | None:
    text = str(grammar or "").strip()
    if not text:
        return None
    if "::=" in text:
        return text
    return f"root ::= {text}"


def _probe_regex(grammar: str | None) -> re.Pattern[str] | None:
    text = str(grammar or "").strip()
    if not text or "::=" in text:
        return None
    try:
        return re.compile(text)
    except re.error:
        return None


def _coerce_intlike(value: Any, default: int | None = None) -> int:
    if isinstance(value, bool):
        return int(value)
    if isinstance(value, (int, float)):
        return int(value)
    text = str(value or "").strip()
    match = re.search(r"-?\d+", text)
    if match:
        return int(match.group(0))
    if default is not None:
        return default
    raise ValueError(f"Cannot parse int from {value!r}")


def _clean_probe_result(text: str, grammar: str | None = None) -> str:
    value = str(text or "").replace("\r\n", "\n").replace("\r", "\n").strip()
    if not value:
        return value
    if "\n" in value:
        value = value.split("\n", 1)[0].strip()
    while len(value) >= 2 and ((value[0], value[-1]) in {('"', '"'), ("'", "'")}):
        value = value[1:-1].strip()
    value = value.rstrip("\"' \t")
    pattern = _probe_regex(grammar)
    if pattern is not None:
        match = pattern.search(value)
        if match:
            return match.group(0).strip()
    return value


class WorkflowContext:
    """Runtime state for a workflow execution."""

    def __init__(
        self,
        workers: dict[str, str],       # role → base_url
        settings: dict[str, Any] | None = None,
        builtins: dict[str, Callable] | None = None,
        on_thread: Callable | None = None,  # callback(role, name, content, extra)
    ) -> None:
        self.workers = workers
        self.settings = settings or {}
        self.vars: dict[str, Any] = {}
        self.state: dict[str, Any] = {}   # @persistent state
        self.builtins = builtins or {}
        self.on_thread = on_thread or (lambda *a, **kw: None)
        self._http = httpx.Client(timeout=180.0, trust_env=False)

    def close(self):
        self._http.close()

    def get(self, ref: str) -> Any:
        """Resolve $var, $var.field, @state.path, or literal."""
        if ref.startswith("$settings."):
            return self.settings.get(ref[10:])
        if ref.startswith("$"):
            path = ref[1:].split(".")
            val = self.vars
            for p in path:
                if isinstance(val, dict):
                    val = val.get(p)
                elif isinstance(val, list) and p.isdigit():
                    val = val[int(p)]
                elif hasattr(val, p):
                    val = getattr(val, p)
                else:
                    return None
            return val
        if ref.startswith("@"):
            path = ref[1:].split(".")
            val = self.state
            for p in path:
                if isinstance(val, dict):
                    val = val.get(p)
                else:
                    return None
            return val
        return ref

    def set(self, ref: str, value: Any) -> None:
        """Set $var or @state path."""
        if ref.startswith("$"):
            path = ref[1:].split(".")
            target = self.vars
            for p in path[:-1]:
                if p not in target:
                    target[p] = {}
                current = target[p]
                # Wrap non-dict values in dict when dotted path needs it
                if not isinstance(current, dict):
                    target[p] = {"_value": current}
                target = target[p]
            target[path[-1]] = value
        elif ref.startswith("@"):
            path = ref[1:].split(".")
            target = self.state
            for p in path[:-1]:
                if p not in target:
                    target[p] = {}
                target = target[p]
            target[path[-1]] = value

    def interpolate(self, text: str) -> str:
        """Replace {$var} and {$var.field} in strings."""
        def replacer(m):
            ref = m.group(1)
            val = self.get("$" + ref if not ref.startswith("$") else ref)
            if val is None:
                return m.group(0)
            if isinstance(val, list):
                return ", ".join(str(v) for v in val)
            if isinstance(val, dict) and "_value" in val:
                return str(val["_value"])
            return str(val)
        return re.sub(r"\{\$([^}]+)\}", replacer, text)

    def eval_expr(self, expr: str) -> Any:
        """Evaluate an expression: $var, func($arg), or literal."""
        expr = expr.strip()

        # Variable reference
        if expr.startswith("$") or expr.startswith("@"):
            return self.get(expr)

        # Function call: name(args)
        m = re.match(r"(\w+)\((.+)\)$", expr, re.DOTALL)
        if m:
            fn_name = m.group(1)
            args_str = m.group(2)
            args = [self.eval_expr(a.strip()) for a in self._split_args(args_str)]
            fn = self.builtins.get(fn_name)
            if fn:
                return fn(*args)
            raise ValueError(f"Unknown function: {fn_name}")

        # String literal
        if expr.startswith('"') and expr.endswith('"'):
            return self.interpolate(expr[1:-1])

        # Number
        try:
            return int(expr)
        except ValueError:
            pass
        try:
            return float(expr)
        except ValueError:
            pass

        # Treat as string
        return self.interpolate(expr)

    def _split_args(self, s: str) -> list[str]:
        """Split function args respecting parentheses."""
        args, depth, current = [], 0, ""
        for ch in s:
            if ch == "(" : depth += 1
            elif ch == ")": depth -= 1
            elif ch == "," and depth == 0:
                args.append(current)
                current = ""
                continue
            current += ch
        if current.strip():
            args.append(current)
        return args

    # --- LLM calls ---

    def llm_call(
        self,
        role: str,
        *,
        prompt: str | None = None,
        messages: list[dict] | None = None,
        mode: str = "prompt",
        temperature: float = 0.6,
        max_tokens: int = 2048,
        stop: list[str] | None = None,
        grammar: str | None = None,
        tag: str = "",
        continue_on_length: bool | None = None,
        max_continue: int | None = None,
    ) -> str:
        """Call an LLM worker. Returns answer text (think stripped)."""
        base_url = self.workers.get(role, "").rstrip("/")
        if not base_url:
            raise ValueError(f"No worker for role '{role}'")
        url = f"{base_url}/v1/chat/completions"

        # Build messages
        if messages is None:
            messages = [{"role": "user", "content": prompt or ""}]

        is_continue = mode in ("continue", "probe_continue")
        payload: dict[str, Any] = {
            "messages": messages,
            "temperature": temperature,
            "max_tokens": max_tokens,
            "stream": False,
            "cache_prompt": False,
        }
        if is_continue:
            payload["continue_assistant_turn"] = True
        if stop:
            payload["stop"] = stop
        normalized_grammar = _normalize_grammar(grammar)
        if normalized_grammar:
            payload["grammar"] = normalized_grammar

        # Execute
        resp = self._http.post(url, json=payload)
        resp.raise_for_status()
        data = resp.json()
        chunk = data.get("choices", [{}])[0].get("message", {}).get("content", "")
        finish = data.get("choices", [{}])[0].get("finish_reason", "stop")

        result = chunk

        full_assistant = result
        if messages and messages[-1]["role"] == "assistant":
            full_assistant = messages[-1]["content"] + result
        should_continue = continue_on_length if continue_on_length is not None else (mode in {"continue", "probe_continue"})
        continue_limit = int(max_continue if max_continue is not None else self.settings.get("max_continue", 20))
        for cont_i in range(continue_limit):
            if not should_continue:
                break
            if not _is_token_limit_finish(finish):
                break
            cont_messages = list(messages[:-1]) if messages and messages[-1]["role"] == "assistant" else list(messages)
            cont_messages.append({"role": "assistant", "content": full_assistant})
            cont_payload = {**payload, "messages": cont_messages, "continue_assistant_turn": True}
            try:
                resp = self._http.post(url, json=cont_payload)
                resp.raise_for_status()
            except (httpx.RemoteProtocolError, httpx.ConnectError, httpx.ReadError):
                # Connection reset — retry with fresh client
                self._http.close()
                self._http = httpx.Client(timeout=60, trust_env=False)
                try:
                    resp = self._http.post(url, json=cont_payload)
                    resp.raise_for_status()
                except Exception:
                    break  # Return partial result
            except httpx.HTTPStatusError:
                break  # Server error, return partial result
            cont_data = resp.json()
            new_chunk = cont_data.get("choices", [{}])[0].get("message", {}).get("content", "")
            result += new_chunk
            full_assistant += new_chunk
            finish = cont_data.get("choices", [{}])[0].get("finish_reason", "stop")

        if mode == "probe_continue":
            probe_value = _clean_probe_result(result, grammar)
            self.on_thread(
                "worker",
                f"{role} ({tag or 'probe'})",
                probe_value,
                {"tag": tag, "finish_reason": finish, "raw": result},
            )
            return probe_value

        # Strip think
        think = ""
        answer = result
        think_match = re.search(r"<think\b[^>]*>([\s\S]*?)</think>", result, re.IGNORECASE)
        if think_match:
            think = think_match.group(1).strip()
            answer = re.sub(r"<think\b[^>]*>[\s\S]*?</think>\s*", "", result, flags=re.DOTALL | re.IGNORECASE).strip()
        elif "<think>" in result:
            idx = result.find("<think>")
            end_idx = result.rfind("</think>")
            if end_idx > idx:
                think = result[idx + 7:end_idx].strip()
                answer = result[end_idx + 8:].strip()

        self.on_thread("worker", f"{role} ({tag or mode})", answer, {"think": think, "tag": tag})
        return answer


# ---------------------------------------------------------------------------
# Step execution
# ---------------------------------------------------------------------------

def _resolve_params(ctx: WorkflowContext, step: dict) -> dict:
    """Extract temperature, max_tokens, stop from step dict."""
    params = {}
    if "temperature" in step:
        v = step["temperature"]
        params["temperature"] = float(ctx.eval_expr(str(v)) if isinstance(v, str) and v.startswith("$") else v)
    if "max_tokens" in step:
        v = step["max_tokens"]
        params["max_tokens"] = int(ctx.eval_expr(str(v)) if isinstance(v, str) and v.startswith("$") else v)
    if "stop" in step:
        params["stop"] = step["stop"]
    if "grammar" in step:
        params["grammar"] = str(step["grammar"])
    if "continue_on_length" in step:
        params["continue_on_length"] = bool(step["continue_on_length"])
    if "max_continue" in step:
        params["max_continue"] = int(step["max_continue"])
    return params


def _build_messages(ctx: WorkflowContext, msg_list: list[dict]) -> list[dict]:
    """Build messages array from DSL spec, interpolating variables."""
    messages = []
    for m in msg_list:
        for role in ("user", "assistant", "system"):
            if role in m:
                content = m[role]
                if isinstance(content, str):
                    if _looks_like_expr(content):
                        resolved = ctx.eval_expr(content)
                        content = str(resolved) if resolved is not None else content
                    content = ctx.interpolate(content)
                messages.append({"role": role, "content": content})
    return messages


def execute_step(ctx: WorkflowContext, step: Any) -> None:
    """Execute a single workflow step."""

    # String step: assignment like "@root.answer = $answer"
    if isinstance(step, str):
        if "=" in step:
            left, right = step.split("=", 1)
            ctx.set(left.strip(), ctx.eval_expr(right.strip()))
        return

    if not isinstance(step, dict):
        return

    # --- Parallel block ---
    # {"name": {"in_parallel": [...]}}
    for key, val in step.items():
        if isinstance(val, dict) and "in_parallel" in val:
            import concurrent.futures
            with concurrent.futures.ThreadPoolExecutor() as pool:
                futures = [pool.submit(execute_step, ctx, s) for s in val["in_parallel"]]
                concurrent.futures.wait(futures)
                for f in futures:
                    f.result()  # raise exceptions
            return

    # --- For loop ---
    # {"for $x in expr": [...]}
    for key, body in step.items():
        m = re.match(r"for\s+(\$\w+)\s+in\s+(.+)", key)
        if m:
            var_name = m.group(1)
            collection = ctx.eval_expr(m.group(2))
            if not isinstance(collection, (list, tuple)):
                ctx.on_thread("system", "for-loop", f"Collection for {var_name} is not iterable: {type(collection).__name__} = {collection}", {})
                return
            if not collection:
                ctx.on_thread("system", "for-loop", f"Collection for {var_name} is empty, skipping", {})
                return
            for item in collection:
                ctx.set(var_name, item)
                execute_steps(ctx, body)
            return

    # --- LLM call ---
    # {"role -> $target": {prompt/continue/mode/...}}
    for key, config in step.items():
        m = re.match(r"(\w+)\s*->\s*(\$[\w.]+)", key)
        if m and isinstance(config, dict):
            role = m.group(1)
            target = m.group(2)
            params = _resolve_params(ctx, config)
            tag = config.get("tag", "")
            mode = config.get("mode", "prompt")

            if "prompt" in config:
                prompt_expr = config["prompt"]
                if isinstance(prompt_expr, str) and _looks_like_expr(prompt_expr):
                    prompt = ctx.eval_expr(prompt_expr)
                else:
                    prompt = prompt_expr
                prompt = ctx.interpolate(str(prompt))
                result = ctx.llm_call(role, prompt=prompt, mode=mode, tag=tag, **params)
            elif "messages" in config:
                messages = _build_messages(ctx, config["messages"])
                result = ctx.llm_call(role, messages=messages, mode=mode, tag=tag, **params)
            else:
                return

            ctx.set(target, result)
            return

    # --- Parse steps ---
    if "parse_claims" in step:
        inner = step["parse_claims"]
        if isinstance(inner, dict):
            from_expr = inner.get("from", "")
            export = inner.get("export", [])
        else:
            from_expr = str(inner) if inner else ""
            export = step.get("export", [])
        text = str(ctx.eval_expr(from_expr))
        entities = _parse_list_from_text(text, "ENTITIES")
        axioms = _parse_list_from_text(text, "AXIOMS")
        hypotheses = _parse_list_from_text(text, "HYPOTHESES")
        if isinstance(export, list) and len(export) >= 3:
            ctx.set(export[0], entities)
            ctx.set(export[1], axioms)
            ctx.set(export[2], hypotheses)
        ctx.on_thread("system", "Parsed",
            f"ENTITIES: {len(entities)}, AXIOMS: {len(axioms)}, HYPOTHESES: {len(hypotheses)}", {})
        return

    if "parse_table" in step:
        inner = step["parse_table"]
        if isinstance(inner, dict):
            from_expr = inner.get("from", "")
            into = inner.get("into")
            export = inner.get("export")
        else:
            from_expr = str(inner) if inner else ""
            into = step.get("into")
            export = step.get("export")
        text = str(ctx.eval_expr(from_expr))
        nodes = _parse_markdown_table(text)
        if into:
            ctx.set(into, nodes)
        if export:
            ctx.set(export, nodes)
        ctx.on_thread("system", "Parsed", f"Table: {len(nodes)} rows", {})
        return

    # --- Verify axioms (single think accumulator, summary output) ---
    if "verify_axioms" in step:
        inner = step["verify_axioms"]
        if isinstance(inner, dict):
            items_expr = inner.get("items", "")
            answer_expr = inner.get("answer", "")
            table_expr = inner.get("table", "")
            role = inner.get("worker", "analyzer")
            tag = inner.get("tag", "verify")
        else:
            return

        items = ctx.eval_expr(items_expr) if isinstance(items_expr, str) else items_expr
        answer_text = str(ctx.eval_expr(answer_expr)) if answer_expr else ""
        table_text = str(ctx.eval_expr(table_expr)) if table_expr else ""

        if not items or not isinstance(items, list):
            ctx.on_thread("system", "Verify", "No items to verify", {})
            return

        base_url = ctx.workers.get(role, "").rstrip("/")
        if not base_url:
            ctx.on_thread("system", "Verify", f"No worker for role '{role}'", {})
            return
        url = f"{base_url}/v1/chat/completions"

        # Build think accumulator (same as JS verifyAxiomsViaThink)
        think_accum = "\n"
        if table_text:
            think_accum += "Summary table:\n" + table_text + "\n\n"
        think_accum += "Verification:\n"
        full_assistant = "<think>" + think_accum

        # Add table truth check first
        all_items = []
        if table_text:
            all_items.append("Table matches truth")
        all_items.extend(str(item["_value"] if isinstance(item, dict) and "_value" in item else item) for item in items)

        results = []
        for item_text in all_items:
            question = f"\n(({item_text}) == 1) === "
            full_assistant += question

            resp = ctx._http.post(url, json={
                "messages": [
                    {"role": "user", "content": answer_text},
                    {"role": "assistant", "content": full_assistant},
                ],
                "continue_assistant_turn": True,
                "cache_prompt": False,
                "temperature": 0.1,
                "max_tokens": 100,
                "stop": ["\n"],
                "stream": False,
            })
            resp.raise_for_status()
            data = resp.json()
            verdict = (data.get("choices", [{}])[0].get("message", {}).get("content", "")).strip()

            passed = verdict.startswith("1") or verdict.lower().startswith("true")
            results.append({"text": item_text, "verdict": verdict, "pass": passed})
            think_accum += question + verdict + "\n"
            full_assistant += verdict + "\n"

        # Build summary like JS button does
        summary = "\n".join(
            f"{'✅' if r['pass'] else '❌'} {r['text']} = {r['verdict']}"
            for r in results
        )
        all_pass = all(r["pass"] for r in results)
        ctx.on_thread("verifier", f"{role} (axioms)",
            summary, {"think": think_accum, "tag": tag, "status": "pass" if all_pass else "fail"})
        return

    # --- ComfyUI generation ---
    if "comfyui" in step:
        inner = step["comfyui"]
        if not isinstance(inner, dict):
            return
        workflow_path = inner.get("workflow", "")
        node_id = str(inner.get("node", "6"))
        field = inner.get("field", "text")
        value = ctx.interpolate(str(ctx.eval_expr(inner.get("value", ""))))
        server = inner.get("server", "http://127.0.0.1:8188")
        export = inner.get("export")

        import json as _json
        from pathlib import Path

        # Resolve workflow path
        wf_path = Path(workflow_path)
        if not wf_path.is_absolute():
            # Try relative to common locations
            for base in [Path.cwd(), Path.home() / ".lmstudio" / "models"]:
                candidate = base / workflow_path
                if candidate.exists():
                    wf_path = candidate
                    break

        if not wf_path.exists():
            ctx.on_thread("system", "ComfyUI", f"Workflow not found: {wf_path}", {"tag": "comfyui"})
            return

        with open(wf_path, "r", encoding="utf-8") as f:
            workflow = _json.load(f)

        # Inject value into node
        if node_id in workflow and field in workflow[node_id].get("inputs", {}):
            workflow[node_id]["inputs"][field] = value

        # Submit to ComfyUI
        try:
            resp = ctx._http.post(f"{server}/prompt", json={"prompt": workflow}, timeout=30)
            resp.raise_for_status()
            result = resp.json()
            prompt_id = result.get("prompt_id", "")
            node_errors = result.get("node_errors", {})

            if node_errors:
                ctx.on_thread("system", "ComfyUI", f"Errors: {node_errors}", {"tag": "comfyui"})
                return

            ctx.on_thread("system", "ComfyUI",
                f"Queued: {prompt_id}\nPrompt: {value[:100]}...",
                {"tag": "comfyui", "prompt_id": prompt_id})

            # Poll for completion
            import time
            max_wait = int(inner.get("timeout", 300))
            poll_interval = 3
            elapsed = 0
            image_url = None

            while elapsed < max_wait:
                time.sleep(poll_interval)
                elapsed += poll_interval
                try:
                    hist_resp = ctx._http.get(f"{server}/history/{prompt_id}", timeout=10)
                    hist_data = hist_resp.json()
                    prompt_data = hist_data.get(prompt_id, {})
                    status = prompt_data.get("status", {})
                    if status.get("completed"):
                        # Find output images
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

            if image_url:
                # Include prompt snippet for matching entity
                prompt_snippet = value[:80] if value else ""
                ctx.on_thread("system", "ComfyUI",
                    f"Done! Image: {image_url}",
                    {"tag": "comfyui", "image_url": image_url, "prompt_id": prompt_id,
                     "prompt_snippet": prompt_snippet})
                if export:
                    ctx.set(export, image_url)
            else:
                ctx.on_thread("system", "ComfyUI",
                    f"Timeout waiting for {prompt_id} ({max_wait}s)",
                    {"tag": "comfyui", "prompt_id": prompt_id})

        except Exception as exc:
            ctx.on_thread("system", "ComfyUI", f"Error: {exc}", {"tag": "comfyui"})
        return

    # --- Assignment in dict form ---
    if "set" in step:
        for ref, expr in step["set"].items():
            ctx.set(ref, ctx.eval_expr(str(expr)))
        return


def execute_steps(ctx: WorkflowContext, steps: list) -> None:
    """Execute a list of steps."""
    for step in steps:
        try:
            execute_step(ctx, step)
        except Exception as exc:
            ctx.on_thread("system", "step-error", f"Step failed: {exc}\nStep: {step}", {})
            # Continue to next step instead of aborting entire workflow


# ---------------------------------------------------------------------------
# Workflow runner
# ---------------------------------------------------------------------------

def parse_spec(yaml_text: str) -> dict:
    """Parse YAML workflow into spec dict. No execution."""
    spec = yaml.safe_load(yaml_text)
    assert spec.get("dsl", "").startswith("workflow/"), f"Unknown DSL: {spec.get('dsl')}"
    return spec


def run_workflow(
    yaml_text: str,
    workers: dict[str, str],
    settings: dict[str, Any] | None = None,
    builtins: dict[str, Callable] | None = None,
    on_thread: Callable | None = None,
    initial_vars: dict[str, Any] | None = None,
) -> WorkflowContext:
    """Parse YAML workflow and execute it."""
    spec = parse_spec(yaml_text)

    # Default builtins
    default_builtins = {
        "claims": lambda x: (
            "Ты — логический аналитик. Извлеки все атомарные утверждения/факты из текста.\n"
            "Верни ТОЛЬКО в формате:\n"
            "ENTITIES: [сущность1, сущность2, ...]\n"
            "AXIOMS:\n- утверждение 1\n- утверждение 2\n"
            "HYPOTHESES:\n- гипотеза 1\n\n"
            "Требования:\n"
            "- Используй pos('Имя') для позиционных утверждений.\n"
            "- AXIOMS = факты, данные как условие.\n"
            "- HYPOTHESES = выводы, предположения.\n"
            "- Каждое утверждение атомарное и короткое.\n"
            "- Не выводи прозу или JSON.\n"
            "- Отвечай на языке текста.\n\n"
            "Текст для анализа:\n" + str(x)
        ),
        "table": lambda x: (
            "Ты — экстрактор данных. Распарси текст в структурированную таблицу.\n"
            "Верни markdown-таблицу с подходящими колонками.\n"
            "Если есть сущности со свойствами: | Сущность | Свойство1 | Свойство2 |\n"
            "Если список: | # | Элемент | Детали |\n"
            "Кратко. Только таблица, без комментариев.\n"
            "Отвечай на языке текста.\n\n"
            "Текст:\n" + str(x)
        ),
        "numbered": lambda text: "\n".join(f"{i+1}. {l}" for i, l in enumerate(str(text).split("\n"))),
        "concat": lambda *args: sum((list(a) if isinstance(a, list) else [a] for a in args), []),
        "slice_lines": lambda text, start, end: _slice_lines(text, start, end),
        "enrich_entities": lambda entities, answer: _enrich_entities(entities, answer),
        "join": lambda lst, sep=", ": sep.join(str(x) for x in lst),
        "len": lambda x: len(x) if x else 0,
        "unique": lambda x: list(set(x)) if isinstance(x, list) else x,
    }
    if builtins:
        default_builtins.update(builtins)

    ctx = WorkflowContext(
        workers=workers,
        settings=settings or {},
        builtins=default_builtins,
        on_thread=on_thread,
    )

    # Load let vars
    for key, val in spec.get("let", {}).items():
        ctx.set("$" + key, val)
    for key, val in (initial_vars or {}).items():
        ref = key if str(key).startswith(("$", "@")) else "$" + str(key)
        ctx.set(ref, val)

    # Store triggers for later execution
    ctx.triggers = spec.get("triggers", {})

    # Execute flow
    execute_steps(ctx, spec.get("flow", []))

    return ctx


def run_trigger(
    ctx: WorkflowContext,
    trigger_name: str,
) -> None:
    """Execute a named trigger from the workflow spec."""
    trigger_steps = ctx.triggers.get(trigger_name)
    if not trigger_steps:
        ctx.on_thread("system", "Trigger", f"Unknown trigger: {trigger_name}", {})
        return
    if isinstance(trigger_steps, list):
        execute_steps(ctx, trigger_steps)
    elif isinstance(trigger_steps, dict):
        execute_step(ctx, trigger_steps)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _enrich_entities(entities: list[dict], answer: str) -> list[dict]:
    """Add _startNum and _firstLine to each entity by finding title in answer."""
    lines = answer.split("\n")
    for entity in entities:
        title = entity.get("_title", "")
        if not title:
            continue
        # Case-insensitive search for title in lines
        title_lower = title.lower().strip()
        for i, line in enumerate(lines):
            if title_lower in line.lower():
                entity["_startNum"] = i + 1  # 1-based
                entity["_firstLine"] = line.strip()
                break
    return entities


def _slice_lines(text: Any, start: Any, end: Any) -> str:
    lines = str(text).split("\n")
    start_idx = max(0, _coerce_intlike(start, 1) - 1)
    end_idx = _coerce_intlike(end, len(lines))
    return "\n".join(lines[start_idx:end_idx]).strip()


def _parse_list_from_text(text: str, section: str) -> list[str]:
    """Parse ENTITIES/AXIOMS/HYPOTHESES from claims text."""
    lines = text.split("\n")
    items = []
    in_section = False
    for line in lines:
        trimmed = line.strip()
        if trimmed.upper().startswith(section.upper() + ":"):
            in_section = True
            after = trimmed[len(section) + 1:].strip()
            if after.startswith("["):
                inner = after.strip("[]")
                items.extend(s.strip() for s in inner.split(",") if s.strip())
                in_section = False
            continue
        if in_section and re.match(r"^[A-Z_]+:", trimmed):
            in_section = False
            continue
        if in_section and trimmed.startswith("-"):
            items.append(trimmed[1:].strip())
    return items


def _parse_markdown_table(text: str) -> list[dict]:
    """Parse markdown table into list of dicts."""
    lines = [l for l in text.strip().split("\n") if l.strip().startswith("|")]
    if len(lines) < 3:
        return []
    headers = [h.strip() for h in lines[0].split("|") if h.strip() and not re.match(r"^-+$", h.strip())]
    rows = []
    for line in lines[2:]:
        cells = [c.strip() for c in line.split("|") if c.strip()]
        if not cells:
            continue
        row = {}
        for j, h in enumerate(headers):
            if j < len(cells):
                row[h] = cells[j]
        if row:
            row["_title"] = cells[0] if cells else ""
            row["_index"] = len(rows)
            rows.append(row)
    return rows
