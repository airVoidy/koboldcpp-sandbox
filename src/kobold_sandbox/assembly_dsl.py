"""Assembly DSL Interpreter v0.2.

Flat instruction set for Atomic pipelines.
10 opcodes: MOV, GEN, PUT, PARSE, CALL, CMP, JIF, LOOP, EACH, NOP.

Reuses WorkflowContext and existing transform functions from workflow_dsl.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any, Callable

from .workflow_dsl import (
    WorkflowContext,
    _atomic_apply_function,
    _atomic_chat_set,
    _atomic_eval_value,
    _atomic_parse_sections,
    _atomic_table_struct,
    _atomic_to_list,
    _atomic_split_text_items,
)


# ---------------------------------------------------------------------------
# Tokeniser: line → Instruction
# ---------------------------------------------------------------------------

@dataclass
class Instruction:
    opcode: str          # MOV, GEN, PUT, PUT+, PARSE, CALL, CMP, JIF, LOOP, EACH
    args: list[str]      # raw string tokens
    flags: dict[str, str] # key:value pairs
    line: int = 0        # source line number
    raw: str = ""        # original text


@dataclass
class AsmFunction:
    name: str
    params: list[str]     # ["@chat", "$prompt", ...]
    outputs: list[str]    # ["@draft", "@constraints", ...]
    instructions: list[Instruction]


@dataclass
class AsmResult:
    state: dict[str, Any]
    log: list[dict[str, Any]]
    error: str | None = None


# Regex for flag:value tokens
_FLAG_RE = re.compile(r'^([A-Za-z_]\w*):(.+)$')


def _tokenise_line(raw: str) -> Instruction | None:
    """Parse one assembly line into an Instruction."""
    line = raw.strip()
    # Strip comments
    if ";" in line:
        # Handle semicolons inside quoted strings
        in_quote = False
        quote_char = None
        for i, ch in enumerate(line):
            if ch in ('"', "'") and not in_quote:
                in_quote = True
                quote_char = ch
            elif ch == quote_char and in_quote:
                in_quote = False
            elif ch == ";" and not in_quote:
                line = line[:i].rstrip()
                break

    if not line:
        return None

    # Split opcode from rest
    parts = line.split(None, 1)
    opcode = parts[0].upper()
    rest = parts[1] if len(parts) > 1 else ""

    # Split args by comma, respecting quotes
    tokens = _split_asm_args(rest)

    args: list[str] = []
    flags: dict[str, str] = {}
    for tok in tokens:
        m = _FLAG_RE.match(tok)
        if m:
            flags[m.group(1)] = m.group(2)
        else:
            args.append(tok)

    return Instruction(opcode=opcode, args=args, flags=flags, raw=raw)


def _split_asm_args(text: str) -> list[str]:
    """Split comma-separated args, respecting quotes and backslash escapes."""
    args: list[str] = []
    current = ""
    depth = 0
    quote: str | None = None
    escaped = False

    for ch in text:
        if escaped:
            current += ch
            escaped = False
            continue
        if ch == "\\" and quote:
            # Backslash inside quotes: escape next char
            current += ch
            escaped = True
            continue
        if quote:
            current += ch
            if ch == quote:
                quote = None
            continue
        if ch in ('"', "'"):
            quote = ch
            current += ch
            continue
        if ch in "([{":
            depth += 1
            current += ch
            continue
        if ch in ")]}":
            depth = max(0, depth - 1)
            current += ch
            continue
        if ch == "," and depth == 0:
            if current.strip():
                args.append(current.strip())
            current = ""
            continue
        current += ch

    if current.strip():
        args.append(current.strip())
    return args


def _resolve_labels(instructions: list[Instruction]) -> list[Instruction]:
    """Resolve :label references in JIF/LOOP args to +N offsets."""
    # First pass: collect label positions
    labels: dict[str, int] = {}
    real_instructions: list[Instruction] = []
    for inst in instructions:
        if inst.opcode == "LABEL":
            # Label pseudo-instruction: store position
            label_name = inst.args[0] if inst.args else ""
            labels[label_name] = len(real_instructions)
        else:
            real_instructions.append(inst)

    # Second pass: resolve :label refs in JIF/LOOP/EACH args
    for ip, inst in enumerate(real_instructions):
        if inst.opcode in ("JIF", "LOOP", "EACH"):
            new_args = []
            for arg in inst.args:
                if arg.startswith(":"):
                    label = arg[1:]  # strip ':'
                    if label in labels:
                        target_ip = labels[label]
                        offset = target_ip - ip - 1  # relative jump (body length)
                        new_args.append(f"{offset:+d}" if offset < 0 else f"+{offset}")
                    else:
                        new_args.append(arg)  # leave unresolved
                else:
                    new_args.append(arg)
            inst.args = new_args

    return real_instructions


def parse_program(text: str) -> tuple[list[Instruction], dict[str, AsmFunction]]:
    """Parse assembly text into instruction list and function table."""
    lines = text.splitlines()
    instructions: list[Instruction] = []
    functions: dict[str, AsmFunction] = {}

    i = 0
    while i < len(lines):
        raw = lines[i]
        stripped = raw.strip()

        # Skip empty / comment lines
        if not stripped or stripped.startswith(";") or stripped.startswith("#"):
            i += 1
            continue

        # Label definition :name
        if stripped.startswith(":") and not stripped.startswith("::"):
            label_name = stripped[1:].strip()
            inst = Instruction(opcode="LABEL", args=[label_name], flags={}, line=i + 1, raw=stripped)
            instructions.append(inst)
            i += 1
            continue

        # fn declaration
        if stripped.startswith("fn "):
            fn_def, fn_instrs, consumed = _parse_fn_block(lines, i)
            # Resolve labels within fn body
            fn_def.instructions = _resolve_labels(fn_def.instructions)
            functions[fn_def.name] = fn_def
            i += consumed
            continue

        inst = _tokenise_line(stripped)
        if inst:
            inst.line = i + 1
            instructions.append(inst)
        i += 1

    # Resolve labels in main program
    instructions = _resolve_labels(instructions)

    return instructions, functions


def _parse_fn_block(lines: list[str], start: int) -> tuple[AsmFunction, list[Instruction], int]:
    """Parse a fn ... : block starting at line index."""
    header = lines[start].strip()
    # fn name(params) -> outputs:
    m = re.match(r'fn\s+(\w+)\(([^)]*)\)(?:\s*->\s*([^:]+))?\s*:', header)
    if not m:
        raise SyntaxError(f"Bad fn declaration at line {start + 1}: {header}")

    name = m.group(1)
    params = [p.strip() for p in m.group(2).split(",") if p.strip()] if m.group(2) else []
    outputs = [o.strip() for o in m.group(3).split(",") if o.strip()] if m.group(3) else []

    fn_instrs: list[Instruction] = []
    consumed = 1  # header line
    i = start + 1
    while i < len(lines):
        raw = lines[i]
        # Body lines must be indented
        if raw and not raw[0].isspace():
            break
        stripped = raw.strip()
        if stripped and not stripped.startswith(";") and not stripped.startswith("#"):
            # Label in fn body
            if stripped.startswith(":") and not stripped.startswith("::"):
                label_name = stripped[1:].strip()
                inst = Instruction(opcode="LABEL", args=[label_name], flags={}, line=i + 1, raw=stripped)
                fn_instrs.append(inst)
            else:
                inst = _tokenise_line(stripped)
                if inst:
                    inst.line = i + 1
                    fn_instrs.append(inst)
        consumed += 1
        i += 1

    # Resolve labels within fn body
    fn_instrs = _resolve_labels(fn_instrs)

    return AsmFunction(name=name, params=params, outputs=outputs, instructions=fn_instrs), fn_instrs, consumed


# ---------------------------------------------------------------------------
# Ref resolution (assembly-style: @ → state, $ → config/vars)
# ---------------------------------------------------------------------------

def _asm_resolve(ctx: WorkflowContext, token: str) -> Any:
    """Resolve an assembly token to a value."""
    token = token.strip()

    # Quoted string literal
    if len(token) >= 2 and token[0] == token[-1] and token[0] in ('"', "'"):
        inner = token[1:-1]
        # Process escape sequences
        inner = inner.replace("\\n", "\n").replace("\\t", "\t").replace('\\"', '"').replace("\\'", "'")
        return inner

    # Boolean
    if token == "true":
        return True
    if token == "false":
        return False

    # Ref
    if token.startswith("@") or token.startswith("$"):
        value = _atomic_eval_value(ctx, token)
        # Implicit await: if value is a Future, block until ready and cache
        from concurrent.futures import Future
        if isinstance(value, Future):
            resolved = value.result()
            _asm_store(ctx, token, resolved)
            return resolved
        return value

    # Numeric
    try:
        return int(token)
    except ValueError:
        pass
    try:
        return float(token)
    except ValueError:
        pass

    # Offset like +3
    if token.startswith("+") and token[1:].isdigit():
        return int(token)

    return token


def _asm_store(ctx: WorkflowContext, ref: str, value: Any) -> None:
    """Store a value into a register ref."""
    ref = ref.strip()
    if ref.startswith("@"):
        # Store in state as $name (workflow_dsl convention: @ maps to $ internally)
        store_ref = "$" + ref[1:]
    elif ref.startswith("$"):
        store_ref = ref
    else:
        store_ref = "$" + ref
    ctx.set(store_ref, value)


def _asm_get(ctx: WorkflowContext, ref: str) -> Any:
    """Get a value from a register ref."""
    from concurrent.futures import Future
    ref = ref.strip()
    if ref.startswith("@"):
        value = ctx.get("$" + ref[1:])
        if isinstance(value, Future):
            resolved = value.result()
            _asm_store(ctx, ref, resolved)
            return resolved
        return value
    return _atomic_eval_value(ctx, ref)


# ---------------------------------------------------------------------------
# Instruction executors
# ---------------------------------------------------------------------------

def _exec_mov(ctx: WorkflowContext, inst: Instruction) -> dict:
    """MOV dst, src"""
    dst = inst.args[0]
    src = inst.args[1] if len(inst.args) > 1 else ""
    value = _asm_resolve(ctx, src)
    _asm_store(ctx, dst, value)
    return {"op": "MOV", "dst": dst, "src": src, "value": _short_repr(value),
            "input_preview": _short_repr(value), "output_preview": _short_repr(value),
            "input_full": _full_repr(value), "output_full": _full_repr(value)}


def _exec_gen(ctx: WorkflowContext, inst: Instruction) -> dict:
    """GEN dst, src [, flags]

    Flags include mode, worker, temp, max, grammar, capture, coerce, stop, think, input.
    When mode=probe and capture/coerce are set, the raw result is cleaned/extracted.
    """
    dst = inst.args[0]
    src = inst.args[1] if len(inst.args) > 1 else ""

    source = _asm_resolve(ctx, src)

    # Map flag names to _atomic_apply_function kw_args
    kw: dict[str, Any] = {}
    flag_map = {
        "mode": "mode", "worker": "worker", "temp": "temperature",
        "temperature": "temperature", "max": "max_tokens", "max_tokens": "max_tokens",
        "think": "think", "stop": "stop", "cap": "capture", "capture": "capture",
        "grammar": "grammar", "input": "input", "coerce": "coerce",
    }
    for k, v in inst.flags.items():
        mapped = flag_map.get(k, k)
        resolved = _asm_resolve(ctx, v)
        kw[mapped] = resolved

    # Extract coerce before passing to generate (it's not a generate kwarg)
    coerce_type = kw.pop("coerce", None)

    mode = kw.get("mode", "prompt")
    is_probe = mode in ("probe", "probe_continue")
    worker_role = kw.get("worker", "generator")

    if is_probe:
        # Probe: synchronous (single-shot, need result immediately)
        result = _atomic_apply_function(ctx, "generate", [source], kw)

        # Post-process probe results with capture/coerce
        if kw.get("capture") or coerce_type:
            from .workflow_dsl import _clean_probe_result
            capture = kw.get("capture")
            cap_dict: dict[str, Any] = {}
            if isinstance(capture, str):
                cap_dict["regex"] = capture
            elif isinstance(capture, dict):
                cap_dict = dict(capture)
            if coerce_type:
                cap_dict["coerce"] = str(coerce_type)
            result = _clean_probe_result(str(result), kw.get("grammar"), cap_dict or None)
            if coerce_type == "int" or str(coerce_type) == "int":
                try:
                    result = int(result)
                except (ValueError, TypeError):
                    result = 0
            elif coerce_type == "float" or str(coerce_type) == "float":
                try:
                    result = float(result)
                except (ValueError, TypeError):
                    result = 0.0

        _asm_store(ctx, dst, result)
        return {"op": "GEN", "dst": dst, "worker": worker_role, "mode": mode,
                "input_preview": _short_repr(source), "output_preview": _short_repr(result),
                "input_full": _full_repr(source), "output_full": _full_repr(result)}

    # Non-probe: async — submit to worker thread pool and continue
    url = ctx.workers.get(worker_role, "").rstrip("/")

    # Capture kw snapshot for the thread (avoid mutation issues)
    kw_snapshot = dict(kw)
    source_snapshot = source

    future = ctx.submit_gen(url, _atomic_apply_function, ctx, "generate", [source_snapshot], kw_snapshot)
    _asm_store(ctx, dst, future)  # store Future — implicit await on first read

    return {"op": "GEN", "dst": dst, "worker": worker_role, "mode": mode,
            "async": True,
            "input_preview": _short_repr(source), "output_preview": "(async pending)",
            "input_full": _full_repr(source), "output_full": "(async pending)"}


def _exec_put(ctx: WorkflowContext, inst: Instruction, append: bool = False) -> dict:
    """PUT target, role, value  /  PUT+ target, role, value"""
    target_ref = inst.args[0]
    role = _asm_resolve(ctx, inst.args[1]) if len(inst.args) > 1 else "user"
    value = _asm_resolve(ctx, inst.args[2]) if len(inst.args) > 2 else ""

    name = target_ref.lstrip("@$")
    current = ctx.get("$" + name)
    updated = _atomic_chat_set(current, str(role), str(value), append=append)
    ctx.set("$" + name, updated)
    op_name = "PUT+" if append else "PUT"
    return {"op": op_name, "target": target_ref, "role": str(role),
            "input_preview": _short_repr(value), "output_preview": f"{role}: {_short_repr(value)}",
            "input_full": _full_repr(value), "output_full": f"{role}: {_full_repr(value)}"}


def _exec_parse(ctx: WorkflowContext, inst: Instruction) -> dict:
    """PARSE dst, src, pattern_flag"""
    dst = inst.args[0]
    src = _asm_resolve(ctx, inst.args[1]) if len(inst.args) > 1 else ""
    text = str(src)

    if "sections" in inst.flags:
        # sections:"ENTITIES:|AXIOMS:|HYPOTHESES:"
        raw_sections = str(inst.flags["sections"]).strip('"').strip("'")
        labels = [l.strip() for l in raw_sections.split("|") if l.strip()]
        named = {}
        for label in labels:
            name = label.rstrip(":").strip().lower()
            named[name] = label
        result = _atomic_parse_sections(text, named)

    elif "split" in inst.flags:
        delimiter = str(_asm_resolve(ctx, inst.flags["split"]))
        result = text.split(delimiter) if delimiter else text.split()

    elif "table" in inst.flags:
        result = _atomic_table_struct(text) or {"headers": [], "rows": []}

    elif "regex" in inst.flags:
        pattern = str(inst.flags["regex"]).strip('"').strip("'")
        m = re.search(pattern, text)
        result = m.group(0) if m else ""
        if "coerce" in inst.flags:
            coerce_type = str(inst.flags["coerce"]).strip('"').strip("'")
            if coerce_type == "int":
                try:
                    result = int(result)
                except (ValueError, TypeError):
                    result = 0
            elif coerce_type == "float":
                try:
                    result = float(result)
                except (ValueError, TypeError):
                    result = 0.0

    elif "from" in inst.flags or "to" in inst.flags:
        from_marker = str(inst.flags.get("from", "")).strip('"').strip("'")
        to_marker = str(inst.flags.get("to", "")).strip('"').strip("'")
        start_idx = text.find(from_marker) if from_marker else 0
        if start_idx >= 0 and from_marker:
            start_idx += len(from_marker)
        end_idx = text.find(to_marker, max(0, start_idx)) if to_marker else len(text)
        if end_idx < 0:
            end_idx = len(text)
        result = text[max(0, start_idx):end_idx].strip()

    else:
        # Positional pattern arg
        pattern_arg = inst.args[2] if len(inst.args) > 2 else ""
        result = text  # fallback

    _asm_store(ctx, dst, result)
    return {"op": "PARSE", "dst": dst,
            "input_preview": _short_repr(text), "output_preview": _short_repr(result),
            "input_full": _full_repr(text), "output_full": _full_repr(result)}


def _exec_call(ctx: WorkflowContext, inst: Instruction, functions: dict[str, AsmFunction]) -> dict:
    """CALL dst, fn_name, args... [, flags...]"""
    dst = inst.args[0]
    fn_name = inst.args[1] if len(inst.args) > 1 else ""
    raw_args = inst.args[2:]

    resolved_args = [_asm_resolve(ctx, a) for a in raw_args]
    args_preview = ", ".join(_short_repr(a) for a in resolved_args[:3])
    args_full = ", ".join(_full_repr(a) for a in resolved_args[:3])

    def _call_result(result):
        return {"op": "CALL", "fn": fn_name, "dst": dst,
                "input_preview": args_preview, "output_preview": _short_repr(result),
                "input_full": args_full, "output_full": _full_repr(result)}

    # Check user-defined assembly functions first
    if fn_name in functions:
        fn_def = functions[fn_name]
        result = _exec_asm_function(ctx, fn_def, raw_args, inst.flags)
        _asm_store(ctx, dst, result)
        return _call_result(result)

    # Check Python-registered functions
    if fn_name in _PYTHON_FUNCTIONS:
        py_fn = _PYTHON_FUNCTIONS[fn_name]
        result = py_fn.handler(ctx, resolved_args, inst.flags)
        _asm_store(ctx, dst, result)
        return _call_result(result)

    # Fall through to existing atomic transforms
    kw_args = {k: _asm_resolve(ctx, v) for k, v in inst.flags.items()}

    result = _atomic_apply_function(ctx, fn_name, resolved_args, kw_args)
    _asm_store(ctx, dst, result)
    return _call_result(result)


def _exec_cmp(ctx: WorkflowContext, inst: Instruction) -> dict:
    """CMP dst, op, a, b"""
    dst = inst.args[0]
    op = inst.args[1] if len(inst.args) > 1 else "eq"
    a = _asm_resolve(ctx, inst.args[2]) if len(inst.args) > 2 else None
    b = _asm_resolve(ctx, inst.args[3]) if len(inst.args) > 3 else None

    ops = {
        "eq": lambda x, y: x == y,
        "ne": lambda x, y: x != y,
        "lt": lambda x, y: x < y,
        "lte": lambda x, y: x <= y,
        "gt": lambda x, y: x > y,
        "gte": lambda x, y: x >= y,
    }
    fn = ops.get(op)
    if fn is None:
        raise ValueError(f"Unknown CMP operator: {op}")

    try:
        result = fn(a, b)
    except TypeError:
        result = False

    _asm_store(ctx, dst, result)
    return {"op": "CMP", "dst": dst, "cmp": op, "result": result,
            "input_preview": f"{_short_repr(a)} {op} {_short_repr(b)}",
            "output_preview": str(result),
            "input_full": f"{_full_repr(a)} {op} {_full_repr(b)}",
            "output_full": str(result)}


def _short_repr(value: Any) -> str:
    """Short string repr for logging."""
    s = str(value)
    return s[:80] + "..." if len(s) > 80 else s


def _full_repr(value: Any) -> str:
    """Full string repr for UI expansion (capped at 4000)."""
    s = str(value)
    return s[:4000] + "..." if len(s) > 4000 else s


# ---------------------------------------------------------------------------
# Assembly function execution
# ---------------------------------------------------------------------------

def _exec_asm_function(ctx: WorkflowContext, fn_def: AsmFunction, raw_args: list[str], flags: dict[str, str]) -> Any:
    """Execute a DSL-defined assembly function."""
    child = ctx.child()

    # Bind params
    for i, param in enumerate(fn_def.params):
        if i < len(raw_args):
            value = _asm_resolve(ctx, raw_args[i])
        else:
            value = None
        _asm_store(child, param, value)

    # Run body
    _run_instructions(child, fn_def.instructions, {})

    # Collect outputs
    if len(fn_def.outputs) == 1:
        return _asm_get(child, fn_def.outputs[0])
    if len(fn_def.outputs) > 1:
        # Return dict of outputs
        result = {}
        for out in fn_def.outputs:
            name = out.lstrip("@$")
            result[name] = _asm_get(child, out)
        return result
    return None


# ---------------------------------------------------------------------------
# Python function registry
# ---------------------------------------------------------------------------

@dataclass
class PythonAsmFunction:
    name: str
    params: list[str]
    outputs: list[str]
    handler: Callable


_PYTHON_FUNCTIONS: dict[str, PythonAsmFunction] = {}


def asm_function(name: str, params: list[str] | None = None, outputs: list[str] | None = None):
    """Decorator to register a Python function as an assembly-callable function."""
    def decorator(fn: Callable) -> Callable:
        _PYTHON_FUNCTIONS[name] = PythonAsmFunction(
            name=name,
            params=params or [],
            outputs=outputs or [],
            handler=fn,
        )
        return fn
    return decorator


# ---------------------------------------------------------------------------
# Main execution engine
# ---------------------------------------------------------------------------

def _run_instructions(ctx: WorkflowContext, instructions: list[Instruction], functions: dict[str, AsmFunction]) -> list[dict]:
    """Execute a list of assembly instructions with instruction pointer."""
    log: list[dict] = []
    ip = 0  # instruction pointer
    max_total = len(instructions) * 100  # safety bound
    steps = 0

    while ip < len(instructions) and steps < max_total:
        steps += 1
        inst = instructions[ip]
        entry = {"ip": ip, "line": inst.line, "op": inst.opcode, "status": "running"}
        log.append(entry)

        try:
            if inst.opcode == "MOV":
                detail = _exec_mov(ctx, inst)
                entry.update(detail)
                ip += 1

            elif inst.opcode == "GEN":
                detail = _exec_gen(ctx, inst)
                entry.update(detail)
                ip += 1

            elif inst.opcode in ("PUT", "PUT+"):
                detail = _exec_put(ctx, inst, append=(inst.opcode == "PUT+"))
                entry.update(detail)
                ip += 1

            elif inst.opcode == "PARSE":
                detail = _exec_parse(ctx, inst)
                entry.update(detail)
                ip += 1

            elif inst.opcode == "CALL":
                detail = _exec_call(ctx, inst, functions)
                entry.update(detail)
                ip += 1

            elif inst.opcode == "CMP":
                detail = _exec_cmp(ctx, inst)
                entry.update(detail)
                ip += 1

            elif inst.opcode == "JIF":
                cond_ref = inst.args[0] if inst.args else ""
                offset_str = inst.args[1] if len(inst.args) > 1 else "+0"
                offset = int(str(offset_str).lstrip("+"))

                cond = _asm_resolve(ctx, cond_ref)
                if cond:
                    ip += offset + 1  # skip N lines + advance past JIF
                    entry.update({"op": "JIF", "cond": bool(cond), "skip": offset})
                else:
                    ip += 1
                    entry.update({"op": "JIF", "cond": False, "skip": 0})

            elif inst.opcode == "LOOP":
                cond_ref = inst.args[0] if inst.args else ""
                max_iters = int(inst.args[1]) if len(inst.args) > 1 else 8
                body_len_str = inst.args[2] if len(inst.args) > 2 else "+1"
                body_len = int(str(body_len_str).lstrip("+"))

                body_start = ip + 1
                body_end = min(body_start + body_len, len(instructions))
                body = instructions[body_start:body_end]

                iterations = 0
                while iterations < max_iters:
                    cond = _asm_resolve(ctx, cond_ref)
                    if not cond:
                        break
                    body_log = _run_instructions(ctx, body, functions)
                    log.extend(body_log)
                    iterations += 1

                entry.update({"op": "LOOP", "iterations": iterations, "body_len": body_len})
                ip = body_end  # jump past body

            elif inst.opcode == "EACH":
                # EACH @item, @collection, +body_len
                item_ref = inst.args[0] if inst.args else "@_item"
                coll_ref = inst.args[1] if len(inst.args) > 1 else ""
                body_len_str = inst.args[2] if len(inst.args) > 2 else "+1"
                body_len = int(str(body_len_str).lstrip("+"))

                collection = _asm_resolve(ctx, coll_ref)
                if not isinstance(collection, list):
                    collection = _atomic_to_list(collection)

                body_start = ip + 1
                body_end = min(body_start + body_len, len(instructions))
                body = instructions[body_start:body_end]

                # Store iteration index in a separate well-known ref
                idx_ref = "$_each_idx"
                for idx, item in enumerate(collection):
                    _asm_store(ctx, item_ref, item)
                    ctx.vars["_each_idx"] = idx
                    # Set _index on dict items only (don't corrupt primitives)
                    if isinstance(item, dict):
                        item["_index"] = idx
                    # Derive a human-readable label for this iteration
                    if isinstance(item, dict):
                        item_label = item.get("_title", item.get("name", item.get("title", f"#{idx}")))
                    else:
                        item_label = _short_repr(item)
                    body_log = _run_instructions(ctx, body, functions)
                    # Annotate each body entry with iteration context
                    for bl_entry in body_log:
                        bl_entry["each_idx"] = idx
                        bl_entry["each_total"] = len(collection)
                        bl_entry["each_item"] = str(item_label)
                    log.extend(body_log)
                    # Write back: if body modified @item fields, update collection
                    updated = _asm_resolve(ctx, item_ref)
                    if isinstance(updated, dict):
                        collection[idx] = updated

                entry.update({"op": "EACH", "iterations": len(collection), "body_len": body_len})
                ip = body_end  # jump past body

            elif inst.opcode == "NOP":
                ip += 1

            else:
                raise ValueError(f"Unknown opcode: {inst.opcode}")

            entry["status"] = "done"

        except Exception as exc:
            entry["status"] = "error"
            entry["error"] = str(exc)
            raise

    return log


def load_library_functions(pages: list[dict[str, Any]] | None = None) -> dict[str, AsmFunction]:
    """Load fn definitions from wiki function_page entries.

    Each page should have a block with Assembly fn source code.
    Returns dict of function name → AsmFunction ready for execute().
    """
    functions: dict[str, AsmFunction] = {}
    if not pages:
        return functions
    for page in pages:
        blocks = page.get("blocks", [])
        for block in blocks:
            text = block.get("text", "")
            if not text or "fn " not in text:
                continue
            try:
                _, fns = parse_program(text)
                functions.update(fns)
            except Exception:
                pass  # skip malformed fn definitions
    return functions


_builtins_registered = False


def _ensure_builtins() -> None:
    global _builtins_registered
    if not _builtins_registered:
        from .dsl_builtins import register_dsl_builtins
        register_dsl_builtins()
        _builtins_registered = True


def execute(
    code: str,
    ctx: WorkflowContext,
    extra_functions: dict[str, AsmFunction] | None = None,
) -> AsmResult:
    """Parse and execute assembly DSL code."""
    _ensure_builtins()
    try:
        instructions, functions = parse_program(code)
        if extra_functions:
            functions.update(extra_functions)

        log = _run_instructions(ctx, instructions, functions)

        # Export state (@ registers → flat dict), resolving any pending Futures
        from concurrent.futures import Future
        state = {}
        for key, value in ctx.vars.items():
            if isinstance(value, Future):
                try:
                    value = value.result(timeout=60)
                except Exception:
                    value = None
            state[key] = value

        return AsmResult(state=state, log=log, error=None)

    except Exception as exc:
        return AsmResult(state={}, log=[], error=str(exc))
