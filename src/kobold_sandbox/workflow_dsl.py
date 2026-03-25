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

from .macro_registry import get_macro


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
    return None


def _capture_regex(capture: Any, grammar: str | None = None) -> re.Pattern[str] | None:
    capture_value = capture
    if isinstance(capture, dict):
        capture_value = capture.get("regex", "")
    text = str(capture_value or "").strip()
    if not text:
        return _probe_regex(grammar)
    try:
        return re.compile(text)
    except re.error:
        return _probe_regex(grammar)


def _capture_coerce(capture: Any) -> str | None:
    if isinstance(capture, dict):
        value = str(capture.get("coerce", "") or "").strip().lower()
        return value or None
    return None


def _probe_regex(grammar: str | None) -> re.Pattern[str] | None:
    text = str(grammar or "").strip()
    if not text or "::=" in text:
        return None
    try:
        return re.compile(text)
    except re.error:
        return None


def _has_unclosed_think(text: str) -> bool:
    value = str(text or "")
    start = re.search(r"<think\b[^>]*>", value, re.IGNORECASE)
    if not start:
        return False
    end = re.search(r"</think>", value[start.end():], re.IGNORECASE)
    return end is None


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


def _clean_probe_result(text: str, grammar: str | None = None, capture: Any = None) -> str:
    value = str(text or "").replace("\r\n", "\n").replace("\r", "\n").strip()
    if not value:
        return value
    if "\n" in value:
        value = value.split("\n", 1)[0].strip()
    while len(value) >= 2 and ((value[0], value[-1]) in {('"', '"'), ("'", "'")}):
        value = value[1:-1].strip()
    value = value.rstrip("\"' \t")
    pattern = _capture_regex(capture, grammar)
    if pattern is not None:
        match = pattern.search(value)
        if match:
            value = match.group(0).strip()
        lowered = value.lower()
        if "[01]" in pattern.pattern:
            if lowered.startswith("true"):
                value = "1"
            if lowered.startswith("false"):
                value = "0"
    coerce = _capture_coerce(capture)
    if coerce == "int":
        return str(_coerce_intlike(value))
    return value


def _probe_value_ready(text: str, grammar: str | None = None, capture: Any = None) -> bool:
    if _capture_regex(capture, grammar) is None and _capture_coerce(capture) is None:
        return False
    try:
        return bool(str(_clean_probe_result(text, grammar, capture)).strip())
    except Exception:
        return False


def _check_status(text: Any) -> str:
    value = str(text or "").strip()
    if re.search(r"\bPASS\b", value, re.IGNORECASE):
        return "pass"
    if re.search(r"\bFAIL\b", value, re.IGNORECASE):
        return "fail"
    return "pending"


