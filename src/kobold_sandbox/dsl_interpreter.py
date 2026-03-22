"""Behavior Tree Element Handler DSL Interpreter v2.

Namespace conventions:
    $x      — element-local runtime variable
    @x      — node.data.x (persistent)
    @@x     — tree.global_meta.x
    #x      — reserved runtime values

Template strings: "Style: {$@style}. Hair: {$@hair_color}. Temp var: {$$prompt}"

Commands (inside meta.do list):
    set, copy, save, render, call, outcome, return,
    if, for_each, append, claims, run_node, collect, finalize_claims
"""
from __future__ import annotations

import json
import re
import threading
from dataclasses import dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING, Any, Callable

if TYPE_CHECKING:
    from .behavior_orchestrator import (
        BehaviorElement,
        BehaviorNode,
        BehaviorTree,
        BehaviorOrchestrator,
        ElementExecutionResult,
    )


# ---------------------------------------------------------------------------
# Context
# ---------------------------------------------------------------------------

@dataclass
class DslContext:
    tree: BehaviorTree
    node: BehaviorNode
    element: BehaviorElement
    orchestrator: BehaviorOrchestrator

    # Accumulated state
    outcome: str = "next"
    value: Any = None
    updated_paths: list[str] = field(default_factory=list)
    op_log: list[dict] = field(default_factory=list)
    halted: bool = False

    # Element-local variables ($x)
    variables: dict[str, Any] = field(default_factory=dict)


class DslHalt(Exception):
    """Stop processing ops."""


# ---------------------------------------------------------------------------
# Ref resolution: $x, @x, @@x, literals
# ---------------------------------------------------------------------------

def _read_ref(ctx: DslContext, ref: Any) -> Any:
    """Read a value from a ref string or return literal."""
    if not isinstance(ref, str):
        # Handle special dict forms like {"inc": "@repair_count"}, {"coalesce": [...]}
        if isinstance(ref, dict):
            if "inc" in ref:
                val = _read_ref(ctx, ref["inc"])
                return (val or 0) + ref.get("by", 1)
            if "coalesce" in ref:
                for r in ref["coalesce"]:
                    v = _read_ref(ctx, r)
                    if v:
                        return v
                return ""
        return ref

    if ref.startswith("@@"):
        return ctx.tree.global_meta.get(ref[2:])
    if ref.startswith("@"):
        return ctx.node.data.get(ref[1:])
    if ref.startswith("$"):
        return ctx.variables.get(ref[1:])
    # Literal
    return ref


def _write_ref(ctx: DslContext, ref: str, value: Any) -> None:
    """Write a value to a ref target."""
    if ref.startswith("@@"):
        ctx.tree.global_meta[ref[2:]] = value
    elif ref.startswith("@"):
        ctx.node.data[ref[1:]] = value
        ctx.updated_paths.append(ref[1:])
    elif ref.startswith("$"):
        ctx.variables[ref[1:]] = value
    else:
        # Treat as node data by default
        ctx.node.data[ref] = value
        ctx.updated_paths.append(ref)


def _render_template(ctx: DslContext, template: str) -> str:
    """Expand template string: {$@field}, {$$var}, {$@@global}."""
    def replacer(m: re.Match) -> str:
        key = m.group(1)
        if key.startswith("@@"):
            val = ctx.tree.global_meta.get(key[2:])
        elif key.startswith("@"):
            val = ctx.node.data.get(key[1:])
        elif key.startswith("$"):
            # {$$varname} → local variable
            val = ctx.variables.get(key[1:])
        else:
            # {$varname} also tries local variable
            val = ctx.variables.get(key)
        return _stringify(val)
    return re.sub(r"\{\$([^}]+)\}", replacer, template)


def _stringify(val: Any) -> str:
    if val is None:
        return ""
    if isinstance(val, (list, tuple)):
        return ", ".join(str(v) for v in val)
    if isinstance(val, dict):
        return json.dumps(val, ensure_ascii=False)
    return str(val)


def _resolve_arg(ctx: DslContext, arg: Any) -> Any:
    """Resolve an argument: if string starting with $ or @, read ref. Otherwise literal."""
    if isinstance(arg, str):
        if arg.startswith("$") or arg.startswith("@"):
            return _read_ref(ctx, arg)
        if "{$" in arg:
            return _render_template(ctx, arg)
    if isinstance(arg, dict):
        return _read_ref(ctx, arg)
    return arg


