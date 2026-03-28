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


class AnnotationWikiBuildRequest(BaseModel):
    messages: list[dict[str, Any]]
    tag_groups: dict[str, list[str]]
    message_id: str = "wiki_unique_annotations_001"
    title: str = "Unique Annotation Summary"


class AnnotationWikiMergeRequest(BaseModel):
    existing_message: dict[str, Any]
    messages: list[dict[str, Any]]
    tag_groups: dict[str, list[str]]


class ProbeAnnotationRequest(BaseModel):
    """Probe-based annotation: use think-injection probes to find char spans."""
    message: dict[str, Any]            # message with text containers
    constraints: list[dict[str, Any]]  # [{name, tags, probe_prompt}]
    workers: dict[str, str] = {}       # {"analyzer": "http://..."}


class FnLibrarySaveRequest(BaseModel):
    """Save a DSL fn definition as a wiki function_page."""
    slug: str                    # e.g. "fn-claims"
    title: str                   # e.g. "claims"
    source: str                  # Assembly fn source code
    tags: list[str] = []


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


def _asm_escape(text: str) -> str:
    """Escape a string for safe embedding in Assembly DSL quoted strings."""
    return str(text).replace("\\", "\\\\").replace('"', '\\"').replace("\n", "\\n").replace("\r", "")


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
        """Execute Assembly DSL code.

        Automatically loads library functions from wiki function_page entries
        if the wiki router is available.
        """
        from .assembly_dsl import execute, load_library_functions
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

    # ── fn library management ─────────────────────────────────────

    @router.post("/fn/save")
    def fn_library_save(req: FnLibrarySaveRequest) -> dict[str, Any]:
        """Save a DSL fn definition as a wiki function_page."""
        from .assembly_dsl import parse_program

        # Validate that the source parses
        try:
            _, fns = parse_program(req.source)
            if not fns:
                return {"error": "No fn definition found in source", "saved": False}
        except SyntaxError as exc:
            return {"error": str(exc), "saved": False}

        fn_names = list(fns.keys())

        # Store as a simple dict in memory (wiki integration is via atomic_wiki router)
        # This endpoint returns the parsed fn info for the caller to persist
        return {
            "slug": req.slug,
            "title": req.title,
            "fn_names": fn_names,
            "fn_params": {n: fns[n].params for n in fn_names},
            "fn_outputs": {n: fns[n].outputs for n in fn_names},
            "source": req.source,
            "tags": req.tags,
            "page": {
                "slug": req.slug,
                "title": req.title,
                "page_kind": "function_page",
                "blocks": [{"kind": "text", "label": "source", "text": req.source}],
                "tags": ["function"] + req.tags,
            },
            "saved": True,
            "error": None,
        }

    @router.post("/fn/list")
    def fn_library_list() -> dict[str, Any]:
        """List available fn definitions from registered pages.

        Note: actual pages come from atomic-wiki; this endpoint
        just validates and parses fn source from provided pages.
        """
        return {"info": "Use GET /api/atomic-wiki/pages?page_kind=function_page to list fn pages"}

    # ── probe-based annotation ─────────────────────────────────────

    @router.post("/annotations/probe")
    def annotations_probe(req: ProbeAnnotationRequest) -> dict[str, Any]:
        """Find char spans for constraints in message text using think-injection probes.

        For each constraint + container, runs Assembly GEN probes to find
        char_start and char_end, then builds annotations.
        Non-LLM fallback: if workers are empty, uses regex matching.
        """
        from .dsl_builtins import char_indexed, create_span_annotation

        message = dict(req.message)
        containers = message.get("containers", [])
        constraints = req.constraints
        workers = req.workers

        annotations: list[dict[str, Any]] = []

        for container in containers:
            if container.get("kind") not in ("text", "wiki_summary"):
                continue
            text = container.get("data", {}).get("text", "")
            if not text:
                continue
            container_name = container.get("name", "main_text")

            for constraint in constraints:
                probe_prompt = constraint.get("probe_prompt", constraint.get("name", ""))

                # If workers provided, use Assembly GEN probes
                if workers and workers.get("analyzer"):
                    from .assembly_dsl import execute
                    from .workflow_dsl import WorkflowContext, build_default_builtins

                    thread_log: list = []
                    ctx = WorkflowContext(
                        workers=workers,
                        settings={},
                        builtins=build_default_builtins(),
                        on_thread=lambda *a, **kw: thread_log.append(a),
                    )

                    indexed = char_indexed(text)

                    # Probe start: think injection
                    start_code = (
                        f'PUT @chat, "user", "{_asm_escape(indexed)}"\n'
                        f'PUT+ @chat, "assistant", "<think>\\n'
                        f'Ищу фрагмент про \\"{_asm_escape(probe_prompt)}\\" в тексте.\\n'
                        f'Фрагмент начинается с символа номер \\"char_start:"\n'
                        f'GEN @start, @chat, mode:probe, grammar:"root ::= [0-9] | [0-9][0-9] | [0-9][0-9][0-9] | [0-9][0-9][0-9][0-9]", '
                        f'capture:"[0-9]+", coerce:int, worker:analyzer, temp:0, max:6'
                    )

                    try:
                        r1 = execute(start_code, ctx)
                        start_pos = ctx.get("$start")
                        if not isinstance(start_pos, int):
                            start_pos = 0
                    except Exception:
                        start_pos = 0
                    finally:
                        ctx.close()

                    # Probe end
                    snippet = text[start_pos:start_pos + 40]
                    ctx2 = WorkflowContext(
                        workers=workers, settings={},
                        builtins=build_default_builtins(),
                        on_thread=lambda *a, **kw: None,
                    )
                    end_code = (
                        f'PUT @chat, "user", "{_asm_escape(indexed)}"\n'
                        f'PUT+ @chat, "assistant", "<think>\\n'
                        f'Фрагмент про \\"{_asm_escape(probe_prompt)}\\":\\n'
                        f'начало: {start_pos}, текст: \\"{_asm_escape(snippet)}...\\"\\n'
                        f'конец фрагмента: char_end:"\n'
                        f'GEN @end, @chat, mode:probe, grammar:"root ::= [0-9] | [0-9][0-9] | [0-9][0-9][0-9] | [0-9][0-9][0-9][0-9]", '
                        f'capture:"[0-9]+", coerce:int, worker:analyzer, temp:0, max:6'
                    )
                    try:
                        r2 = execute(end_code, ctx2)
                        end_pos = ctx2.get("$end")
                        if not isinstance(end_pos, int) or end_pos <= start_pos:
                            end_pos = min(start_pos + len(probe_prompt) + 20, len(text))
                    except Exception:
                        end_pos = min(start_pos + len(probe_prompt) + 20, len(text))
                    finally:
                        ctx2.close()

                else:
                    # Regex fallback: simple substring search
                    import re as _re
                    pattern = _re.escape(probe_prompt)
                    m = _re.search(pattern, text, _re.IGNORECASE)
                    if m:
                        start_pos = m.start()
                        end_pos = m.end()
                    else:
                        start_pos = 0
                        end_pos = 0

                if start_pos >= 0 and end_pos > start_pos:
                    entity_like = {
                        "answer": text,
                        "_message_ref": message.get("message_id", ""),
                        "_container_ref": container_name,
                    }
                    ann = create_span_annotation(entity_like, constraint, start_pos, end_pos)
                    annotations.append(ann)

        # Merge annotations into message
        if "annotations" not in message:
            message["annotations"] = []
        message["annotations"].extend(annotations)

        return {
            "message": message,
            "annotations_added": len(annotations),
            "error": None,
        }

    @router.post("/annotations/wiki/build")
    def annotations_wiki_build(req: AnnotationWikiBuildRequest) -> dict[str, Any]:
        from .atomic_annotations import build_unique_wikilike_message

        message = build_unique_wikilike_message(
            req.messages,
            req.tag_groups,
            message_id=req.message_id,
            title=req.title,
        )
        return {
            "message": message,
            "error": None,
        }

    @router.post("/annotations/wiki/merge")
    def annotations_wiki_merge(req: AnnotationWikiMergeRequest) -> dict[str, Any]:
        from .atomic_annotations import merge_unique_wikilike_message

        message = merge_unique_wikilike_message(
            req.existing_message,
            req.messages,
            req.tag_groups,
        )
        return {
            "message": message,
            "error": None,
        }

    return router