def build_default_builtins(overrides: dict[str, Callable] | None = None) -> dict[str, Callable]:
    builtins: dict[str, Callable] = {
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
        "check_status": _check_status,
    }
    if overrides:
        builtins.update(overrides)
    return builtins


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
        self.macro_registry_path = self.settings.get("macro_registry_path")

    def close(self):
        self._http.close()

    def child(self) -> "WorkflowContext":
        """Create an isolated child context that shares workers/settings/builtins."""
        child = WorkflowContext(
            workers=self.workers,
            settings=self.settings,
            builtins=self.builtins,
            on_thread=self.on_thread,
        )
        child.macro_registry_path = self.macro_registry_path
        return child

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
        capture: Any = None,
        tag: str = "",
        max_continue: int | None = None,
        no_think: bool = False,
    ) -> str:
        """Call an LLM worker. Returns answer text (think stripped)."""
        base_url = self.workers.get(role, "").rstrip("/")
        if not base_url:
            raise ValueError(f"No worker for role '{role}'")
        url = f"{base_url}/v1/chat/completions"

        # Build messages
        if messages is None:
            messages = [{"role": "user", "content": prompt or ""}]

        # no_think: add assistant prefill to skip reasoning
        if no_think and (not messages or messages[-1]["role"] != "assistant"):
            messages = list(messages) + [{"role": "assistant", "content": "<think>\n\n</think>\n\n"}]

        is_continue = mode in ("continue", "probe_continue") or no_think
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
            payload["grammar_string"] = normalized_grammar

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
        continue_limit = int(max_continue if max_continue is not None else self.settings.get("max_continue", 20))
        for cont_i in range(continue_limit):
            if not _is_token_limit_finish(finish):
                break
            if mode == "probe_continue" and _probe_value_ready(result, grammar, capture):
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
            probe_value = _clean_probe_result(result, grammar, capture)
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
        elif _has_unclosed_think(result):
            start_match = re.search(r"<think\b[^>]*>", result, re.IGNORECASE)
            if start_match:
                think = result[start_match.end():].strip()
                answer = result[:start_match.start()].strip()

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
    if "capture" in step:
        params["capture"] = step["capture"]
    if "max_continue" in step:
        params["max_continue"] = int(step["max_continue"])
    if "no_think" in step:
        params["no_think"] = bool(step["no_think"])
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
    if "atomic" in step:
        inner = step["atomic"]
        if not isinstance(inner, dict):
            return

        child = ctx.child()
        bind_map = inner.get("bind", {}) or {}
        for callee_name, caller_expr in bind_map.items():
            target_ref = callee_name if str(callee_name).startswith(("$", "@")) else "$" + str(callee_name)
            value = ctx.eval_expr(str(caller_expr))
            child.set(target_ref, value)

        inline_flow = inner.get("flow")
        inline_steps = inner.get("steps")
        inline_dsl = inner.get("dsl")

        if inline_flow is not None:
            child.on_thread("system", "Atomic", "Run inline atomic flow", {"tag": "atomic"})
            execute_steps(child, inline_flow if isinstance(inline_flow, list) else [inline_flow])
        elif inline_steps is not None:
            child.on_thread("system", "Atomic", "Run inline atomic steps", {"tag": "atomic"})
            execute_steps(child, inline_steps if isinstance(inline_steps, list) else [inline_steps])
        elif inline_dsl:
            child.on_thread("system", "Atomic", "Run inline atomic DSL", {"tag": "atomic"})
            _run_atomic_dsl(child, str(inline_dsl))
        else:
            ctx.on_thread("system", "Atomic", "atomic step requires flow, steps, or dsl", {"tag": "atomic"})
            return

        export_map = inner.get("export", {}) or {}
        for caller_target, callee_ref in export_map.items():
            source_ref = callee_ref if str(callee_ref).startswith(("$", "@")) else "$" + str(callee_ref)
            ctx.set(str(caller_target), child.get(source_ref))
        return

    if "use_macro" in step:
        inner = step["use_macro"]
        if not isinstance(inner, dict):
            return
        macro_name = str(inner.get("name", "")).strip()
        if not macro_name:
            ctx.on_thread("system", "Macro", "Macro name is required", {})
            return
        macro = get_macro(macro_name, ctx.macro_registry_path)
        if not macro:
            ctx.on_thread("system", "Macro", f"Macro not found: {macro_name}", {})
            return
        if not macro.workflow_alias:
            ctx.on_thread(
                "system",
                "Macro",
                f"Macro '{macro_name}' is not workflow-callable yet",
                {"layer": macro.layer, "has_dsl": bool(macro.dsl)},
            )
            return

        child = ctx.child()
        bind_map = inner.get("bind", {}) or {}
        for callee_name, caller_expr in bind_map.items():
            target_ref = callee_name if str(callee_name).startswith(("$", "@")) else "$" + str(callee_name)
            value = ctx.eval_expr(str(caller_expr))
            child.set(target_ref, value)

        ctx.on_thread("system", "Macro", f"Run macro: {macro_name}", {"tag": "use_macro"})
        execute_steps(child, macro.workflow_alias)

        export_map = inner.get("export", {}) or {}
        for caller_target, callee_ref in export_map.items():
            source_ref = callee_ref if str(callee_ref).startswith(("$", "@")) else "$" + str(callee_ref)
            ctx.set(str(caller_target), child.get(source_ref))
        return

    if "parse_claims" in step:
        inner = step["parse_claims"]
        if isinstance(inner, dict):
            from_expr = inner.get("from", "")
            export = inner.get("export", [])
        else:
            from_expr = str(inner) if inner else ""
            export = step.get("export", [])
        text = str(ctx.eval_expr(from_expr))
        # Determine author from which worker produced the claims
        author = "analyzer"
        for wname, wurl in ctx.workers.items():
            if wname == "analyzer":
                author = f"worker:{wname}"
                break
        entities = _parse_list_from_text(text, "ENTITIES", author=author, policy="worker")
        axioms = _parse_list_from_text(text, "AXIOMS", author=author, policy="worker")
        hypotheses = _parse_list_from_text(text, "HYPOTHESES", author=author, policy="worker")
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
        all_items.extend(item_text(item) for item in items)

        results = []
        for it_text in all_items:
            question = f"\n(({it_text}) == 1) === "
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
            results.append({"text": it_text, "verdict": verdict, "pass": passed})
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