# ---------------------------------------------------------------------------
# Predicate evaluation
# ---------------------------------------------------------------------------

def _eval_test(ctx: DslContext, test: dict) -> bool:
    """Evaluate a predicate expression."""
    if "empty" in test:
        val = _resolve_arg(ctx, test["empty"])
        if val is None:
            return True
        if isinstance(val, (list, str, dict)):
            return len(val) == 0
        return not val

    if "not_empty" in test:
        return not _eval_test(ctx, {"empty": test["not_empty"]})

    if "eq" in test:
        args = test["eq"]
        return _resolve_arg(ctx, args[0]) == _resolve_arg(ctx, args[1])

    if "ne" in test:
        args = test["ne"]
        return _resolve_arg(ctx, args[0]) != _resolve_arg(ctx, args[1])

    if "gt" in test:
        args = test["gt"]
        a, b = _resolve_arg(ctx, args[0]), _resolve_arg(ctx, args[1])
        return a is not None and a > b

    if "gte" in test:
        args = test["gte"]
        a, b = _resolve_arg(ctx, args[0]), _resolve_arg(ctx, args[1])
        return a is not None and a >= b

    if "lt" in test:
        args = test["lt"]
        a, b = _resolve_arg(ctx, args[0]), _resolve_arg(ctx, args[1])
        return a is not None and a < b

    if "lte" in test:
        args = test["lte"]
        a, b = _resolve_arg(ctx, args[0]), _resolve_arg(ctx, args[1])
        return a is not None and a <= b

    if "contains" in test:
        args = test["contains"]
        haystack = _resolve_arg(ctx, args[0])
        needle = _resolve_arg(ctx, args[1])
        if isinstance(haystack, str) and isinstance(needle, str):
            return needle.lower() in haystack.lower()
        if isinstance(haystack, (list, tuple)):
            return needle in haystack
        return False

    if "in" in test:
        args = test["in"]
        val = _resolve_arg(ctx, args[0])
        collection = _resolve_arg(ctx, args[1])
        if isinstance(collection, (list, tuple)):
            return val in collection
        return False

    if "in_range" in test:
        args = test["in_range"]
        val = _resolve_arg(ctx, args[0])
        rng = _resolve_arg(ctx, args[1])
        if val is not None and isinstance(rng, (list, tuple)) and len(rng) >= 2:
            return rng[0] <= val <= rng[1]
        return False

    if "all" in test:
        return all(_eval_test(ctx, sub) for sub in test["all"])

    if "any" in test:
        return any(_eval_test(ctx, sub) for sub in test["any"])

    if "not" in test:
        return not _eval_test(ctx, test["not"])

    return False


# ---------------------------------------------------------------------------
# Builtin functions registry
# ---------------------------------------------------------------------------

def _fn_len(ctx: DslContext, args: dict) -> Any:
    val = _resolve_arg(ctx, args.get("value"))
    return len(val) if val else 0


def _fn_split_sentences(ctx: DslContext, args: dict) -> Any:
    from .behavior_orchestrator import _sentence_split
    text = str(_resolve_arg(ctx, args.get("text", "")))
    return _sentence_split(text)


def _fn_join_sentences(ctx: DslContext, args: dict) -> Any:
    sentences = _resolve_arg(ctx, args.get("sentences", []))
    if isinstance(sentences, list):
        return " ".join(f"{s}." for s in sentences)
    return str(sentences)


def _fn_truncate_sentences(ctx: DslContext, args: dict) -> Any:
    from .behavior_orchestrator import _sentence_split
    text = str(_resolve_arg(ctx, args.get("text", "")))
    rng = _resolve_arg(ctx, args.get("range")) or ctx.tree.global_meta.get("sentence_range") or [5, 10]
    max_sent = int(rng[1]) if isinstance(rng, (list, tuple)) and len(rng) > 1 else 10
    sentences = _sentence_split(text)
    if len(sentences) > max_sent:
        sentences = sentences[:max_sent]
    return " ".join(f"{s}." for s in sentences)


