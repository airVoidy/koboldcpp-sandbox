"""Atomic Data DSL MVP — API router.

Ingests arbitrary JSON, projects it to a table with metadata,
supports patches, and resolves back to JSON.
"""

from __future__ import annotations

import time
from typing import Any

from fastapi import APIRouter
from pydantic import BaseModel


# ── request / response models ───────────────────────────────────────

class IngestRequest(BaseModel):
    json_data: dict[str, Any]
    name: str = "object"


class PatchRequest(BaseModel):
    rows: list[dict[str, Any]]
    patch: dict[str, Any]  # {target, value, reason?}


class ResolveRequest(BaseModel):
    rows: list[dict[str, Any]]
    object_name: str = "object"


class AsmRequest(BaseModel):
    code: str
    config: dict[str, Any] = {}
    state: dict[str, Any] = {}
    workers: dict[str, str] = {}  # role → base_url


class EventCompileRequest(BaseModel):
    dsl: str


# ── helpers ─────────────────────────────────────────────────────────

def _type_name(v: Any) -> str:
    if v is None:
        return "null"
    if isinstance(v, bool):
        return "bool"
    if isinstance(v, int):
        return "int"
    if isinstance(v, float):
        return "float"
    if isinstance(v, str):
        return "str"
    if isinstance(v, list):
        return "list"
    if isinstance(v, dict):
        return "dict"
    return type(v).__name__


def _field_group(path: str, object_name: str = "") -> str:
    relative = _strip_object_prefix(path, object_name)
    if "." in relative:
        return relative.split(".", 1)[0]
    return "root"


def _strip_object_prefix(path: str, object_name: str) -> str:
    if object_name and path.startswith(f"{object_name}."):
        return path[len(object_name) + 1 :]
    return path


def flatten_json(data: dict[str, Any], prefix: str = "", object_name: str = "") -> list[dict[str, Any]]:
    """Flatten a nested JSON object into table rows with dot-paths."""
    rows: list[dict[str, Any]] = []
    for key, value in data.items():
        path = f"{prefix}.{key}" if prefix else key
        if isinstance(value, dict):
            rows.extend(flatten_json(value, path, object_name=object_name))
        elif isinstance(value, list):
            # Store lists as-is (single row with type=list)
            rows.append({
                "field": key,
                "type": _type_name(value),
                "value": value,
                "path": path,
                "group": _field_group(path, object_name),
                "aliases": [path, _strip_object_prefix(path, object_name)],
                "meta": {"cell_kind": "plain", "is_collection": True},
            })
        else:
            rows.append({
                "field": key,
                "type": _type_name(value),
                "value": value,
                "path": path,
                "group": _field_group(path, object_name),
                "aliases": [path, _strip_object_prefix(path, object_name)],
                "meta": {"cell_kind": "plain"},
            })
    return rows


def rows_to_json(rows: list[dict[str, Any]], object_name: str = "") -> dict[str, Any]:
    """Reconstruct nested JSON from table rows with dot-paths."""
    result: dict[str, Any] = {}
    for row in rows:
        path = _strip_object_prefix(row["path"], object_name)
        value = row["value"]
        # Coerce value back from string edits
        vtype = row.get("type", "str")
        value = _coerce(value, vtype)
        parts = path.split(".")
        target = result
        for part in parts[:-1]:
            if part not in target:
                target[part] = {}
            target = target[part]
        target[parts[-1]] = value
    return result


def _coerce(value: Any, vtype: str) -> Any:
    """Best-effort coerce a value to its declared type."""
    if value is None:
        return None
    try:
        if vtype == "int":
            return int(value)
        if vtype == "float":
            return float(value)
        if vtype == "bool":
            if isinstance(value, str):
                return value.strip().lower() in ("true", "1", "yes", "on")
            return bool(value)
        if vtype in ("list", "dict"):
            return value  # keep structured types as-is
        if vtype == "null":
            return None
    except (ValueError, TypeError):
        pass
    return value