def _atomic_split_statements(text: str) -> list[str]:
    lines = str(text or "").splitlines()
    statements: list[str] = []
    current: list[str] = []
    depth = 0
    triple = False
    for raw in lines:
        line = raw.rstrip()
        stripped = line.strip()
        if not stripped:
            if current:
                current.append(line)
            continue
        if stripped.startswith("#") and not current:
            continue
        current.append(line)
        i = 0
        while i < len(line):
            if line.startswith('"""', i):
                triple = not triple
                i += 3
                continue
            if not triple:
                ch = line[i]
                if ch in "([{":
                    depth += 1
                elif ch in ")]}":
                    depth = max(0, depth - 1)
            i += 1
        if depth == 0 and not triple:
            statements.append("\n".join(current).strip())
            current = []
    if current:
        statements.append("\n".join(current).strip())
    return [stmt for stmt in statements if stmt]


def _atomic_split_args(text: str) -> list[str]:
    args: list[str] = []
    current = ""
    depth = 0
    triple = False
    quote: str | None = None
    i = 0
    while i < len(text):
        if text.startswith('"""', i):
            triple = not triple
            current += '"""'
            i += 3
            continue
        ch = text[i]
        if not triple:
            if quote:
                if ch == quote and (i == 0 or text[i - 1] != "\\"):
                    quote = None
            elif ch in ("'", '"'):
                quote = ch
            elif ch in "([{":
                depth += 1
            elif ch in ")]}":
                depth = max(0, depth - 1)
            elif ch == "," and depth == 0:
                if current.strip():
                    args.append(current.strip())
                current = ""
                i += 1
                continue
        current += ch
        i += 1
    if current.strip():
        args.append(current.strip())
    return args


def _atomic_parse_call(stmt: str) -> tuple[str, list[str]]:
    match = re.match(r"(\w+)\(([\s\S]*)\)$", stmt.strip())
    if not match:
        raise ValueError(f"Unsupported atomic statement: {stmt}")
    return match.group(1), _atomic_split_args(match.group(2))


def _atomic_chat_set(chat: Any, role: str, text: str, append: bool = False) -> dict[str, Any]:
    if not isinstance(chat, dict) or chat.get("_kind") != "chat":
        chat = {"_kind": "chat", "messages": []}
    messages = chat.setdefault("messages", [])
    for msg in messages:
        if msg.get("role") == role:
            msg["content"] = (str(msg.get("content") or "") + text) if append else text
            return chat
    messages.append({"role": role, "content": text})
    return chat