def _fn_unique(ctx: DslContext, args: dict) -> Any:
    val = _resolve_arg(ctx, args.get("value", []))
    if isinstance(val, list):
        seen = set()
        result = []
        for v in val:
            if v not in seen:
                seen.add(v)
                result.append(v)
        return result
    return val


def _fn_count(ctx: DslContext, args: dict) -> Any:
    return _fn_len(ctx, args)


def _fn_node_field(ctx: DslContext, args: dict) -> Any:
    node_id = str(_resolve_arg(ctx, args.get("node_id", "")))
    field_name = str(_resolve_arg(ctx, args.get("field", "")))
    target_node = ctx.tree.nodes.get(node_id)
    if target_node:
        return target_node.data.get(field_name)
    return None


def _fn_render_template(ctx: DslContext, args: dict) -> Any:
    template = str(_resolve_arg(ctx, args.get("template", "")))
    return _render_template(ctx, template)


def _fn_call_agent(ctx: DslContext, args: dict) -> Any:
    from .behavior_orchestrator import _strip_think

    agent = str(_resolve_arg(ctx, args.get("agent", "")) or ctx.tree.global_meta.get("creative_agent", "small_context_worker"))
    prompt = str(_resolve_arg(ctx, args.get("prompt", "")))
    system = _resolve_arg(ctx, args.get("system"))
    temp = float(_resolve_arg(ctx, args.get("temperature")) or ctx.tree.global_meta.get("temperature", 0.6))
    max_tok = int(_resolve_arg(ctx, args.get("max_tokens")) or ctx.tree.global_meta.get("max_tokens", 2048))
    no_think = _resolve_arg(ctx, args.get("no_think"))
    if no_think is None:
        no_think = True

    text = ctx.orchestrator.llm.call(
        agent, prompt,
        system_prompt=str(system) if system else None,
        temperature=temp,
        max_tokens=max_tok,
        no_think=bool(no_think),
    )
    return _strip_think(text).strip()


def _fn_eval_claims(ctx: DslContext, args: dict) -> Any:
    scope = str(_resolve_arg(ctx, args.get("scope", "node")))
    if scope == "tree":
        ctx.orchestrator.evaluate_claims(ctx.tree)
    else:
        ctx.orchestrator.evaluate_claims(ctx.tree, node_id=ctx.node.node_id)
    from .behavior_orchestrator import ClaimLifecycle
    return [c.claim_id for c in ctx.node.claims if c.status != ClaimLifecycle.PASS]


def _fn_inc(ctx: DslContext, args: dict) -> Any:
    val = _resolve_arg(ctx, args.get("value", 0))
    by = args.get("by", 1)
    return (val or 0) + by


BUILTIN_FNS: dict[str, Callable[[DslContext, dict], Any]] = {
    "inc": _fn_inc,
    "len": _fn_len,
    "split_sentences": _fn_split_sentences,
    "join_sentences": _fn_join_sentences,
    "truncate_sentences": _fn_truncate_sentences,
    "unique": _fn_unique,
    "count": _fn_count,
    "node_field": _fn_node_field,
    "render_template": _fn_render_template,
    "call_agent": _fn_call_agent,
    "eval_claims": _fn_eval_claims,
    "evaluate_claims": _fn_eval_claims,
}


# ---------------------------------------------------------------------------
# Command execution
# ---------------------------------------------------------------------------