def apply_patch(rows: list[dict[str, Any]], target: str, value: Any) -> list[dict[str, Any]]:
    """Apply a patch to table rows, returning new rows list."""
    updated = []
    for row in rows:
        if row["path"] == target:
            new_row = dict(row)
            new_row["value"] = value
            new_row["type"] = _type_name(value)
            row_meta = dict(new_row.get("meta") or {})
            row_meta["last_patch_value_type"] = new_row["type"]
            new_row["meta"] = row_meta
            updated.append(new_row)
        else:
            updated.append(row)
    return updated


# ── router factory ──────────────────────────────────────────────────

def create_atomic_dsl_router() -> APIRouter:
    router = APIRouter(tags=["atomic-dsl"])

    @router.post("/ingest")
    def ingest(req: IngestRequest) -> dict[str, Any]:
        raw = req.json_data
        name = req.name
        rows = flatten_json(raw, name, object_name=name)
        ts = time.time()

        node_tree = {
            "node": "object",
            "name": name,
            "children": [
                {"node": "raw_json", "value": raw},
                {
                    "node": "table",
                    "value": {"rows": rows},
                },
                {
                    "node": "meta",
                    "value": {
                        "ingested_at": ts,
                        "field_count": len(rows),
                        "source": "user_input",
                        "object_path": name,
                    },
                },
            ],
        }
        return node_tree

    @router.post("/patch")
    def patch(req: PatchRequest) -> dict[str, Any]:
        target = req.patch.get("target", "")
        value = req.patch.get("value")
        reason = req.patch.get("reason", "")

        new_rows = apply_patch(req.rows, target, value)

        patch_node = {
            "node": "patch",
            "target": target,
            "value": value,
            "meta": {"reason": reason, "applied_at": time.time()},
        }
        return {"rows": new_rows, "patch_node": patch_node}

    @router.post("/resolve")
    def resolve(req: ResolveRequest) -> dict[str, Any]:
        resolved = rows_to_json(req.rows, object_name=req.object_name)
        return {
            "node": "resolved_json",
            "value": resolved,
        }

    @router.post("/asm")
    def asm_execute(req: AsmRequest) -> dict[str, Any]:
        """Execute Assembly DSL code."""
        from .assembly_dsl import execute
        from .workflow_dsl import WorkflowContext, build_default_builtins

        workers = req.workers
        if not workers:
            workers = {"generator": "http://127.0.0.1:5001", "analyzer": "http://127.0.0.1:5001", "verifier": "http://127.0.0.1:5001"}

        thread_log: list[dict[str, Any]] = []

        def on_thread(role: str, name: str, content: str, extra: dict) -> None:
            thread_log.append({"role": role, "name": name, "content": content[:500], **extra})

        ctx = WorkflowContext(
            workers=workers,
            settings=req.config,
            builtins=build_default_builtins(),
            on_thread=on_thread,
        )

        # Pre-load state
        for key, val in req.state.items():
            ref = key if key.startswith(("$", "@")) else "$" + key
            ctx.set(ref, val)

        # Pre-load config as $config.*
        for key, val in req.config.items():
            ctx.set(f"$config.{key}", val)

        try:
            result = execute(req.code, ctx)
            return {
                "state": result.state,
                "log": result.log,
                "thread": thread_log,
                "error": result.error,
            }
        except Exception as exc:
            return {
                "state": {},
                "log": [],
                "thread": thread_log,
                "error": str(exc),
            }
        finally:
            ctx.close()

    @router.post("/event/compile")
    def event_compile(req: EventCompileRequest) -> dict[str, Any]:
        from .event_dsl import EventDslSyntaxError, compile_event_dsl, parse_event_dsl

        try:
            statements = parse_event_dsl(req.dsl)
            assembly = compile_event_dsl(req.dsl)
            return {
                "assembly": assembly,
                "statement_count": len(statements),
                "error": None,
            }
        except EventDslSyntaxError as exc:
            return {
                "assembly": "",
                "statement_count": 0,
                "error": str(exc),
            }

    return router