def _atomic_parse_sections(text: str, named: dict[str, str]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    ordered = list(named.items())
    for idx, (name, start_delim) in enumerate(ordered):
        next_delim = ordered[idx + 1][1] if idx + 1 < len(ordered) else None
        start_idx = text.find(start_delim)
        if start_idx < 0:
            result[name] = []
            continue
        start = start_idx + len(start_delim)
        end = text.find(next_delim, start) if next_delim else len(text)
        if end < 0:
            end = len(text)
        section_text = text[start:end].strip()
        result[name] = _parse_list_from_text(
            f"{start_delim}\n{section_text}",
            start_delim.rstrip(":"),
            author="atomic",
            policy="atomic",
        )
    return result


def _atomic_split_text_items(text: Any) -> list[Any]:
    normalized = str(text or "").replace("\r", "").strip()
    if not normalized:
        return []
    numbered = [
        part.strip()
        for part in re.split(r"\n(?=\s*(?:\d+[.)]|[-*•])\s+)", normalized)
        if part.strip()
    ]
    if len(numbered) > 1:
        return [re.sub(r"^\s*(?:\d+[.)]|[-*•])\s+", "", part).strip() for part in numbered if part.strip()]
    blocks = [part.strip() for part in re.split(r"\n\s*\n+", normalized) if part.strip()]
    if len(blocks) > 1:
        return blocks
    return [line.strip() for line in normalized.split("\n") if line.strip()]


def _atomic_to_list(value: Any) -> list[Any]:
    if value is None:
        return []
    if isinstance(value, list):
        return value
    if isinstance(value, tuple):
        return list(value)
    if isinstance(value, dict) and "items" in value and isinstance(value["items"], list):
        return value["items"]
    if isinstance(value, str):
        return _atomic_split_text_items(value)
    return [value]


def _atomic_table_struct(value: Any) -> dict[str, Any] | None:
    if value is None:
        return None
    if isinstance(value, dict) and "headers" in value and "rows" in value:
        return {
            "headers": list(value["headers"]),
            "rows": [list(row) for row in value["rows"]],
        }
    if isinstance(value, list) and value and all(isinstance(row, dict) for row in value):
        headers: list[str] = []
        for row in value:
            for key in row.keys():
                if not str(key).startswith("_") and key not in headers:
                    headers.append(str(key))
        rows = [[str(row.get(h, "")) for h in headers] for row in value]
        return {"headers": headers, "rows": rows}
    if isinstance(value, str):
        rows = _parse_markdown_table(value)
        return _atomic_table_struct(rows)
    return None


def _atomic_boolish(cell: Any) -> bool | None:
    text = str(cell or "").strip().lower()
    if not text:
        return None
    if text in {"yes", "true", "pass", "ok", "1", "y"}:
        return True
    if text in {"no", "false", "fail", "0", "n"}:
        return False
    return None


def _atomic_resolve_column_index(table: dict[str, Any], column: Any, fallback: int = -1) -> int:
    headers = table.get("headers", [])
    if not headers:
        return fallback
    if column is None or column == "":
        return fallback
    if isinstance(column, (int, float)):
        idx = int(column)
        return idx if 0 <= idx < len(headers) else fallback
    normalized = str(column).strip().lower()
    for idx, header in enumerate(headers):
        if str(header).strip().lower() == normalized:
            return idx
    return fallback


def _atomic_resolve_check_indexes(table: dict[str, Any], checks: Any = None) -> list[int]:
    headers = table.get("headers", [])
    rows = table.get("rows", [])
    if not headers:
        return []
    explicit = [str(item).strip().lower() for item in _atomic_to_list(checks)] if checks is not None else []
    normalized_headers = [str(h).strip().lower() for h in headers]
    if explicit:
        return [normalized_headers.index(name) for name in explicit if name in normalized_headers]
    indexes: list[int] = []
    for row in rows:
        for idx, cell in enumerate(row):
            if idx == 0:
                continue
            if _atomic_boolish(cell) is not None and idx not in indexes:
                indexes.append(idx)
    return indexes


def _atomic_infer_label_index(table: dict[str, Any], check_indexes: list[int]) -> int:
    headers = table.get("headers", [])
    blocked = {0, *check_indexes}
    for idx in range(1, len(headers)):
        if idx not in blocked:
            return idx
    return min(1, max(0, len(headers) - 1))


def _atomic_apply_function(ctx: WorkflowContext, fn_name: str, pos_args: list[Any], kw_args: dict[str, Any]) -> Any:
    if fn_name == "generate":
        source = pos_args[0] if pos_args else kw_args.get("input") or kw_args.get("prompt") or ""
        role = str(kw_args.get("worker") or "generator")
        mode = str(kw_args.get("mode") or "prompt")
        no_think = not bool(kw_args.get("think", True))
        temperature = float(kw_args.get("temperature", ctx.settings.get("temperature", 0.6)))
        max_tokens = int(kw_args.get("max_tokens", ctx.settings.get("max_tokens", 2048)))
        stop = kw_args.get("stop")
        grammar = kw_args.get("grammar")
        capture = kw_args.get("capture")
        if isinstance(source, dict) and source.get("_kind") == "chat":
            return ctx.llm_call(
                role,
                messages=source.get("messages", []),
                mode=mode,
                temperature=temperature,
                max_tokens=max_tokens,
                stop=stop if isinstance(stop, list) else ([stop] if stop else None),
                grammar=grammar,
                capture=capture,
                no_think=no_think,
                tag="atomic",
            )
        return ctx.llm_call(
            role,
            prompt=str(source),
            mode=mode,
            temperature=temperature,
            max_tokens=max_tokens,
            stop=stop if isinstance(stop, list) else ([stop] if stop else None),
            grammar=grammar,
            capture=capture,
            no_think=no_think,
            tag="atomic",
        )
    if fn_name == "parse_sections":
        source = str(pos_args[0] if pos_args else "")
        return _atomic_parse_sections(source, {str(k): str(v) for k, v in kw_args.items()})
    if fn_name == "parse_table":
        source = str(pos_args[0] if pos_args else "")
        return _atomic_table_struct(source) or {"headers": [], "rows": []}
    if fn_name == "row_count":
        table = _atomic_table_struct(pos_args[0] if pos_args else None)
        return len(table.get("rows", [])) if table else 0
    if fn_name == "concat":
        result = []
        for item in pos_args:
            if isinstance(item, list):
                result.extend(item)
            else:
                result.append(item)
        return result
    if fn_name == "table_header":
        columns = []
        for item in pos_args:
            columns.extend(str(x) for x in _atomic_to_list(item))
        all_columns = ["#", *columns]
        header = f"| {' | '.join(all_columns)} |"
        sep = "|" + "|".join("---" for _ in all_columns) + "|"
        return {"content": f"{header}\n{sep}", "columns": all_columns}
    if fn_name == "prepend":
        result = []
        for item in pos_args[1:]:
            result.extend(_atomic_to_list(item))
        result.extend(_atomic_to_list(pos_args[0] if pos_args else []))
        return result
    if fn_name == "join":
        seq = pos_args[0] if pos_args else []
        sep = str(kw_args.get("sep", ", "))
        prefix = str(kw_args.get("prefix", ""))
        suffix = str(kw_args.get("suffix", ""))
        return prefix + sep.join(str(x) for x in (seq or [])) + suffix
    if fn_name == "join_list":
        seq = pos_args[0] if pos_args else []
        sep = str(kw_args.get("sep", ", "))
        return sep.join(str(x) for x in _atomic_to_list(seq))
    if fn_name == "len":
        source = pos_args[0] if pos_args else None
        return len(source) if source is not None else 0
    if fn_name == "repeat":
        source = _atomic_to_list(pos_args[0] if pos_args else [])
        count = int(kw_args.get("count", pos_args[1] if len(pos_args) > 1 else 0) or 0)
        result = []
        for _ in range(max(0, count)):
            result.extend(source)
        return result
    if fn_name == "chunk":
        source = _atomic_to_list(pos_args[0] if pos_args else [])
        size = int(kw_args.get("size", pos_args[1] if len(pos_args) > 1 else 1) or 1)
        size = max(1, size)
        return [source[i:i + size] for i in range(0, len(source), size)]
    if fn_name == "reshape_grid":
        source = pos_args[0] if pos_args else []
        items = _atomic_split_text_items(source) if isinstance(source, str) else _atomic_to_list(source)
        cols = int(kw_args.get("cols", kw_args.get("size", pos_args[1] if len(pos_args) > 1 else 1)) or 1)
        cols = max(1, cols)
        return [items[i:i + cols] for i in range(0, len(items), cols)]
    if fn_name == "lines":
        chunks: list[str] = []
        for item in pos_args:
            if isinstance(item, list):
                chunks.extend(str(x) for x in item)
            else:
                chunks.append(str(item))
        return "\n".join(chunks)
    if fn_name == "add":
        return (pos_args[0] if len(pos_args) > 0 else 0) + (pos_args[1] if len(pos_args) > 1 else 0)
    if fn_name == "sub":
        return (pos_args[0] if len(pos_args) > 0 else 0) - (pos_args[1] if len(pos_args) > 1 else 0)
    if fn_name == "eq":
        return str(pos_args[0] if len(pos_args) > 0 else "") == str(pos_args[1] if len(pos_args) > 1 else "")
    if fn_name == "lt":
        return (pos_args[0] if len(pos_args) > 0 else 0) < (pos_args[1] if len(pos_args) > 1 else 0)
    if fn_name == "lte":
        return (pos_args[0] if len(pos_args) > 0 else 0) <= (pos_args[1] if len(pos_args) > 1 else 0)
    if fn_name == "gt":
        return (pos_args[0] if len(pos_args) > 0 else 0) > (pos_args[1] if len(pos_args) > 1 else 0)
    if fn_name == "gte":
        return (pos_args[0] if len(pos_args) > 0 else 0) >= (pos_args[1] if len(pos_args) > 1 else 0)
    if fn_name == "not":
        return not _atomic_truthy(pos_args[0] if pos_args else None)
    if fn_name == "guard":
        return pos_args[1] if len(pos_args) > 1 and _atomic_truthy(pos_args[0]) else None
    if fn_name == "get_column":
        table = _atomic_table_struct(pos_args[0] if pos_args else None)
        if not table:
            return []
        index = _atomic_resolve_column_index(table, pos_args[1] if len(pos_args) > 1 else None, -1)
        if index < 0:
            return []
        return [row[index] if index < len(row) else "" for row in table.get("rows", [])]
    if fn_name == "split_rows":
        table = _atomic_table_struct(pos_args[0] if pos_args else None)
        if not table:
            return {"headers": ["#", "Label", "Row"], "rows": []}
        label_index = _atomic_resolve_column_index(table, pos_args[1] if len(pos_args) > 1 else None, 1)
        rows = []
        for row_index, row in enumerate(table.get("rows", [])):
            label = str(row[label_index] if label_index < len(row) else (row[0] if row else ""))
            detail = "\n".join(
                f"{table['headers'][idx]}: {row[idx] if idx < len(row) else ''}"
                for idx in range(len(table.get("headers", [])))
            )
            rows.append([str(row_index + 1), label, detail])
        return {"headers": ["#", "Label", "Row"], "rows": rows}
    if fn_name == "filter_rows":
        table = _atomic_table_struct(pos_args[0] if pos_args else None)
        if not table:
            return {"headers": [], "rows": []}
        mode = str(kw_args.get("where", kw_args.get("mode", "all_yes"))).strip().lower()
        check_indexes = _atomic_resolve_check_indexes(table, kw_args.get("checks"))
        filtered = []
        for row in table.get("rows", []):
            values = [_atomic_boolish(row[idx]) for idx in (check_indexes or list(range(1, len(row)))) if idx < len(row)]
            comparable = [v for v in values if v is not None]
            if not comparable:
                continue
            keep = all(bool(v) for v in comparable)
            if mode == "any_yes":
                keep = any(bool(v) for v in comparable)
            elif mode == "any_no":
                keep = any(v is False for v in comparable)
            if keep:
                filtered.append(list(row))
        return {"headers": table.get("headers", []), "rows": filtered}
    if fn_name == "reject_reasons":
        table = _atomic_table_struct(pos_args[0] if pos_args else None)
        if not table:
            return {"headers": ["#", "Item", "Reasons"], "rows": []}
        check_indexes = _atomic_resolve_check_indexes(table, kw_args.get("checks"))
        label_index = _atomic_infer_label_index(table, check_indexes)
        rows = []
        for row_index, row in enumerate(table.get("rows", [])):
            failed = [table["headers"][idx] for idx in check_indexes if idx < len(row) and _atomic_boolish(row[idx]) is False]
            if not failed:
                continue
            label = str(row[label_index] if label_index < len(row) else (row[0] if row else f"row_{row_index + 1}"))
            rows.append([str(len(rows) + 1), label, " | ".join(failed)])
        return {"headers": ["#", "Item", "Reasons"], "rows": rows}
    if fn_name == "accepted_list":
        table = _atomic_table_struct(pos_args[0] if pos_args else None)
        if not table:
            return []
        check_indexes = _atomic_resolve_check_indexes(table, kw_args.get("checks"))
        label_index = _atomic_infer_label_index(table, check_indexes)
        accepted = []
        for row in table.get("rows", []):
            values = [_atomic_boolish(row[idx]) for idx in check_indexes if idx < len(row)]
            comparable = [v for v in values if v is not None]
            if comparable and all(comparable):
                accepted.append(str(row[label_index] if label_index < len(row) else (row[0] if row else "")))
        return accepted
    raise ValueError(f"Unsupported atomic function: {fn_name}")


def _atomic_eval_value(ctx: WorkflowContext, expr: str) -> Any:
    expr = str(expr).strip()
    if not expr:
        return ""
    if expr.startswith("@"):
        return ctx.get("$" + expr[1:])
    if expr.startswith("$"):
        return ctx.get(expr)
    if expr.startswith('"""') and expr.endswith('"""'):
        return ctx.interpolate(expr[3:-3])
    if expr.startswith('"') and expr.endswith('"'):
        return ctx.interpolate(expr[1:-1])
    if expr in {"true", "false"}:
        return expr == "true"
    try:
        return int(expr)
    except ValueError:
        pass
    try:
        return float(expr)
    except ValueError:
        pass
    if re.match(r"^\w+\(", expr):
        fn_name, raw_args = _atomic_parse_call(expr)
        pos_args: list[Any] = []
        kw_args: dict[str, Any] = {}
        for arg in raw_args:
            if ":" in arg:
                key, value = arg.split(":", 1)
                if re.match(r"^[A-Za-z_]\w*$", key.strip()):
                    kw_args[key.strip()] = _atomic_eval_value(ctx, value.strip())
                    continue
            pos_args.append(_atomic_eval_value(ctx, arg))
        try:
            return _atomic_apply_function(ctx, fn_name, pos_args, kw_args)
        except ValueError:
            return ctx.eval_expr(expr)
    return ctx.interpolate(expr)


def _atomic_truthy(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return value != 0
    if isinstance(value, list):
        return len(value) > 0
    if value is None:
        return False
    text = str(value).strip().lower()
    if not text:
        return False
    return text not in {"false", "0", "no", "fail", "pending", "none", "null"}


def _atomic_has_value(ctx: WorkflowContext, ref: str) -> bool:
    ref = str(ref).strip()
    if ref.startswith("@"):
        value = ctx.get("$" + ref[1:])
    else:
        value = ctx.get(ref)
    return value is not None


def _atomic_parse_loop(stmt: str) -> tuple[str, int, str]:
    match = re.match(r"loop\(([\s\S]*?)\)\s*\{([\s\S]*)\}\s*$", stmt.strip())
    if not match:
        raise ValueError(f"Invalid atomic loop block: {stmt}")
    header = match.group(1)
    body = match.group(2).strip()
    while_expr = ""
    max_iters = 8
    for part in _atomic_split_args(header):
        if ":" not in part:
            continue
        key, value = part.split(":", 1)
        key = key.strip()
        value = value.strip()
        if key == "while":
            while_expr = value
        elif key == "max_iters":
            max_iters = int(_coerce_intlike(value, 8))
    if not while_expr:
        raise ValueError("atomic loop requires while: condition")
    return while_expr, max_iters, body


def _atomic_parse_on(stmt: str) -> tuple[list[str], str]:
    match = re.match(r"on\s+(.+?)\s*->\s*([\s\S]+)$", stmt.strip())
    if not match:
        raise ValueError(f"Invalid atomic reactive statement: {stmt}")
    deps = [part.strip() for part in match.group(1).split(",") if part.strip()]
    action = match.group(2).strip()
    return deps, action


def _run_atomic_dsl(ctx: WorkflowContext, dsl_text: str) -> None:
    watchers: list[dict[str, Any]] = []

    def flush_watchers() -> None:
        guard = max(1, len(watchers) * 4 + 4)
        passes = 0
        while passes < guard:
            passes += 1
            fired = False
            for watcher in watchers:
                if watcher.get("fired"):
                    continue
                if all(_atomic_has_value(ctx, dep) for dep in watcher["deps"]):
                    watcher["fired"] = True
                    _run_atomic_dsl(ctx, watcher["action"])
                    fired = True
            if not fired:
                break

    for stmt in _atomic_split_statements(dsl_text):
        if stmt.startswith("on "):
            deps, action = _atomic_parse_on(stmt)
            watchers.append({"deps": deps, "action": action, "fired": False})
            flush_watchers()
            continue
        if stmt.startswith("loop("):
            while_expr, max_iters, body = _atomic_parse_loop(stmt)
            iterations = 0
            while _atomic_truthy(_atomic_eval_value(ctx, while_expr)):
                if iterations >= max_iters:
                    raise ValueError(f"atomic loop iteration limit reached ({max_iters})")
                _run_atomic_dsl(ctx, body)
                iterations += 1
            flush_watchers()
            continue

        is_assignment = "=" in stmt and not stmt.lstrip().startswith(("set_text(", "append_text(", "tag(", "untag("))
        if is_assignment:
            left, right = stmt.split("=", 1)
            target = left.strip()
            expr = right.strip()

            if re.match(r"^\w+\(", expr):
                fn_name, raw_args = _atomic_parse_call(expr)
                pos_args: list[Any] = []
                kw_args: dict[str, Any] = {}
                for arg in raw_args:
                    if ":" in arg:
                        key, value = arg.split(":", 1)
                        if re.match(r"^[A-Za-z_]\w*$", key.strip()):
                            kw_args[key.strip()] = _atomic_eval_value(ctx, value.strip())
                            continue
                    pos_args.append(_atomic_eval_value(ctx, arg))

                try:
                    result = _atomic_apply_function(ctx, fn_name, pos_args, kw_args)
                except ValueError:
                    result = ctx.eval_expr(expr)

                store_ref = target if target.startswith("$") else "$" + target.lstrip("@")
                ctx.set(store_ref, result)
                flush_watchers()
                continue

            store_ref = target if target.startswith("$") else "$" + target.lstrip("@")
            ctx.set(store_ref, _atomic_eval_value(ctx, expr))
            flush_watchers()
            continue

        fn_name, raw_args = _atomic_parse_call(stmt)
        pos_args = [_atomic_eval_value(ctx, arg) for arg in raw_args]
        if fn_name == "set_text":
            ref = str(raw_args[0]).strip()
            name = ref.lstrip("@$")
            role = str(pos_args[1])
            text = str(pos_args[2])
            ctx.set("$" + name, _atomic_chat_set(ctx.get("$" + name), role, text, append=False))
            flush_watchers()
        elif fn_name == "append_text":
            ref = str(raw_args[0]).strip()
            name = ref.lstrip("@$")
            role = str(pos_args[1])
            text = str(pos_args[2])
            ctx.set("$" + name, _atomic_chat_set(ctx.get("$" + name), role, text, append=True))
            flush_watchers()
        elif fn_name in {"tag", "untag"}:
            continue
        else:
            raise ValueError(f"Unsupported atomic statement: {stmt}")


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

    default_builtins = build_default_builtins(builtins)

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
        # Strip markdown formatting and extract core name for matching
        clean_title = re.sub(r'\*+', '', title).strip()  # remove ** bold
        clean_title = re.sub(r'^\d+\.\s*', '', clean_title).strip()  # remove "1. " prefix
        clean_title = clean_title.split('(')[0].strip()  # remove "(english name)" suffix
        clean_title = clean_title.strip('«»""\':').strip()  # remove quotes
        title_lower = clean_title.lower() if clean_title else title.lower().strip()
        found = False
        for i, line in enumerate(lines):
            if title_lower in line.lower():
                entity["_startNum"] = i + 1  # 1-based
                entity["_firstLine"] = line.strip()
                found = True
                break
        if not found:
            # Fallback: default to line 1
            entity.setdefault("_startNum", 1)
            entity.setdefault("_firstLine", lines[0].strip() if lines else "")
            import logging
            logging.warning(f"enrich_entities: title '{title_lower}' not found in answer ({len(lines)} lines)")
    return entities


def _slice_lines(text: Any, start: Any, end: Any) -> str:
    lines = str(text).split("\n")
    start_idx = max(0, _coerce_intlike(start, 1) - 1)
    end_idx = min(len(lines), _coerce_intlike(end, len(lines)))
    if end_idx < start_idx + 1:
        end_idx = start_idx + 1
    return "\n".join(lines[start_idx:end_idx]).strip()


def make_item(text: str, author: str = "system", policy: str = "system") -> dict:
    """Create a structured item with metadata."""
    from datetime import datetime
    return {
        "text": text,
        "author": author,
        "policy": policy,
        "ts": datetime.now().isoformat(),
    }


def item_text(item) -> str:
    """Extract text from item (handles both str and dict formats)."""
    if isinstance(item, dict):
        return item.get("text", item.get("_value", str(item)))
    return str(item)


def _parse_list_from_text(text: str, section: str, author: str = "system", policy: str = "system") -> list[dict]:
    """Parse ENTITIES/AXIOMS/HYPOTHESES from claims text. Returns structured items."""
    lines = text.split("\n")
    raw_items = []
    in_section = False
    for line in lines:
        trimmed = line.strip()
        if trimmed.upper().startswith(section.upper() + ":"):
            in_section = True
            after = trimmed[len(section) + 1:].strip()
            if after.startswith("["):
                inner = after.strip("[]")
                raw_items.extend(s.strip() for s in inner.split(",") if s.strip())
                in_section = False
            continue
        if in_section and re.match(r"^[A-Z_]+:", trimmed):
            in_section = False
            continue
        if in_section and trimmed.startswith("-"):
            raw_items.append(trimmed[1:].strip())
    return [make_item(t, author=author, policy=policy) for t in raw_items]


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
            # Use second column as title if first is numeric (e.g. row number)
            if len(cells) >= 2 and re.match(r"^\d+$", cells[0].strip()):
                row["_title"] = cells[1]
            else:
                row["_title"] = cells[0] if cells else ""
            row["_index"] = len(rows)
            rows.append(row)
    return rows