def _exec_cmd(ctx: DslContext, cmd: dict) -> None:
    """Execute a single DSL command."""

    # --- set ---
    if "set" in cmd:
        for ref, val in cmd["set"].items():
            resolved = _resolve_arg(ctx, val)
            _write_ref(ctx, ref, resolved)

    # --- copy ---
    elif "copy" in cmd:
        src = cmd["copy"]["from"]
        dst = cmd["copy"]["to"]
        _write_ref(ctx, dst, _read_ref(ctx, src))

    # --- save (local → persistent) ---
    elif "save" in cmd:
        for ref, val_ref in cmd["save"].items():
            _write_ref(ctx, ref, _read_ref(ctx, val_ref))

    # --- render ---
    elif "render" in cmd:
        spec = cmd["render"]
        template = spec.get("template", "")
        rendered = _render_template(ctx, template)
        target = spec.get("to", "$_rendered")
        _write_ref(ctx, target, rendered)

    # --- call ---
    elif "call" in cmd:
        spec = cmd["call"]
        fn_name = spec.get("fn", "")
        raw_args = spec.get("args", {})
        target = spec.get("to")

        # Resolve args
        resolved_args = {}
        for k, v in raw_args.items():
            resolved_args[k] = _resolve_arg(ctx, v)

        # Python function call: py:module.path:function_name
        if fn_name.startswith("py:"):
            result = _call_python_fn(ctx, fn_name[3:], resolved_args)
        else:
            fn = BUILTIN_FNS.get(fn_name)
            if fn is None:
                raise ValueError(f"Unknown builtin function: {fn_name}")
            result = fn(ctx, resolved_args)

        if target:
            _write_ref(ctx, target, result)

    # --- outcome ---
    elif "outcome" in cmd:
        ctx.outcome = str(_resolve_arg(ctx, cmd["outcome"]))

    # --- return ---
    elif "return" in cmd:
        ctx.value = _read_ref(ctx, cmd["return"])

    # --- if ---
    elif "if" in cmd:
        spec = cmd["if"]
        test = spec.get("test", {})
        if _eval_test(ctx, test):
            _run_do(ctx, spec.get("then", []))
        else:
            _run_do(ctx, spec.get("else", []))

    # --- for_each ---
    elif "for_each" in cmd:
        spec = cmd["for_each"]
        items = _resolve_arg(ctx, spec.get("in", []))
        var_name = spec.get("as", "$item")
        if not var_name.startswith("$"):
            var_name = "$" + var_name
        body = spec.get("do", [])
        max_iter = spec.get("max", 100)

        if isinstance(items, (list, tuple)):
            for i, item in enumerate(items):
                if i >= max_iter:
                    break
                ctx.variables[var_name[1:]] = item
                ctx.variables["_index"] = i
                _run_do(ctx, body)
                if ctx.halted:
                    break

    # --- append ---
    elif "append" in cmd:
        spec = cmd["append"]
        target = spec.get("to", "$_list")
        value = _resolve_arg(ctx, spec.get("value"))
        current = _read_ref(ctx, target)
        if not isinstance(current, list):
            current = []
        current.append(value)
        _write_ref(ctx, target, current)

    # --- claims (shortcut) ---
    elif "claims" in cmd:
        target = cmd["claims"]
        if isinstance(target, dict):
            scope = target.get("scope", "node")
            to = target.get("to", "$_failures")
        else:
            scope = "node"
            to = target

        failures = _fn_eval_claims(ctx, {"scope": scope})
        _write_ref(ctx, to, failures)

    # --- run_node ---
    elif "run_node" in cmd:
        spec = cmd["run_node"]
        node_id = str(_resolve_arg(ctx, spec.get("node_id", "")))
        target = spec.get("to")
        record = ctx.orchestrator.run_node(ctx.tree, node_id)
        if target:
            _write_ref(ctx, target, {
                "outcome": record.outcome,
                "return_value": record.return_value,
                "executed_elements": record.executed_elements,
            })

    # --- collect ---
    elif "collect" in cmd:
        spec = cmd["collect"]
        node_ids = _resolve_arg(ctx, spec.get("from_nodes", []))
        field_name = spec.get("field", "final_text")
        target = spec.get("to", "$_collected")
        results = []
        if isinstance(node_ids, (list, tuple)):
            for nid in node_ids:
                target_node = ctx.tree.nodes.get(str(nid))
                if target_node:
                    results.append(target_node.data.get(field_name))
        _write_ref(ctx, target, results)

    # --- finalize_claims ---
    elif "finalize_claims" in cmd:
        spec = cmd["finalize_claims"]
        from .behavior_orchestrator import ClaimLifecycle
        ctx.orchestrator.evaluate_claims(ctx.tree, node_id=ctx.node.node_id)
        all_pass = all(c.status == ClaimLifecycle.PASS for c in ctx.node.claims)
        status_field = spec.get("status_field", "@audit_status")
        _write_ref(ctx, status_field, spec.get("pass", "pass") if all_pass else spec.get("fail", "fail"))
        ret_field = spec.get("return")
        if ret_field:
            ctx.value = _read_ref(ctx, ret_field)

    # --- halt ---
    elif "halt" in cmd:
        raise DslHalt()

    # --- log ---
    elif "log" in cmd:
        msg = _render_template(ctx, str(cmd["log"]))
        ctx.op_log.append({"cmd": "log", "message": msg, "status": "done"})

    else:
        raise ValueError(f"Unknown DSL command: {list(cmd.keys())}")


def _call_python_fn(ctx: DslContext, dotted_path: str, args: dict) -> Any:
    """Call a Python function by dotted path: module.path:function_name."""
    import importlib
    parts = dotted_path.rsplit(":", 1)
    if len(parts) != 2:
        raise ValueError(f"Invalid py function path: {dotted_path}")
    module_path, fn_name = parts
    mod = importlib.import_module(module_path)
    fn = getattr(mod, fn_name)
    return fn(**args)


# ---------------------------------------------------------------------------
# Interpreter loop
# ---------------------------------------------------------------------------

def _run_do(ctx: DslContext, commands: list[dict]) -> None:
    """Execute a list of DSL commands."""
    for cmd in commands:
        if ctx.halted:
            break

        # Determine command name for logging
        cmd_name = next(iter(cmd.keys()), "?")
        log_entry = {"cmd": cmd_name, "status": "running"}
        ctx.op_log.append(log_entry)

        try:
            _exec_cmd(ctx, cmd)
            log_entry["status"] = "done"
        except DslHalt:
            log_entry["status"] = "halted"
            ctx.halted = True
        except Exception as exc:
            log_entry["status"] = "error"
            log_entry["error"] = str(exc)
            raise


# ---------------------------------------------------------------------------
# Entry point: registered as "__dsl__" handler
# ---------------------------------------------------------------------------

def handle_dsl(
    tree: BehaviorTree,
    node: BehaviorNode,
    element: BehaviorElement,
    orchestrator: BehaviorOrchestrator,
) -> ElementExecutionResult:
    from .behavior_orchestrator import ElementExecutionResult

    commands = element.meta.get("do", [])
    ctx = DslContext(
        tree=tree, node=node, element=element, orchestrator=orchestrator,
    )

    _run_do(ctx, commands)

    # Persist op log for UI inspection
    node.meta["_dsl_log"] = ctx.op_log

    return ElementExecutionResult(
        outcome=ctx.outcome,
        value=ctx.value,
        updated_paths=tuple(ctx.updated_paths),
    )


# ---------------------------------------------------------------------------
# DSL-based claim evaluation
# ---------------------------------------------------------------------------

def eval_dsl_claim(tree: BehaviorTree, claim: Any, orchestrator: BehaviorOrchestrator) -> tuple[str, str]:
    """Evaluate a claim defined with DSL expr/dsl. Returns (status, details)."""
    from .behavior_orchestrator import ClaimLifecycle

    node = tree.nodes.get(claim.owner_node_id or "")
    if not node:
        return ClaimLifecycle.PENDING, "node not found"

    # Build a minimal context for predicate evaluation
    ctx = DslContext(
        tree=tree, node=node,
        element=node.elements[0] if node.elements else None,
        orchestrator=orchestrator,
    )

    dsl_spec = claim.meta.get("dsl") if hasattr(claim, "meta") and claim.meta else None
    expr = claim.meta.get("expr") if hasattr(claim, "meta") and claim.meta else None

    if dsl_spec:
        # Check pending condition first
        pending_test = dsl_spec.get("pending_if")
        if pending_test and _eval_test(ctx, pending_test):
            return ClaimLifecycle.PENDING, dsl_spec.get("pending", "pending")

        test = dsl_spec.get("test", {})
        if _eval_test(ctx, test):
            return ClaimLifecycle.PASS, dsl_spec.get("pass", "pass")
        return ClaimLifecycle.FAIL, dsl_spec.get("fail", "fail")

    if expr:
        if _eval_test(ctx, expr):
            return ClaimLifecycle.PASS, "expr pass"
        return ClaimLifecycle.FAIL, "expr fail"

    return ClaimLifecycle.PENDING, "no dsl/expr defined"
