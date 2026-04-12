from __future__ import annotations

import asyncio
import copy
import hashlib
from dataclasses import asdict, is_dataclass
import shutil
import uuid
import json
import re
import time
from pathlib import Path
from typing import Any

from fastapi import FastAPI, Header, HTTPException, Request, Response
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse
import httpx
import yaml
from pydantic import BaseModel

from .assertions import ClaimStatus, HypothesisTree
from .models import PNode, PNodeStore, jpath, utc_now
from .behavior_orchestrator import (
    BehaviorTree,
    build_character_description_reference_tree,
    create_reference_behavior_orchestrator,
    load_reference_behavior_tree_template,
    reference_behavior_tree_template_path,
)
from .hypothesis_runtime import HypothesisRuntime
from .logic_manifest import (
    AtomicRuleSet,
    LinearSchemaExtractionResult,
    LogicExtractionResult,
    LogicManifest,
    build_linear_schema_prompt,
    build_logic_manifest_prompt,
    linear_schema_to_manifest,
    load_first_thoughts_example,
    parse_atomic_rule_set,
    parse_linear_logic_schema,
    parse_logic_manifest,
    prepare_reasoning_excerpt,
    verify_logic,
)
from .llm_continue import llm_call_with_continue, strip_think
from .reactive import AtomRuntime, ReactiveAtom, evaluate_atom
from .orchestrator import export_graph, run_task
from .kobold_client import KoboldClient, KoboldGenerationConfig
from .macro_registry import MacroRecord, get_macro, load_macro_registry, save_macro_registry
from .storage import Sandbox
from .core import build_schema_backends_from_linear, linear_schema_to_puzzle_schema
from .data_store.api import create_datastore_router
from .data_store.store import DataStore
from .atomic_data_revision import create_atomic_data_revision_router
from .atomic_wiki import create_atomic_wiki_router
from .atomic_dsl_api import create_atomic_dsl_router, flatten_json
try:
    import jsonata as _jsonata_mod
    _HAS_JSONATA = True
except ImportError:
    _HAS_JSONATA = False
try:
    from .ui_proto import (
        AddNodeOp,
        ConsoleCommandError,
        ConsolePatchContext,
        LayoutDocument,
        LayoutNode,
        MoveNodeOp,
        NlpMeta,
        NodeMeta,
        Rect,
        ScreenSpec,
        SetNodeRectOp,
        UiRuntime,
        UpdateNodeMetaOp,
        apply_patch_ops,
        build_ui_runtime,
        compile_console_command,
        load_ui,
        render_utf_runtime,
        save_ui,
    )
    _UI_PROTO_AVAILABLE = True
except Exception:
    _UI_PROTO_AVAILABLE = False

    class _UiProtoMissingError(RuntimeError):
        pass

    def _missing_ui_proto(*_args: Any, **_kwargs: Any) -> Any:
        raise _UiProtoMissingError("legacy ui_proto module is unavailable in this checkout")

    AddNodeOp = MoveNodeOp = SetNodeRectOp = UpdateNodeMetaOp = object
    ConsoleCommandError = _UiProtoMissingError
    ConsolePatchContext = LayoutDocument = LayoutNode = NlpMeta = NodeMeta = Rect = ScreenSpec = UiRuntime = object
    apply_patch_ops = build_ui_runtime = compile_console_command = load_ui = render_utf_runtime = save_ui = _missing_ui_proto

try:
    from .ui_proto_reactive import (
        ReactiveUiError,
        add_node as reactive_add_node,
        build_base_json as reactive_build_base_json,
        compose_layers as reactive_compose_layers,
        delete_node as reactive_delete_node,
        ensure_project as reactive_ensure_project,
        global_rect as reactive_global_rect,
        load_project as reactive_load_project,
        local_rect as reactive_local_rect,
        move_node as reactive_move_node,
        next_id as reactive_next_id,
        pick_node as reactive_pick_node,
        project_tree as reactive_project_tree,
        replace_node_from_yaml as reactive_replace_node_from_yaml,
        resolve_focus as reactive_resolve_focus,
        resize_node as reactive_resize_node,
        save_layers as reactive_save_layers,
        save_project as reactive_save_project,
        selected_node_json as reactive_selected_node_json,
        selected_node_yaml as reactive_selected_node_yaml,
    )
    _UI_PROTO_REACTIVE_AVAILABLE = True
except Exception:
    _UI_PROTO_REACTIVE_AVAILABLE = False

    class ReactiveUiError(RuntimeError):
        pass

    def _missing_ui_proto_reactive(*_args: Any, **_kwargs: Any) -> Any:
        raise ReactiveUiError("legacy ui_proto_reactive module is unavailable in this checkout")

    reactive_add_node = reactive_build_base_json = reactive_compose_layers = reactive_delete_node = _missing_ui_proto_reactive
    reactive_ensure_project = reactive_global_rect = reactive_load_project = reactive_local_rect = _missing_ui_proto_reactive
    reactive_move_node = reactive_next_id = reactive_pick_node = reactive_project_tree = _missing_ui_proto_reactive
    reactive_replace_node_from_yaml = reactive_resolve_focus = reactive_resize_node = _missing_ui_proto_reactive
    reactive_save_layers = reactive_save_project = reactive_selected_node_json = reactive_selected_node_yaml = _missing_ui_proto_reactive


class CreateNodeRequest(BaseModel):
    parent_id: str
    title: str
    summary: str = ""
    tags: list[str] = []


class RunRequest(BaseModel):
    task: str
    model: str | None = None
    commit: bool = False


class ProjectionRequest(BaseModel):
    template: str
    scope: str = ""


class MessageProjectionRequest(BaseModel):
    path: str


class AtomicViewRequest(BaseModel):
    path: str
    view: str = "object"


class AtomicPatchRequest(BaseModel):
    atomic_path: str
    value: Any


class AtomicDefineFieldRequest(BaseModel):
    atomic_path: str
    value_type: str | None = None
    default: Any = None


def _mojibake_marker_count(text: str) -> int:
    value = str(text or "")
    patterns = (
        r"Р[А-Яа-яЁё]",
        r"С[А-Яа-яЁё]",
        r"вЂ.",
        r"Ñ.",
        r"Ð.",
    )
    return sum(len(re.findall(pattern, value)) for pattern in patterns)


def _encoding_report(text: Any) -> dict[str, Any]:
    value = str(text or "")
    repaired_cp1251 = None
    repaired_latin1 = None

    try:
        candidate = value.encode("cp1251").decode("utf-8")
        if candidate != value:
            repaired_cp1251 = candidate
    except UnicodeError:
        repaired_cp1251 = None

    try:
        candidate = value.encode("latin1").decode("utf-8")
        if candidate != value:
            repaired_latin1 = candidate
    except UnicodeError:
        repaired_latin1 = None

    markers = _mojibake_marker_count(value)
    suspect = bool(repaired_cp1251 or repaired_latin1) and markers >= 3
    repair_preview = repaired_cp1251 or repaired_latin1 or ""

    return {
        "length": len(value),
        "has_cyrillic": bool(re.search(r"[А-Яа-яЁё]", value)),
        "mojibake_markers": markers,
        "suspect_mojibake": suspect,
        "repair_preview": repair_preview[:240],
        "sample": value[:240],
    }


def _legacy_ui_unavailable(name: str) -> HTTPException:
    return HTTPException(status_code=410, detail=f"legacy UI '{name}' is unavailable in this checkout")


class NotesRequest(BaseModel):
    content: str


class AtomEvaluateRequest(BaseModel):
    atom_id: str | None = None
    expression: str | None = None
    variables: list[str] = []
    source_claim_id: str | None = None
    context: dict[str, Any] = {}


class AtomBatchEvaluateItem(BaseModel):
    atom_id: str | None = None
    expression: str
    variables: list[str] = []
    source_claim_id: str | None = None


class AtomBatchEvaluateRequest(BaseModel):
    atoms: list[AtomBatchEvaluateItem]
    context: dict[str, Any] = {}


class HypothesisEvaluateItem(BaseModel):
    hypothesis_id: str
    title: str
    parent_id: str = "root"
    status: str = "hypothesis"
    assumptions: list[str] = []
    consequences: list[str] = []
    related_cells: list[str] = []
    related_hypothesis_ids: list[str] = []
    atom_ids: list[str] = []


class HypothesisEvaluateAtom(BaseModel):
    atom_id: str
    expression: str
    variables: list[str] = []
    source_claim_id: str | None = None
    hypothesis_id: str


class HypothesisEvaluateRequest(BaseModel):
    start_hypothesis_id: str
    hypotheses: list[HypothesisEvaluateItem]
    atoms: list[HypothesisEvaluateAtom]
    context: dict[str, Any] = {}


class ChatRequest(BaseModel):
    session_id: str | None = None
    nickname: str | None = None
    user_context: str | None = None
    message: str
    system_prompt: str | None = None
    model: str | None = None


class LogicParseRequest(BaseModel):
    analysis_text: str
    model: str | None = None


class LogicVerifyRequest(BaseModel):
    """Accept raw text in ENTITIES/RULES/BRANCHES format for parse + verify without LLM."""
    raw_schema: str


class ImageGenerateRequest(BaseModel):
    session_id: str | None = None
    prompt: str
    negative_prompt: str | None = None
    steps: int = 20
    width: int = 512
    height: int = 512
    cfg_scale: float = 7.0
    sampler_name: str | None = None
    batch_size: int = 1


class ChatSessionCreateRequest(BaseModel):
    title: str | None = None


class PChatExecRequest(BaseModel):
    cmd: str
    user: str = "anon"
    log: bool = True  # set False for read-only operations (skip logging)
    scope: str = "CMD"  # terminal scope name


class PChatBatchRequest(BaseModel):
    cmds: list[str]
    user: str = "anon"
    log: bool = True
    scope: str = "CMD"


class PChatSysRequest(BaseModel):
    """Non-user CMD: binds, triggers, auto-patches."""
    cmd: str
    user: str = "system"
    scope: str = "sys"


class PChatStateRequest(BaseModel):
    channel: str | None = None
    msg_limit: int = 50
    user: str = "anon"


class BehaviorJsonUpdateRequest(BaseModel):
    payload: dict[str, Any]
    expected_revision: int | None = None
    merge_on_conflict: bool = False


class BehaviorPatchRequest(BaseModel):
    patch: dict[str, Any]
    expected_revision: int | None = None
    merge_on_conflict: bool = True


class PlanTaskRequest(BaseModel):
    session_id: str | None = None
    task: str
    tree_id: str = "auto"
    run: bool = False
    settings: dict | None = None


class UiProtoCommandRequest(BaseModel):
    command: str
    selected_id: str | None = None
    focus_id: str | None = None


class UiProtoSelectRequest(BaseModel):
    x: int
    y: int
    selected_id: str | None = None
    focus_id: str | None = None


class UiProtoGuiActionRequest(BaseModel):
    action: str
    selected_id: str | None = None
    focus_id: str | None = None
    rect: list[int] | None = None
    parent_id: str | None = None
    kind: str = "panel"
    node_id: str | None = None


class UiProtoMetaSaveRequest(BaseModel):
    selected_id: str
    yaml_text: str
    focus_id: str | None = None


class UiProto2NodeSaveRequest(BaseModel):
    selected_id: str
    yaml_text: str
    focus_id: str | None = None


class UiProto2FilesSaveRequest(BaseModel):
    base_text: str
    events_dsl: str
    selected_id: str | None = None
    focus_id: str | None = None


class UiProto2CommandRequest(BaseModel):
    command: str
    selected_id: str | None = None
    focus_id: str | None = None


class UiProto2SelectRequest(BaseModel):
    x: int
    y: int
    selected_id: str | None = None
    focus_id: str | None = None


class UiProto2GuiActionRequest(BaseModel):
    action: str
    selected_id: str | None = None
    focus_id: str | None = None
    rect: list[int] | None = None
    parent_id: str | None = None
    kind: str = "panel"
    node_id: str | None = None


def _mcp_success(request_id: Any, result: dict[str, Any]) -> dict[str, Any]:
    return {"jsonrpc": "2.0", "id": request_id, "result": result}


def _mcp_error(request_id: Any, code: int, message: str, data: Any | None = None) -> dict[str, Any]:
    error: dict[str, Any] = {"code": code, "message": message}
    if data is not None:
        error["data"] = data
    return {"jsonrpc": "2.0", "id": request_id, "error": error}


def _mcp_tool_result(payload: Any, *, is_error: bool = False) -> dict[str, Any]:
    return {
        "content": [
            {
                "type": "text",
                "text": json.dumps(payload, ensure_ascii=False, indent=2),
            }
        ],
        "structuredContent": payload,
        "isError": is_error,
    }


def _etag_for_revision(revision: int) -> str:
    return f'W/"rev-{revision}"'


def _revision_from_if_match(value: str | None) -> int | None:
    if not value:
        return None
    match = re.fullmatch(r'W/"rev-(\d+)"|"rev-(\d+)"|rev-(\d+)', value.strip())
    if not match:
        return None
    for group in match.groups():
        if group is not None:
            return int(group)
    return None


def _paths_overlap(left: set[tuple[str, ...]], right: set[tuple[str, ...]]) -> bool:
    for lhs in left:
        for rhs in right:
            if lhs == rhs or lhs[: len(rhs)] == rhs or rhs[: len(lhs)] == lhs:
                return True
    return False


def _diff_paths(base: Any, other: Any, prefix: tuple[str, ...] = ()) -> set[tuple[str, ...]]:
    if isinstance(base, dict) and isinstance(other, dict):
        changed: set[tuple[str, ...]] = set()
        for key in set(base) | set(other):
            if key not in base or key not in other:
                changed.add(prefix + (str(key),))
                continue
            changed |= _diff_paths(base[key], other[key], prefix + (str(key),))
        return changed
    if isinstance(base, list) and isinstance(other, list):
        if base == other:
            return set()
        return {prefix}
    if base != other:
        return {prefix}
    return set()


def _deep_merge(target: dict[str, Any], patch: dict[str, Any]) -> dict[str, Any]:
    merged = dict(target)
    for key, value in patch.items():
        if isinstance(value, dict) and isinstance(merged.get(key), dict):
            merged[key] = _deep_merge(merged[key], value)
        else:
            merged[key] = value
    return merged


def _patch_paths(patch: Any, prefix: tuple[str, ...] = ()) -> set[tuple[str, ...]]:
    if isinstance(patch, dict):
        changed: set[tuple[str, ...]] = set()
        for key, value in patch.items():
            child_prefix = prefix + (str(key),)
            nested = _patch_paths(value, child_prefix)
            if nested:
                changed |= nested
            else:
                changed.add(child_prefix)
        return changed
    return {prefix} if prefix else set()


def _history_snapshot(history_holder: dict[str, Any], revision: int) -> dict[str, Any] | None:
    history = history_holder.get("_revision_history", {})
    snapshot = history.get(str(revision))
    return snapshot if isinstance(snapshot, dict) else None


def _set_behavior_headers(
    response: Response,
    *,
    revision: int,
    updated_at: str,
    merge_status: str = "none",
) -> None:
    response.headers["ETag"] = _etag_for_revision(revision)
    response.headers["Last-Modified"] = updated_at
    response.headers["X-Behavior-Merge"] = merge_status


def create_app(root: str) -> FastAPI:
    sandbox = Sandbox(Path(root))
    atom_runtime = AtomRuntime()
    hypothesis_runtime = HypothesisRuntime(atom_runtime)
    import os

    behavior_orchestrator = create_reference_behavior_orchestrator(
        worker_url=os.environ.get("BEHAVIOR_WORKER_URL"),
        planner_url=os.environ.get("BEHAVIOR_PLANNER_URL"),
    )
    behavior_trees: dict[str, BehaviorTree] = {"default": build_character_description_reference_tree()}
    app = FastAPI(title="Kobold Sandbox")

    def resolve_behavior_tree(session_id: str | None = None) -> BehaviorTree:
        resolved = (session_id or "default").strip() or "default"
        if resolved not in behavior_trees:
            behavior_trees[resolved] = build_character_description_reference_tree()
        return behavior_trees[resolved]

    # CORS for browser access
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # Mount DataStore API
    datastore_root = Path(root).resolve() / ".sandbox" / "datastore"
    app.include_router(create_datastore_router(datastore_root), prefix="/api/datastore")
    app.include_router(create_atomic_wiki_router(DataStore(datastore_root)), prefix="/api/atomic-wiki")
    app.include_router(create_atomic_data_revision_router(DataStore(datastore_root)), prefix="/api/atomic-data")
    app.include_router(create_atomic_dsl_router(), prefix="/api/dsl")

    from .pipeline_store import create_pipeline_store_router
    pipeline_store_dir = Path(root).resolve() / ".sandbox" / "pipeline_store"
    app.include_router(create_pipeline_store_router(pipeline_store_dir), prefix="/api/pipeline-store")

    sessions: dict[str, dict[str, Any]] = {
        "default": {
            "id": "default",
            "title": "Main Chat",
            "chat_log": [],
            "chat_history": [],
        }
    }

    def ensure_session(session_id: str | None) -> dict[str, Any]:
        sid = session_id or "default"
        if sid not in sessions:
            sessions[sid] = {
                "id": sid,
                "title": "Untitled Chat",
                "chat_log": [],
                "chat_history": [],
            }
        return sessions[sid]

    def resolve_client() -> KoboldClient:
        candidate_urls: list[str] = []
        if sandbox.exists():
            candidate_urls.append(sandbox.load_state().kobold_url)
        if "http://localhost:5001" not in candidate_urls:
            candidate_urls.append("http://localhost:5001")
        for url in candidate_urls:
            if _kobold_available(url):
                return KoboldClient(url)
        return KoboldClient(candidate_urls[0])

    def resolve_default_model() -> str | None:
        if sandbox.exists():
            return sandbox.load_state().default_model
        return None

    def require_initialized_sandbox() -> None:
        if not sandbox.exists():
            raise RuntimeError("Sandbox not initialized.")

    def run_atom_evaluation(request: AtomEvaluateRequest) -> dict[str, Any]:
        atom = ReactiveAtom(
            atom_id=request.atom_id or "anonymous-atom",
            expression=request.expression or "",
            variables=tuple(request.variables),
            source_claim_id=request.source_claim_id,
        )
        atom_runtime.register(atom)
        return evaluate_atom(atom, request.context).__dict__

    def run_connected_hypothesis_evaluation(request: HypothesisEvaluateRequest) -> dict[str, Any]:
        tree = HypothesisTree.from_problem("api-runtime")
        built: dict[str, Any] = {tree.root.node_id: tree.root, "root": tree.root}

        pending = list(request.hypotheses)
        while pending:
            progressed = False
            for item in pending[:]:
                if item.parent_id not in built:
                    continue
                node = built[item.parent_id]
                child = tree.create_child(
                    node,
                    claim=_claim_stub(item),
                    title=item.title,
                    consequences=item.consequences,
                    related_cells=item.related_cells,
                )
                child.node_id = item.hypothesis_id
                child.branch_name = f"hyp/{item.hypothesis_id}"
                child.status = ClaimStatus(item.status)
                child.assumptions = list(item.assumptions)
                child.related_hypothesis_ids = list(item.related_hypothesis_ids)
                built[item.hypothesis_id] = child
                pending.remove(item)
                progressed = True
            if not progressed:
                raise ValueError("Could not resolve hypothesis parent links.")

        for atom_item in request.atoms:
            if atom_item.hypothesis_id not in built:
                raise ValueError(f"Unknown hypothesis id for atom: {atom_item.hypothesis_id}")
            hypothesis_runtime.attach_atom(
                built[atom_item.hypothesis_id],
                ReactiveAtom(
                    atom_id=atom_item.atom_id,
                    expression=atom_item.expression,
                    variables=tuple(atom_item.variables),
                    source_claim_id=atom_item.source_claim_id,
                ),
            )

        graph = hypothesis_runtime.build_dependency_graph(tree)
        reaction = hypothesis_runtime.evaluate_connected(tree, request.start_hypothesis_id, request.context)
        return {
            "dependency_graph": {
                "adjacency": graph.adjacency,
                "reasons": graph.reasons,
            },
            "reaction": _reaction_to_dict(reaction),
        }

    mcp_tools = [
        {
            "name": "sandbox.graph",
            "description": "Return the current sandbox node graph.",
            "inputSchema": {"type": "object", "properties": {}, "additionalProperties": False},
        },
        {
            "name": "sandbox.create_node",
            "description": "Create a new sandbox node under a parent node.",
            "inputSchema": {
                "type": "object",
                "properties": {
                    "parent_id": {"type": "string"},
                    "title": {"type": "string"},
                    "summary": {"type": "string"},
                    "tags": {"type": "array", "items": {"type": "string"}},
                },
                "required": ["parent_id", "title"],
                "additionalProperties": False,
            },
        },
        {
            "name": "sandbox.update_notes",
            "description": "Replace node notes with the provided markdown content.",
            "inputSchema": {
                "type": "object",
                "properties": {
                    "node_id": {"type": "string"},
                    "content": {"type": "string"},
                },
                "required": ["node_id", "content"],
                "additionalProperties": False,
            },
        },
        {
            "name": "atoms.evaluate",
            "description": "Evaluate one reactive atom against a context object.",
            "inputSchema": {
                "type": "object",
                "properties": {
                    "atom_id": {"type": "string"},
                    "expression": {"type": "string"},
                    "variables": {"type": "array", "items": {"type": "string"}},
                    "source_claim_id": {"type": "string"},
                    "context": {"type": "object"},
                },
                "required": ["expression"],
                "additionalProperties": False,
            },
        },
        {
            "name": "hypotheses.evaluate_connected",
            "description": "Evaluate a connected hypothesis component with attached atoms.",
            "inputSchema": {
                "type": "object",
                "properties": {
                    "start_hypothesis_id": {"type": "string"},
                    "hypotheses": {"type": "array"},
                    "atoms": {"type": "array"},
                    "context": {"type": "object"},
                },
                "required": ["start_hypothesis_id", "hypotheses", "atoms"],
                "additionalProperties": False,
            },
        },
    ]

    def call_mcp_tool(name: str, arguments: dict[str, Any]) -> dict[str, Any]:
        if name == "sandbox.graph":
            require_initialized_sandbox()
            return export_graph(sandbox)
        if name == "sandbox.create_node":
            require_initialized_sandbox()
            request = CreateNodeRequest.model_validate(arguments)
            return sandbox.create_node(
                parent_id=request.parent_id,
                title=request.title,
                summary=request.summary,
                tags=request.tags,
            ).model_dump()
        if name == "sandbox.update_notes":
            require_initialized_sandbox()
            node_id = arguments.get("node_id")
            content = arguments.get("content")
            if not isinstance(node_id, str) or not isinstance(content, str):
                raise ValueError("sandbox.update_notes requires string fields: node_id, content")
            sandbox.update_notes(node_id, content)
            return {"ok": True, "node_id": node_id}
        if name == "atoms.evaluate":
            request = AtomEvaluateRequest.model_validate(arguments)
            return run_atom_evaluation(request)
        if name == "hypotheses.evaluate_connected":
            request = HypothesisEvaluateRequest.model_validate(arguments)
            return run_connected_hypothesis_evaluation(request)
        raise KeyError(name)

    @app.get("/health")
    def health() -> dict:
        return {"ok": True, "sandbox_exists": sandbox.exists()}

    @app.post("/api/mcp")
    def mcp_rpc(request: dict[str, Any]) -> dict[str, Any]:
        request_id = request.get("id")
        method = request.get("method")
        params = request.get("params") or {}
        if request.get("jsonrpc") != "2.0":
            return _mcp_error(request_id, -32600, "Invalid Request", "jsonrpc must be '2.0'.")
        if not isinstance(method, str):
            return _mcp_error(request_id, -32600, "Invalid Request", "method must be a string.")
        if not isinstance(params, dict):
            return _mcp_error(request_id, -32602, "Invalid params", "params must be an object.")

        try:
            if method == "initialize":
                return _mcp_success(
                    request_id,
                    {
                        "protocolVersion": "2025-03-26",
                        "serverInfo": {"name": "kobold-sandbox", "version": "0.1.0"},
                        "capabilities": {"tools": {"listChanged": False}},
                    },
                )
            if method == "ping":
                return _mcp_success(request_id, {"ok": True})
            if method == "tools/list":
                return _mcp_success(request_id, {"tools": mcp_tools})
            if method == "tools/call":
                name = params.get("name")
                arguments = params.get("arguments") or {}
                if not isinstance(name, str):
                    return _mcp_error(request_id, -32602, "Invalid params", "Tool name must be a string.")
                if not isinstance(arguments, dict):
                    return _mcp_error(request_id, -32602, "Invalid params", "Tool arguments must be an object.")
                try:
                    payload = call_mcp_tool(name, arguments)
                    return _mcp_success(request_id, _mcp_tool_result(payload))
                except KeyError:
                    return _mcp_error(request_id, -32601, f"Unknown tool: {name}")
                except (ValueError, RuntimeError) as exc:
                    return _mcp_success(request_id, _mcp_tool_result({"error": str(exc)}, is_error=True))
            return _mcp_error(request_id, -32601, f"Method not found: {method}")
        except Exception as exc:
            return _mcp_error(request_id, -32603, "Internal error", str(exc))

    @app.get("/graph")
    def graph() -> dict:
        if not sandbox.exists():
            raise HTTPException(404, "Sandbox not initialized.")
        return export_graph(sandbox)

    @app.get("/api/behavior/template")
    def get_behavior_template() -> dict:
        return {
            "path": str(reference_behavior_tree_template_path()),
            "template": load_reference_behavior_tree_template(),
        }

    @app.get("/api/behavior/tree")
    def get_behavior_tree(response: Response, session_id: str | None = None) -> dict:
        tree = resolve_behavior_tree(session_id)
        _set_behavior_headers(response, revision=tree.revision, updated_at=tree.updated_at)
        return tree.to_serialized_dict()

    @app.post("/api/behavior/tree")
    def update_behavior_tree(
        response: Response,
        request: BehaviorJsonUpdateRequest,
        session_id: str | None = None,
        if_match: str | None = Header(default=None, alias="If-Match"),
    ) -> dict:
        tree = resolve_behavior_tree(session_id)
        merge_status = "none"
        expected_revision = _revision_from_if_match(if_match)
        if expected_revision is None:
            expected_revision = request.expected_revision
        if expected_revision is None:
            incoming_revision = request.payload.get("revision")
            if isinstance(incoming_revision, int):
                expected_revision = incoming_revision
        if expected_revision is not None and expected_revision != tree.revision:
            if request.merge_on_conflict:
                base_snapshot = _history_snapshot(tree.global_meta, expected_revision)
                if isinstance(base_snapshot, dict):
                    current_snapshot = tree.to_serialized_dict()
                    user_changes = _diff_paths(base_snapshot, request.payload)
                    current_changes = _diff_paths(base_snapshot, current_snapshot)
                    if not _paths_overlap(user_changes, current_changes):
                        merged_payload = _deep_merge(current_snapshot, request.payload)
                        behavior_orchestrator.update_tree_from_json(tree, merged_payload)
                        behavior_orchestrator.persist_tree_to_meta(tree)
                        merge_status = "applied"
                        _set_behavior_headers(
                            response,
                            revision=tree.revision,
                            updated_at=tree.updated_at,
                            merge_status=merge_status,
                        )
                        return tree.to_serialized_dict()
            raise HTTPException(
                409,
                {
                    "error": "revision_conflict",
                    "expected_revision": expected_revision,
                    "actual_revision": tree.revision,
                },
            )
        behavior_orchestrator.update_tree_from_json(tree, request.payload)
        behavior_orchestrator.persist_tree_to_meta(tree)
        _set_behavior_headers(response, revision=tree.revision, updated_at=tree.updated_at, merge_status=merge_status)
        return tree.to_serialized_dict()

    @app.patch("/api/behavior/tree")
    def patch_behavior_tree(
        response: Response,
        request: BehaviorPatchRequest,
        session_id: str | None = None,
        if_match: str | None = Header(default=None, alias="If-Match"),
    ) -> dict:
        tree = resolve_behavior_tree(session_id)
        merge_status = "none"
        expected_revision = _revision_from_if_match(if_match)
        if expected_revision is None:
            expected_revision = request.expected_revision
        current_snapshot = tree.to_serialized_dict()
        merged_payload = _deep_merge(current_snapshot, request.patch)
        if expected_revision is not None and expected_revision != tree.revision:
            if request.merge_on_conflict:
                base_snapshot = _history_snapshot(tree.global_meta, expected_revision)
                if isinstance(base_snapshot, dict):
                    patch_paths = _patch_paths(request.patch)
                    current_changes = _diff_paths(base_snapshot, current_snapshot)
                    if not _paths_overlap(patch_paths, current_changes):
                        behavior_orchestrator.update_tree_from_json(tree, merged_payload)
                        behavior_orchestrator.persist_tree_to_meta(tree)
                        merge_status = "applied"
                        _set_behavior_headers(
                            response,
                            revision=tree.revision,
                            updated_at=tree.updated_at,
                            merge_status=merge_status,
                        )
                        return tree.to_serialized_dict()
            raise HTTPException(
                409,
                {
                    "error": "revision_conflict",
                    "expected_revision": expected_revision,
                    "actual_revision": tree.revision,
                },
            )
        behavior_orchestrator.update_tree_from_json(tree, merged_payload)
        behavior_orchestrator.persist_tree_to_meta(tree)
        _set_behavior_headers(response, revision=tree.revision, updated_at=tree.updated_at, merge_status=merge_status)
        return tree.to_serialized_dict()

    @app.get("/api/behavior/nodes/{node_id}")
    def get_behavior_node(node_id: str, response: Response, session_id: str | None = None) -> dict:
        try:
            node = resolve_behavior_tree(session_id).node(node_id)
            _set_behavior_headers(response, revision=node.revision, updated_at=node.updated_at)
            return node.to_serialized_dict()
        except KeyError as exc:
            raise HTTPException(404, f"Behavior node not found: {node_id}") from exc

    @app.post("/api/behavior/nodes/{node_id}")
    def update_behavior_node(
        node_id: str,
        response: Response,
        request: BehaviorJsonUpdateRequest,
        session_id: str | None = None,
        if_match: str | None = Header(default=None, alias="If-Match"),
    ) -> dict:
        tree = resolve_behavior_tree(session_id)
        try:
            node = tree.node(node_id)
            merge_status = "none"
            expected_revision = _revision_from_if_match(if_match)
            if expected_revision is None:
                expected_revision = request.expected_revision
            if expected_revision is None:
                incoming_revision = request.payload.get("revision")
                if isinstance(incoming_revision, int):
                    expected_revision = incoming_revision
            if expected_revision is not None and expected_revision != node.revision:
                if request.merge_on_conflict:
                    base_snapshot = _history_snapshot(node.meta, expected_revision)
                    if isinstance(base_snapshot, dict):
                        current_snapshot = node.to_serialized_dict()
                        user_changes = _diff_paths(base_snapshot, request.payload)
                        current_changes = _diff_paths(base_snapshot, current_snapshot)
                        if not _paths_overlap(user_changes, current_changes):
                            merged_payload = _deep_merge(current_snapshot, request.payload)
                            behavior_orchestrator.update_node_from_json(tree, node_id, merged_payload)
                            behavior_orchestrator.persist_node_to_meta(tree, node_id)
                            behavior_orchestrator.persist_tree_to_meta(tree)
                            merge_status = "applied"
                            current_node = tree.node(node_id)
                            _set_behavior_headers(
                                response,
                                revision=current_node.revision,
                                updated_at=current_node.updated_at,
                                merge_status=merge_status,
                            )
                            return tree.node(node_id).to_serialized_dict()
                raise HTTPException(
                    409,
                    {
                        "error": "revision_conflict",
                        "expected_revision": expected_revision,
                        "actual_revision": node.revision,
                        "node_id": node_id,
                    },
                )
            behavior_orchestrator.update_node_from_json(tree, node_id, request.payload)
            behavior_orchestrator.persist_node_to_meta(tree, node_id)
            behavior_orchestrator.persist_tree_to_meta(tree)
            current_node = tree.node(node_id)
            _set_behavior_headers(
                response,
                revision=current_node.revision,
                updated_at=current_node.updated_at,
                merge_status=merge_status,
            )
            return current_node.to_serialized_dict()
        except KeyError as exc:
            raise HTTPException(404, f"Behavior node not found: {node_id}") from exc

    @app.patch("/api/behavior/nodes/{node_id}")
    def patch_behavior_node(
        node_id: str,
        response: Response,
        request: BehaviorPatchRequest,
        session_id: str | None = None,
        if_match: str | None = Header(default=None, alias="If-Match"),
    ) -> dict:
        tree = resolve_behavior_tree(session_id)
        try:
            node = tree.node(node_id)
            merge_status = "none"
            expected_revision = _revision_from_if_match(if_match)
            if expected_revision is None:
                expected_revision = request.expected_revision
            current_snapshot = node.to_serialized_dict()
            merged_payload = _deep_merge(current_snapshot, request.patch)
            if expected_revision is not None and expected_revision != node.revision:
                if request.merge_on_conflict:
                    base_snapshot = _history_snapshot(node.meta, expected_revision)
                    if isinstance(base_snapshot, dict):
                        patch_paths = _patch_paths(request.patch)
                        current_changes = _diff_paths(base_snapshot, current_snapshot)
                        if not _paths_overlap(patch_paths, current_changes):
                            behavior_orchestrator.update_node_from_json(tree, node_id, merged_payload)
                            behavior_orchestrator.persist_node_to_meta(tree, node_id)
                            behavior_orchestrator.persist_tree_to_meta(tree)
                            merge_status = "applied"
                            current_node = tree.node(node_id)
                            _set_behavior_headers(
                                response,
                                revision=current_node.revision,
                                updated_at=current_node.updated_at,
                                merge_status=merge_status,
                            )
                            return tree.node(node_id).to_serialized_dict()
                raise HTTPException(
                    409,
                    {
                        "error": "revision_conflict",
                        "expected_revision": expected_revision,
                        "actual_revision": node.revision,
                        "node_id": node_id,
                    },
                )
            behavior_orchestrator.update_node_from_json(tree, node_id, merged_payload)
            behavior_orchestrator.persist_node_to_meta(tree, node_id)
            behavior_orchestrator.persist_tree_to_meta(tree)
            current_node = tree.node(node_id)
            _set_behavior_headers(
                response,
                revision=current_node.revision,
                updated_at=current_node.updated_at,
                merge_status=merge_status,
            )
            return current_node.to_serialized_dict()
        except KeyError as exc:
            raise HTTPException(404, f"Behavior node not found: {node_id}") from exc

    import threading

    _run_lock = threading.Lock()
    _run_status: dict = {"running": False, "node_id": None, "error": None}

    def _apply_settings(tree, body):
        for key in ("sentence_range", "temperature", "max_tokens", "language", "creative_agent"):
            if key in body:
                tree.global_meta[key] = body[key]

    def _bg_run_tree(tree):
        try:
            _run_status.update(running=True, node_id="root", error=None)
            behavior_orchestrator.run_tree(tree)
            _run_status.update(running=False, node_id=None)
        except Exception as exc:
            _run_status.update(running=False, error=str(exc))

    def _bg_run_node(tree, node_id):
        try:
            _run_status.update(running=True, node_id=node_id, error=None)
            behavior_orchestrator.run_node(tree, node_id)
            _run_status.update(running=False, node_id=None)
        except Exception as exc:
            _run_status.update(running=False, error=str(exc))

    @app.post("/api/behavior/run")
    async def run_behavior_tree(request: Request, session_id: str | None = None, sync: bool = False) -> dict:
        body = await request.json() if await request.body() else {}
        tree = resolve_behavior_tree(session_id)
        _apply_settings(tree, body)

        if sync:
            outputs = behavior_orchestrator.run_tree(tree)
            return {"root_node_id": tree.root_node_id, "outputs": outputs, "tree": tree.to_serialized_dict()}

        if _run_status["running"]:
            raise HTTPException(409, "A run is already in progress")
        threading.Thread(target=_bg_run_tree, args=(tree,), daemon=True).start()
        return {"status": "started", "root_node_id": tree.root_node_id}

    @app.post("/api/behavior/nodes/{node_id}/run")
    async def run_behavior_node(request: Request, node_id: str, session_id: str | None = None, sync: bool = False) -> dict:
        body = await request.json() if await request.body() else {}
        tree = resolve_behavior_tree(session_id)
        _apply_settings(tree, body)

        if sync:
            try:
                available = list(tree.nodes.keys())
                if node_id not in tree.nodes:
                    raise HTTPException(404, f"Node '{node_id}' not in tree. Available: {available}")
                record = behavior_orchestrator.run_node(tree, node_id)
                return {"record": record.model_dump(), "node": tree.node(node_id).to_serialized_dict(), "tree_meta": tree.global_meta}
            except KeyError as exc:
                raise HTTPException(404, f"Behavior node not found: {node_id}. Available: {list(tree.nodes.keys())}") from exc

        if _run_status["running"]:
            raise HTTPException(409, "A run is already in progress")
        threading.Thread(target=_bg_run_node, args=(tree, node_id), daemon=True).start()
        return {"status": "started", "node_id": node_id}

    @app.get("/api/behavior/status")
    def run_status() -> dict:
        return _run_status

    @app.post("/api/behavior/plan")
    def plan_behavior_tree(request: PlanTaskRequest) -> dict:
        from .nl_to_dsl import plan_and_build
        from .behavior_orchestrator import BehaviorTree

        try:
            # Build global_meta from UI settings
            global_meta: dict = {}
            if request.settings:
                for key in ("sentence_range", "temperature", "max_tokens", "language", "creative_agent"):
                    if key in request.settings:
                        global_meta[key] = request.settings[key]

            # Determine which agent to use for planning
            planner_agent = global_meta.get("creative_agent") or "small_context_worker"
            # Use first registered agent as fallback
            if planner_agent not in behavior_orchestrator.llm._clients:
                available = list(behavior_orchestrator.llm._clients.keys())
                if available:
                    planner_agent = available[0]

            tree_dict = plan_and_build(
                behavior_orchestrator.llm,
                request.task,
                planner_agent,
                global_meta=global_meta,
            )

            new_tree = BehaviorTree.from_serialized_dict(tree_dict)
            session_id = (request.session_id or "default").strip() or "default"
            behavior_trees[session_id] = new_tree

            result: dict = {
                "status": "planned",
                "tree_id": new_tree.tree_id,
                "item_count": len(new_tree.nodes) - 1,
                "tree": new_tree.to_serialized_dict(),
            }

            if request.run:
                outputs = behavior_orchestrator.run_tree(new_tree)
                result["status"] = "completed"
                result["outputs"] = outputs
                result["tree"] = new_tree.to_serialized_dict()

            return result
        except Exception as exc:
            raise HTTPException(500, f"Planning failed: {exc}") from exc

    @app.post("/api/behavior/agents")
    async def register_behavior_agents(request: Request) -> dict:
        """Register or update LLM agent URLs for the behavior orchestrator."""
        from .kobold_client import KoboldClient

        body = await request.json()
        registered = []
        for agent_name, url in body.items():
            if not url or not isinstance(url, str):
                continue
            url = url.strip().rstrip("/")
            if not url:
                continue
            behavior_orchestrator.llm.register(agent_name, KoboldClient(url, timeout=180.0))
            registered.append(agent_name)
        return {"registered": registered}

    @app.get("/api/behavior/agents")
    def list_behavior_agents() -> dict:
        """List registered LLM agent names."""
        return {"agents": list(behavior_orchestrator.llm._clients.keys())}

    @app.post("/api/behavior/nl/plan")
    async def nl_plan(request: Request) -> dict:
        """NL task → plan items → build tree with DSL elements."""
        from .nl_to_dsl import plan_and_build, plan_items

        body = await request.json()
        task = body.get("task", "")
        agent = body.get("agent", "small_context_worker")
        global_meta = body.get("global_meta", {})
        plan_only = body.get("plan_only", False)

        if not task:
            raise HTTPException(400, "task is required")

        try:
            if plan_only:
                items = plan_items(behavior_orchestrator.llm, task, agent)
                return {"status": "planned", "items": items}

            tree_dict = plan_and_build(
                behavior_orchestrator.llm, task, agent,
                global_meta=global_meta,
            )
            # Store as active tree
            session_id = body.get("session_id", "default")
            from .behavior_orchestrator import BehaviorTree
            new_tree = BehaviorTree.from_serialized_dict(tree_dict)
            behavior_trees[session_id] = new_tree
            return {
                "status": "built",
                "tree_id": tree_dict.get("tree_id"),
                "node_count": len(tree_dict.get("nodes", {})),
                "tree": tree_dict,
            }
        except Exception as exc:
            raise HTTPException(500, f"NL plan failed: {exc}") from exc

    @app.post("/api/behavior/nl/edit-element")
    async def nl_edit_element(request: Request) -> dict:
        """Edit element via NL chat instruction."""
        from .nl_to_dsl import edit_element_via_chat

        body = await request.json()
        element_json = body.get("element")
        instruction = body.get("instruction", "")
        agent = body.get("agent", "small_context_worker")

        if not element_json or not instruction:
            raise HTTPException(400, "element and instruction are required")

        try:
            result = edit_element_via_chat(
                behavior_orchestrator.llm,
                element_json,
                instruction,
                agent,
            )
            return {"status": "ok", "element": result}
        except Exception as exc:
            raise HTTPException(500, f"Edit failed: {exc}") from exc

    def _collect_valid_paths(tree_dict: dict, node_id: str | None = None) -> list[str]:
        """Collect sample valid set_path paths for the model to learn from."""
        paths = []
        gm = tree_dict.get("global_meta", {})
        for k in list(gm.keys())[:5]:
            paths.append(f"global_meta.{k}")
        if node_id and node_id in tree_dict.get("nodes", {}):
            node = tree_dict["nodes"][node_id]
            for k in list(node.get("data", {}).keys())[:8]:
                paths.append(f"nodes.{node_id}.data.{k}")
            els = node.get("elements", [])
            if els:
                paths.append(f"nodes.{node_id}.elements[0].meta.do")
        else:
            for nid in list(tree_dict.get("nodes", {}).keys())[:3]:
                for k in list(tree_dict["nodes"][nid].get("data", {}).keys())[:4]:
                    paths.append(f"nodes.{nid}.data.{k}")
        return paths

    @app.post("/api/behavior/nl/edit-node")
    async def nl_edit_node(request: Request) -> dict:
        """Edit tree/node via NL instruction using set_path patches."""
        from .nl_to_dsl import edit_tree_via_chat, apply_set_patches

        body = await request.json()
        instruction = body.get("instruction", "")
        node_id = body.get("node_id")
        agent = body.get("agent", "small_context_worker")
        session_id = body.get("session_id", "default")

        if not instruction:
            raise HTTPException(400, "instruction is required")

        tree = behavior_trees.get(session_id)
        if tree is None:
            raise HTTPException(404, "No active tree")

        try:
            tree_dict = tree.to_serialized_dict()
            patches = edit_tree_via_chat(
                behavior_orchestrator.llm,
                tree_dict,
                instruction,
                agent,
                node_id=node_id,
            )
            result = apply_set_patches(tree_dict, patches)

            # Retry failed patches: show errors to model, ask to fix
            if result.failed and result.applied > 0:
                # Some worked, some didn't — retry failed ones
                available_paths = _collect_valid_paths(tree_dict, node_id)
                retry_instruction = (
                    f"Некоторые патчи не удалось применить. Исправь пути.\n"
                    f"Ошибки:\n" +
                    "\n".join(f"  {p['set_path']}: {p['_error']}" for p in result.failed) +
                    f"\n\nДоступные пути:\n{json.dumps(available_paths, ensure_ascii=False)}"
                )
                try:
                    retry_patches = edit_tree_via_chat(
                        behavior_orchestrator.llm,
                        tree_dict,
                        retry_instruction,
                        agent,
                        node_id=node_id,
                    )
                    retry_result = apply_set_patches(tree_dict, retry_patches)
                    result.applied += retry_result.applied
                    result.failed = retry_result.failed
                except Exception:
                    pass  # retry is best-effort

            tree.refresh_from_serialized(tree_dict)
            return {
                "status": "ok",
                "patches": patches,
                "applied": result.applied,
                "failed": [{"set_path": p["set_path"], "error": p["_error"]} for p in result.failed],
                "tree": tree.to_serialized_dict(),
            }
        except Exception as exc:
            raise HTTPException(500, f"Edit failed: {exc}") from exc

    @app.get("/models")
    def models() -> dict:
        return {"models": resolve_client().list_models()}

    @app.post("/nodes")
    def create_node(request: CreateNodeRequest) -> dict:
        node = sandbox.create_node(
            parent_id=request.parent_id,
            title=request.title,
            summary=request.summary,
            tags=request.tags,
        )
        return node.model_dump()

    @app.put("/nodes/{node_id}/notes")
    def update_notes(node_id: str, request: NotesRequest) -> dict:
        sandbox.update_notes(node_id, request.content)
        return {"ok": True}

    @app.post("/nodes/{node_id}/run")
    def run(node_id: str, request: RunRequest) -> dict:
        result = run_task(sandbox, node_id, request.task, model=request.model, commit=request.commit)
        return result.model_dump()

    @app.get("/behavior", response_class=HTMLResponse)
    def behavior_page() -> str:
        raise _legacy_ui_unavailable("/behavior")

    # ------------------------------------------------------------------
    # Reactive Entity endpoints
    # ------------------------------------------------------------------
    from .reactive_entity import ReactiveTask, VerifyConfig
    from .reactive_runner import ReactiveRunner

    reactive_tasks: dict[str, ReactiveTask] = {}
    _reactive_run_status: dict[str, Any] = {"running": False}
    reactive_runner = ReactiveRunner(behavior_orchestrator)

    @app.post("/api/reactive/task")
    async def create_reactive_task(request: Request) -> dict:
        """Create a ReactiveTask from JSON spec."""
        body = await request.json()
        session_id = body.pop("session_id", "default")
        try:
            task = ReactiveTask.from_dict(body)
            reactive_tasks[session_id] = task
            return {
                "status": "created",
                "task_id": task.task_id,
                "entity_count": len(task.entities),
                "session_id": session_id,
            }
        except Exception as exc:
            raise HTTPException(400, f"Invalid task spec: {exc}") from exc

    @app.get("/api/reactive/task")
    def get_reactive_task(session_id: str | None = None) -> dict:
        """Get current reactive task state."""
        sid = session_id or "default"
        task = reactive_tasks.get(sid)
        if task is None:
            raise HTTPException(404, "No active reactive task")
        return task.to_dict()

    @app.post("/api/reactive/task/run")
    async def run_reactive_task(request: Request, session_id: str | None = None, sync: bool = False) -> dict:
        """Execute the reactive task."""
        import threading

        sid = session_id or "default"
        task = reactive_tasks.get(sid)
        if task is None:
            raise HTTPException(404, "No active reactive task")

        if _reactive_run_status["running"]:
            raise HTTPException(409, "A reactive task is already running")

        # Apply optional runtime settings from body
        body = {}
        try:
            body = await request.json()
        except Exception:
            pass

        if "verify_config" in body:
            task.verify_config = VerifyConfig.from_dict(body["verify_config"])

        if sync:
            _reactive_run_status["running"] = True
            try:
                result = reactive_runner.run_task(task)
                return {"status": "done", **result}
            finally:
                _reactive_run_status["running"] = False

        # Async
        def _bg_run():
            _reactive_run_status["running"] = True
            _reactive_run_status["error"] = None
            try:
                reactive_runner.run_task(task)
            except Exception as exc:
                _reactive_run_status["error"] = str(exc)
            finally:
                _reactive_run_status["running"] = False

        threading.Thread(target=_bg_run, daemon=True).start()
        return {"status": "started", "task_id": task.task_id}

    @app.get("/api/reactive/task/status")
    def reactive_task_status() -> dict:
        return dict(_reactive_run_status)

    @app.post("/api/reactive/task/entity/{entity_id}")
    async def set_reactive_entity(entity_id: str, request: Request, session_id: str | None = None) -> dict:
        """Manually set entity properties (triggers events)."""
        sid = session_id or "default"
        task = reactive_tasks.get(sid)
        if task is None:
            raise HTTPException(404, "No active reactive task")
        entity = task.entities.get(entity_id)
        if entity is None:
            raise HTTPException(404, f"Entity {entity_id} not found")

        body = await request.json()
        for key, value in body.items():
            entity.set(key, value)
        return entity.to_dict()

    @app.post("/api/reactive/task/pipeline/add")
    async def add_reactive_pipeline_layer(request: Request, session_id: str | None = None) -> dict:
        """Add a pipeline layer at runtime."""
        from .reactive_entity import PipelineLayer

        sid = session_id or "default"
        task = reactive_tasks.get(sid)
        if task is None:
            raise HTTPException(404, "No active reactive task")

        body = await request.json()
        try:
            layer = PipelineLayer.from_dict(body)
            task.add_layer(layer)
            return {"status": "added", "layer_id": layer.layer_id, "total_layers": len(task.pipeline)}
        except Exception as exc:
            raise HTTPException(400, f"Invalid layer: {exc}") from exc

    @app.get("/api/reactive/task/events")
    def get_reactive_events(session_id: str | None = None, limit: int = 100) -> dict:
        """Get event log."""
        sid = session_id or "default"
        task = reactive_tasks.get(sid)
        if task is None:
            raise HTTPException(404, "No active reactive task")
        return {"events": task.event_bus.event_log[-limit:]}

    @app.post("/api/reactive/reset")
    async def reset_reactive_state(request: Request, session_id: str | None = None) -> dict:
        """Reset reactive task/chat state for a session."""
        sid = session_id or "default"
        try:
            body = await request.json()
            sid = body.get("session_id", sid) or sid
        except Exception:
            pass

        task_existed = reactive_tasks.pop(sid, None) is not None
        chat_existed = _reactive_chat_state.pop(sid, None) is not None

        if not _reactive_run_status.get("running"):
            _reactive_run_status.pop("error", None)

        return {
            "status": "reset",
            "session_id": sid,
            "reactive_task_cleared": task_existed,
            "reactive_chat_cleared": chat_existed,
        }

    # ------------------------------------------------------------------
    # Reactive Chat — server-side task parsing + question generation
    # ------------------------------------------------------------------
    from .reactive_task_parser import (
        new_dialog_state, add_worker_response, add_user_message,
        call_worker, build_task_from_parsed, create_next_entity,
        extract_structure_from_response,
    )

    # Per-session dialog state
    _reactive_chat_state: dict[str, dict] = {}

    @app.post("/api/reactive/chat/send")
    async def reactive_chat_send(request: Request) -> dict:
        """Send message in dialog. Proxies to worker, all visible in thread.

        First message: creates dialog state, sends to worker.
        Follow-up: adds to conversation, sends to worker.
        Worker response returned for UI to display in thread.
        If worker returns parseable structure → task is built.
        """
        body = await request.json()
        message = body.get("message", "").strip()
        sid = body.get("session_id", "default")
        settings = body.get("settings", {})

        if not message:
            return {"type": "error", "message": "Empty message"}

        # Get or create dialog state
        state = _reactive_chat_state.get(sid)
        if not state:
            state = new_dialog_state(message)
        else:
            add_user_message(state, message)

        # Send to worker — no system prompt, just conversation
        worker_answer = ""
        worker_think = ""
        agent_name = settings.get("agent", "small_context_worker")
        if behavior_orchestrator.llm.get(agent_name):
            try:
                worker_answer, worker_think = call_worker(
                    state, behavior_orchestrator.llm,
                    agent_name=agent_name,
                    settings=settings,
                )
                add_worker_response(state, worker_answer, worker_think)
            except Exception as exc:
                worker_answer = f"Error: {exc}"
                add_worker_response(state, worker_answer)
        else:
            worker_answer = "(no worker registered)"
            add_worker_response(state, worker_answer)

        _reactive_chat_state[sid] = state

        # Build response
        result: dict[str, Any] = {
            "type": "dialog",
            "worker_answer": worker_answer,
            "worker_think": worker_think,
            "phase": state["phase"],
            "message_count": len(state["messages"]),
        }

        # If structure was extracted → build task
        if state["phase"] == "ready" and state.get("parsed"):
            task_dict = build_task_from_parsed(state)
            if task_dict:
                for k in ("temperature", "max_tokens", "max_continue", "no_think"):
                    if k in settings:
                        task_dict.setdefault("global_meta", {})[k] = settings[k]
                task = ReactiveTask.from_dict(task_dict)
                reactive_tasks[sid] = task
                result["type"] = "task_ready"
                result["task"] = task.to_dict()
                result["parsed"] = state["parsed"]

        return result

    @app.post("/api/reactive/chat/next-entity")
    async def reactive_chat_next_entity(request: Request) -> dict:
        """Create next entity after previous one completes. Iterative."""
        body = await request.json()
        sid = body.get("session_id", "default")

        state = _reactive_chat_state.get(sid)
        if not state:
            raise HTTPException(404, "No active task session")

        task = reactive_tasks.get(sid)
        if not task:
            raise HTTPException(404, "No active reactive task")

        entity_spec = create_next_entity(state)
        if not entity_spec:
            return {"type": "complete", "message": f"All {state.get('entity_count', 0)} entities created"}

        # Add entity to task
        eid = entity_spec["entity_id"]
        task.add_entity(eid, entity_spec["properties"])
        _reactive_chat_state[sid] = state

        return {
            "type": "entity_created",
            "entity_id": eid,
            "entity": task.entities[eid].to_dict(),
            "entities_created": state["entities_created"],
            "entity_count": state["entity_count"],
        }

    # ------------------------------------------------------------------
    # Workflow DSL executor
    # ------------------------------------------------------------------

    import threading as _workflow_threading
    import uuid as _workflow_uuid

    _workflow_runs_lock = _workflow_threading.Lock()
    _workflow_runs: dict[str, dict] = {}

    def _workflow_run_set(run_id: str, **updates) -> None:
        with _workflow_runs_lock:
            state = _workflow_runs.setdefault(run_id, {"thread": []})
            state.update(updates)

    def _workflow_run_append(run_id: str, item: dict) -> None:
        with _workflow_runs_lock:
            state = _workflow_runs.setdefault(run_id, {"thread": []})
            state.setdefault("thread", []).append(item)

    def _workflow_run_snapshot(run_id: str) -> dict | None:
        with _workflow_runs_lock:
            state = _workflow_runs.get(run_id)
            if state is None:
                return None
            return {
                "status": state.get("status", "running"),
                "thread": list(state.get("thread", [])),
                "vars": dict(state.get("vars", {})) if isinstance(state.get("vars"), dict) else state.get("vars"),
                "state": state.get("state"),
                "error": state.get("error"),
                "diagnostics": state.get("diagnostics", {}),
            }

    def _run_workflow_sync(
        yaml_text: str,
        input_text: str,
        settings: dict,
        worker_urls: dict,
        on_thread,
    ) -> dict:
        from .workflow_dsl import run_workflow

        thread: list[dict] = []

        def _thread_cb(role, name, content, extra=None):
            item = {"role": role, "name": name, "content": content, **(extra or {})}
            thread.append(item)
            on_thread(item)

        ctx = run_workflow(
            yaml_text,
            workers=worker_urls,
            settings=settings,
            on_thread=_thread_cb,
            initial_vars={"$input": input_text} if input_text else None,
        )
        try:
            return {
                "status": "done",
                "thread": thread,
                "vars": {k: _serialize(v) for k, v in ctx.vars.items()},
                "state": ctx.state,
                "diagnostics": {
                    "yaml": _encoding_report(yaml_text),
                    "input": _encoding_report(input_text),
                },
            }
        finally:
            ctx.close()

    def _start_workflow_run(yaml_text: str, input_text: str, settings: dict, worker_urls: dict) -> str:
        run_id = _workflow_uuid.uuid4().hex
        diagnostics = {
            "yaml": _encoding_report(yaml_text),
            "input": _encoding_report(input_text),
        }
        _workflow_run_set(run_id, status="running", thread=[], vars={}, state={}, error=None, diagnostics=diagnostics)

        def _worker() -> None:
            try:
                result = _run_workflow_sync(yaml_text, input_text, settings, worker_urls, lambda item: _workflow_run_append(run_id, item))
                _workflow_run_set(
                    run_id,
                    status=result["status"],
                    vars=result["vars"],
                    state=result["state"],
                    diagnostics=result["diagnostics"],
                    error=None,
                )
            except Exception as exc:
                _workflow_run_set(run_id, status="error", error=str(exc))

        _workflow_threading.Thread(target=_worker, daemon=True).start()
        return run_id

    @app.post("/api/workflow/run")
    async def run_workflow_endpoint(request: Request) -> dict:
        """Execute a workflow DSL YAML. All steps visible via thread callback."""
        body = await request.json()
        yaml_text = body.get("yaml", "")
        input_text = body.get("input", "")
        settings = body.get("settings", {})
        worker_urls = body.get("workers", {})  # role → url
        async_progress = bool(body.get("async_progress"))

        if not yaml_text:
            raise HTTPException(400, "yaml is required")

        if async_progress:
            run_id = _start_workflow_run(yaml_text, input_text, settings, worker_urls)
            return {"status": "started", "run_id": run_id}

        try:
            return _run_workflow_sync(yaml_text, input_text, settings, worker_urls, lambda item: None)
        except Exception as exc:
            return {
                "status": "error",
                "error": str(exc),
                "thread": [],
                "diagnostics": {
                    "yaml": _encoding_report(yaml_text),
                    "input": _encoding_report(input_text),
                },
            }

    @app.post("/api/workflow/patch")
    async def patch_workflow(request: Request) -> dict:
        """Apply set_path patches to YAML workflow."""
        import yaml as _yaml
        body = await request.json()
        yaml_text = body.get("yaml", "")
        patches = body.get("patches", [])
        try:
            spec = _yaml.safe_load(yaml_text)
            for patch in patches:
                path = patch.get("set_path", "")
                value = patch.get("value")
                # Navigate dotted/bracket path
                parts = []
                for p in re.split(r'\.|\[', path):
                    p = p.rstrip(']')
                    if p:
                        parts.append(int(p) if p.isdigit() else p)
                target = spec
                for p in parts[:-1]:
                    target = target[p]
                target[parts[-1]] = value
            return {"yaml": _yaml.dump(spec, allow_unicode=True, default_flow_style=False, sort_keys=False)}
        except Exception as e:
            return {"error": str(e)}

    @app.post("/api/workflow/clear")
    async def clear_workflow(request: Request) -> dict:
        """Clear KV cache on all workers."""
        import httpx
        body = await request.json()
        worker_urls = body.get("workers", {})
        cleared = []
        for role, url in worker_urls.items():
            try:
                async with httpx.AsyncClient(timeout=5) as client:
                    await client.post(f"{url.rstrip('/')}/api/admin/clear_state")
                cleared.append(role)
            except Exception:
                pass
        return {"status": "cleared", "workers": cleared}

    def _run_trigger_sync(
        yaml_text: str,
        trigger_name: str,
        settings: dict,
        worker_urls: dict,
        prev_vars: dict,
        on_thread,
    ) -> dict:
        from .workflow_dsl import run_workflow, run_trigger

        thread: list[dict] = []

        def _thread_cb(role, name, content, extra=None):
            item = {"role": role, "name": name, "content": content, **(extra or {})}
            thread.append(item)
            on_thread(item)

        ctx = run_workflow.__wrapped__(yaml_text, worker_urls, settings, None, _thread_cb) if hasattr(run_workflow, '__wrapped__') else None
        if ctx is None:
            import yaml as _yaml
            spec = _yaml.safe_load(yaml_text)
            from .workflow_dsl import WorkflowContext, build_default_builtins
            ctx = WorkflowContext(
                workers=worker_urls,
                settings=settings,
                builtins=build_default_builtins(),
                on_thread=_thread_cb,
            )
            ctx.triggers = spec.get("triggers", {})
            for k, v in prev_vars.items():
                ctx.set(k, v)

        try:
            run_trigger(ctx, trigger_name)
            return {
                "status": "done",
                "thread": thread,
                "vars": {k: _serialize(v) for k, v in ctx.vars.items()},
                "state": ctx.state,
                "diagnostics": {
                    "yaml": _encoding_report(yaml_text),
                    "trigger": trigger_name,
                },
            }
        finally:
            ctx.close()

    def _start_workflow_trigger(yaml_text: str, trigger_name: str, settings: dict, worker_urls: dict, prev_vars: dict) -> str:
        run_id = _workflow_uuid.uuid4().hex
        diagnostics = {
            "yaml": _encoding_report(yaml_text),
            "trigger": trigger_name,
        }
        _workflow_run_set(run_id, status="running", thread=[], vars={}, state={}, error=None, diagnostics=diagnostics)

        def _worker() -> None:
            try:
                result = _run_trigger_sync(yaml_text, trigger_name, settings, worker_urls, prev_vars, lambda item: _workflow_run_append(run_id, item))
                _workflow_run_set(
                    run_id,
                    status=result["status"],
                    vars=result["vars"],
                    state=result["state"],
                    diagnostics=result["diagnostics"],
                    error=None,
                )
            except Exception as exc:
                _workflow_run_set(run_id, status="error", error=str(exc))

        _workflow_threading.Thread(target=_worker, daemon=True).start()
        return run_id

    @app.post("/api/workflow/trigger")
    async def run_workflow_trigger(request: Request) -> dict:
        """Execute a named trigger from a workflow. Requires prior workflow run context."""
        body = await request.json()
        yaml_text = body.get("yaml", "")
        trigger_name = body.get("trigger", "")
        settings = body.get("settings", {})
        worker_urls = body.get("workers", {})
        prev_vars = body.get("vars", {})
        async_progress = bool(body.get("async_progress"))

        if not yaml_text or not trigger_name:
            raise HTTPException(400, "yaml and trigger are required")

        if async_progress:
            run_id = _start_workflow_trigger(yaml_text, trigger_name, settings, worker_urls, prev_vars)
            return {"status": "started", "run_id": run_id}

        try:
            return _run_trigger_sync(yaml_text, trigger_name, settings, worker_urls, prev_vars, lambda item: None)
        except Exception as exc:
            return {
                "status": "error",
                "error": str(exc),
                "thread": [],
                "diagnostics": {
                    "yaml": _encoding_report(yaml_text),
                    "trigger": trigger_name,
                },
            }

    @app.get("/api/workflow/progress")
    def get_workflow_progress(run_id: str, cursor: int = 0) -> dict:
        snapshot = _workflow_run_snapshot(run_id)
        if snapshot is None:
            raise HTTPException(404, "Unknown workflow run")
        all_thread = snapshot.get("thread", [])
        safe_cursor = max(0, int(cursor))
        return {
            "status": snapshot.get("status", "running"),
            "thread": all_thread[safe_cursor:],
            "next_cursor": len(all_thread),
            "vars": snapshot.get("vars") or {},
            "state": snapshot.get("state") or {},
            "error": snapshot.get("error"),
            "diagnostics": snapshot.get("diagnostics") or {},
        }

    @app.get("/api/workflow/default")
    def get_default_workflow() -> dict:
        """Return the default demo workflow YAML."""
        yaml_path = Path(__file__).resolve().parents[2] / "examples" / "behavior_case" / "demo_workflow.yaml"
        if yaml_path.exists():
            yaml_text = yaml_path.read_text(encoding="utf-8")
            return {"yaml": yaml_text, "encoding": _encoding_report(yaml_text)}
        return {"yaml": "", "encoding": _encoding_report("")}

    @app.get("/api/workflow/spec")
    def get_workflow_spec() -> dict:
        """Return the workflow DSL spec for LLM context."""
        spec_path = Path(__file__).resolve().parents[2] / "examples" / "behavior_case" / "WORKFLOW_DSL_SPEC.md"
        if spec_path.exists():
            spec_text = spec_path.read_text(encoding="utf-8")
            return {"spec": spec_text, "encoding": _encoding_report(spec_text)}
        return {"spec": "", "encoding": _encoding_report("")}

    @app.get("/api/macro-registry")
    def get_macro_registry_endpoint() -> dict:
        macros = load_macro_registry()
        return {
            "status": "ok",
            "macros": {name: macro.to_payload() for name, macro in macros.items()},
        }

    @app.post("/api/macro-registry/upsert")
    async def upsert_macro_registry_endpoint(request: Request) -> dict:
        body = await request.json()
        name = str(body.get("name", "") or "").strip()
        if not name:
            raise HTTPException(400, "name is required")
        macros = load_macro_registry()
        prior = macros.get(name)
        payload = {
            "name": name,
            "layer": str(body.get("layer") or (prior.layer if prior else "atomic")),
            "inputs": body.get("inputs") or (prior.inputs if prior else []),
            "outputs": body.get("outputs") or (prior.outputs if prior else []),
            "dsl": str(body.get("dsl") or (prior.dsl if prior else "")),
            "workflow_alias": body.get("workflow_alias") or (prior.workflow_alias if prior else []),
            "tags": body.get("tags") or (prior.tags if prior else []),
            "description": str(body.get("description") or (prior.description if prior else "")),
        }
        macros[name] = MacroRecord.from_payload(name, payload)
        path = save_macro_registry(macros)
        return {"status": "ok", "path": str(path), "macro": macros[name].to_payload()}

    @app.post("/api/macro-registry/delete")
    async def delete_macro_registry_endpoint(request: Request) -> dict:
        body = await request.json()
        name = str(body.get("name", "") or "").strip()
        if not name:
            raise HTTPException(400, "name is required")
        macros = load_macro_registry()
        removed = macros.pop(name, None)
        save_macro_registry(macros)
        return {"status": "ok", "deleted": bool(removed), "name": name}

    @app.get("/api/comfyui/view")
    async def comfyui_proxy_view(
        filename: str,
        subfolder: str = "",
        type: str = "output",
        server: str = "http://127.0.0.1:8188",
    ) -> Response:
        """Proxy ComfyUI image view to avoid CORS issues."""
        url = f"{server}/view?filename={filename}&subfolder={subfolder}&type={type}"
        try:
            async with httpx.AsyncClient() as client:
                resp = await client.get(url, timeout=30)
                return Response(
                    content=resp.content,
                    media_type=resp.headers.get("content-type", "image/png"),
                )
        except Exception as exc:
            raise HTTPException(502, f"ComfyUI proxy error: {exc}")

    @app.get("/api/comfyui/history/{prompt_id}")
    async def comfyui_proxy_history(
        prompt_id: str,
        server: str = "http://127.0.0.1:8188",
    ) -> dict:
        """Proxy ComfyUI history to check generation status."""
        try:
            async with httpx.AsyncClient() as client:
                resp = await client.get(f"{server}/history/{prompt_id}", timeout=10)
                return resp.json()
        except Exception as exc:
            raise HTTPException(502, f"ComfyUI proxy error: {exc}")

    @app.post("/api/think-lab/step")
    async def think_lab_step(request: Request) -> dict:
        """Proxy a single OpenAI-compatible chat completion step for Think Lab."""
        body = await request.json()
        url = str(body.get("url", "")).strip().rstrip("/")
        payload = body.get("payload")

        if not url:
            raise HTTPException(400, "url is required")
        if not isinstance(payload, dict):
            raise HTTPException(400, "payload must be an object")

        # Fix for llama.cpp with thinking models (port 5004 only):
        # Remove assistant prefill and disable thinking via chat_template_kwargs
        if "5004" in url:
            import copy
            payload = copy.deepcopy(payload)
            if payload.get("continue_assistant_turn"):
                msgs = payload.get("messages", [])
                if msgs and msgs[-1].get("role") == "assistant":
                    prefill = msgs[-1].get("content", "")
                    msgs = msgs[:-1]
                    if msgs and msgs[-1].get("role") == "user":
                        msgs[-1]["content"] = msgs[-1]["content"] + "\n\nContinue from: " + prefill
                    payload["messages"] = msgs
                payload.pop("continue_assistant_turn", None)
            payload.pop("enable_thinking", None)
            payload["chat_template_kwargs"] = {"enable_thinking": False}

        started_at = time.perf_counter()
        try:
            response = httpx.post(
                f"{url}/v1/chat/completions",
                json=payload,
                timeout=180.0,
                trust_env=False,
            )
            response.raise_for_status()
        except httpx.HTTPStatusError as exc:
            remote_text = exc.response.text[:2000] if exc.response is not None else ""
            detail = str(exc)
            if remote_text:
                detail = f"{detail}: {remote_text}"
            raise HTTPException(502, detail) from exc
        except httpx.HTTPError as exc:
            raise HTTPException(502, str(exc)) from exc

        latency_ms = int((time.perf_counter() - started_at) * 1000)
        raw = response.json()
        choice = (raw.get("choices") or [{}])[0]
        message = choice.get("message") or {}
        content = message.get("content")
        if isinstance(content, list):
            text = "".join(
                part.get("text", "")
                for part in content
                if isinstance(part, dict) and part.get("text")
            )
        else:
            text = str(content or "")
        # Extract token metrics from usage block (if present)
        usage = raw.get("usage") or {}
        prompt_tokens = usage.get("prompt_tokens")
        completion_tokens = usage.get("completion_tokens")
        tokens_per_second = None
        if completion_tokens and latency_ms > 0:
            tokens_per_second = round(completion_tokens / (latency_ms / 1000), 1)

        return {
            "status": "ok",
            "content": text,
            "finish_reason": choice.get("finish_reason"),
            "latency_ms": latency_ms,
            "prompt_tokens": prompt_tokens,
            "completion_tokens": completion_tokens,
            "tokens_per_second": tokens_per_second,
            "raw": raw,
        }

    # ================================================================
    #  LLM generate — centralised continue-on-length
    # ================================================================

    @app.post("/api/llm/generate")
    async def llm_generate(request: Request) -> dict:
        """Centralised LLM call with auto-continue on max_tokens.

        Body:
          url: worker base URL (e.g. "http://localhost:5001")
          messages: [{role, content}, ...]
          temperature?: float (default 0.6)
          max_tokens?: int (default 2048)
          no_think?: bool (default true)
          max_continue?: int (default 20)
          continue_on_length?: bool (default true)
          stop?: list[str]
          grammar?: str
          prompt_mode?: "auto"|"chat"|"instruct"

        Returns:
          {answer, think, continues, finish_reason, latency_ms, tokens}
        """
        body = await request.json()
        base_url = (body.get("url") or "").rstrip("/")
        if not base_url:
            raise HTTPException(400, "url is required")
        messages = body.get("messages", [])
        if not messages:
            raise HTTPException(400, "messages is required")

        no_think = body.get("no_think", True)
        try:
            res = llm_call_with_continue(
                base_url,
                messages,
                temperature=float(body.get("temperature", 0.6)),
                max_tokens=int(body.get("max_tokens", 2048)),
                no_think=no_think,
                max_continue=int(body.get("max_continue", 20)),
                continue_on_length=body.get("continue_on_length", True),
                stop=body.get("stop"),
                grammar=body.get("grammar"),
                prompt_mode=body.get("prompt_mode", "auto"),
            )
        except Exception as exc:
            raise HTTPException(502, str(exc)) from exc

        usage = res.raw_responses[-1].get("usage", {}) if res.raw_responses else {}
        return {
            "status": "ok",
            "answer": res.answer,
            "think": res.think,
            "continues": res.continues,
            "finish_reason": res.finish_reason,
            "prompt_mode": res.prompt_mode,
            "latency_ms": res.latency_ms,
            "tokens": {
                "prompt": usage.get("prompt_tokens"),
                "completion": usage.get("completion_tokens"),
            },
        }

    # ================================================================
    #  Atomic Tasks — server-side tool execution
    # ================================================================

    @app.post("/api/atomic/run")
    async def atomic_run(request: Request) -> dict:
        """Execute an atomic tool server-side.

        Body:
          tool: "slice" | "split" | "generate" | "claims" | ...
          params: tool-specific params (text, from_delim, to_delim, etc.)
          workers: {role: url} for LLM tools
          settings: {temperature, max_tokens, no_think, max_continue}
          role: which worker role to use (for LLM tools)
        """
        body = await request.json()
        tool = body.get("tool", "")
        params = body.get("params", {})
        workers = body.get("workers", {})
        settings = body.get("settings", {})
        role = body.get("role", "generator")

        if not tool:
            raise HTTPException(400, "tool is required")

        try:
            result = _run_atomic_tool(tool, params, workers, settings, role)
            if asyncio.iscoroutine(result):
                result = await result
            return {"status": "ok", **result}
        except ValueError as e:
            raise HTTPException(400, str(e))
        except Exception as e:
            raise HTTPException(500, f"{type(e).__name__}: {e}")

    def _scope_contexts(scope_vars: dict[str, Any]) -> dict[str, str]:
        contexts = scope_vars.get("__contexts__")
        if not isinstance(contexts, dict):
            contexts = {}
            scope_vars["__contexts__"] = contexts
        return contexts

    def _scope_get_context(scope_vars: dict[str, Any], name: str) -> str:
        return str(_scope_contexts(scope_vars).get(name, "") or "")

    def _scope_set_context(scope_vars: dict[str, Any], name: str, text: Any) -> str:
        value = str(text or "")
        _scope_contexts(scope_vars)[name] = value
        return value

    def _scope_append_context(
        scope_vars: dict[str, Any],
        name: str,
        text: Any,
        separator: str = "\n\n",
    ) -> str:
        appended = str(text or "").strip()
        current = _scope_get_context(scope_vars, name)
        if not appended:
            return current
        merged = f"{current}{separator if current else ''}{appended}"
        _scope_contexts(scope_vars)[name] = merged
        return merged

    def _scope_resolve_ref(ref_str: Any, scope_vars: dict[str, Any]) -> Any:
        if not isinstance(ref_str, str) or not ref_str.startswith("$"):
            return ref_str
        path = ref_str[1:]
        parts = path.split(".", 1)
        data = scope_vars.get(parts[0])
        if data is None:
            return ref_str
        if len(parts) > 1:
            return data.get(parts[1], ref_str) if isinstance(data, dict) else ref_str
        return data

    def _scope_inject_context(step: dict, params: dict, scope_vars: dict[str, Any]) -> dict:
        context_name = str(step.get("context") or "").strip()
        if not context_name:
            return params
        context_text = _scope_get_context(scope_vars, context_name)
        if not context_text:
            return params
        context_prefix = str(step.get("context_prefix") or "Context:\n{context}\n\n")
        injected = context_prefix.replace("{context}", context_text)
        next_params = copy.deepcopy(params)
        messages = next_params.get("messages")
        if isinstance(messages, list) and messages:
            if len(messages) == 1 and str(messages[0].get("role", "")).lower() == "user":
                messages[0]["content"] = f"{injected}{messages[0].get('content') or ''}"
            else:
                first_role = str(messages[0].get("role", "")).lower()
                if first_role == "system":
                    messages[0]["content"] = f"{messages[0].get('content') or ''}\n\n{injected}".strip()
                else:
                    messages.insert(0, {"role": "system", "content": injected.strip()})
            next_params["messages"] = messages
            return next_params
        for key in ("text", "prompt_template", "prompt", "content"):
            if isinstance(next_params.get(key), str):
                next_params[key] = f"{injected}{next_params[key]}"
                break
        return next_params

    def _scope_default_context_growth(result: Any) -> str:
        if isinstance(result, dict):
            for key in ("content", "answer", "text"):
                value = result.get(key)
                if isinstance(value, str) and value.strip():
                    return value
        return ""

    def _scope_apply_context_growth(step: dict, result: Any, scope_vars: dict[str, Any]) -> None:
        context_name = str(step.get("context") or "").strip()
        if not context_name:
            return
        tool_name = str(step.get("tool") or "").strip().lower()
        if "context_grow" not in step and tool_name in {"context_append", "prompt_factory"}:
            return
        if step.get("context_grow", True) is False:
            return
        append_spec = step.get("context_append")
        if append_spec is None:
            append_text = _scope_default_context_growth(result)
        else:
            ref_scope = dict(scope_vars)
            ref_scope["result"] = result
            resolved = _scope_resolve_ref(append_spec, ref_scope)
            append_text = resolved if isinstance(resolved, str) else json.dumps(resolved, ensure_ascii=False)
        _scope_append_context(scope_vars, context_name, append_text, str(step.get("context_separator") or "\n\n"))

    def _scope_run_factory_step(step: dict, params: dict, scope_vars: dict[str, Any]) -> dict | None:
        tool = str(step.get("tool") or "").strip().lower()
        if tool == "context_append":
            context_name = str(params.get("context") or step.get("context") or "main").strip() or "main"
            text = _scope_resolve_ref(params.get("text") or params.get("content") or "", scope_vars)
            merged = _scope_append_context(
                scope_vars,
                context_name,
                text,
                str(params.get("separator") or step.get("context_separator") or "\n\n"),
            )
            return {"content": merged, "context_name": context_name, "appended": str(text or "")}
        if tool == "prompt_factory":
            context_name = str(params.get("context") or step.get("context") or "main").strip() or "main"
            prompt = str(params.get("prompt") or params.get("text") or params.get("content") or "")
            context_text = _scope_get_context(scope_vars, context_name)
            prefix = str(params.get("context_prefix") or step.get("context_prefix") or "Context:\n{context}\n\n")
            assembled = f"{prefix.replace('{context}', context_text)}{prompt}" if context_text else prompt
            return {
                "content": assembled,
                "prompt": prompt,
                "context": context_text,
                "context_name": context_name,
            }
        return None

    @app.post("/api/atomic/scope")
    async def atomic_scope(request: Request) -> dict:
        """Execute a batch of atomic tools in a local scope.
        Only exported variables survive. One request, no round-trips.

        Body:
          steps: [{tool, params, role?, out?, on?, context?, context_grow?}, ...]
          export: ["name1"] or {"out": {"field": "$ref.field"}}
          contexts: {name: text}
          workers: {role: url}
          settings: {temperature, max_tokens, ...}

        Each step's `out` names the result in local scope.
        Steps can reference previous results via $out_name in params.
        `on` (optional): list of $var names that must exist before step runs.
        Steps without `on` run in order. Steps with `on` wait for deps.
        """
        body = await request.json()
        steps = body.get("steps", [])
        export_names = body.get("export", [])
        workers = body.get("workers", {})
        settings = body.get("settings", {})
        initial_contexts = body.get("contexts", {})

        if not steps:
            raise HTTPException(400, "steps is required")

        local_vars: dict[str, dict] = {}  # out_name → result dict
        log: list[str] = []
        if isinstance(initial_contexts, dict):
            for context_name, context_text in initial_contexts.items():
                _scope_set_context(local_vars, str(context_name), context_text)

        def _resolve_params(params_raw: dict, scope_vars: dict[str, Any]) -> dict:
            """Resolve $ref and $ref.field in param values."""
            params = dict(params_raw)
            for k, v in params.items():
                if isinstance(v, str) and v.startswith("$"):
                    ref_name = v[1:]
                    ref_field = None
                    if "." in ref_name:
                        ref_name, ref_field = ref_name.split(".", 1)
                    if ref_name in scope_vars:
                        ref_data = scope_vars[ref_name]
                        if ref_field:
                            params[k] = ref_data.get(ref_field, v)
                        else:
                            params[k] = ref_data.get("content") or ref_data.get("items") or ref_data
                        if isinstance(params[k], list):
                            params[k] = "\n".join(str(x) for x in params[k])
            return params

        def _resolve_ref(ref_str: str, scope_vars: dict[str, Any]) -> Any:
            if not isinstance(ref_str, str) or not ref_str.startswith("$"):
                return ref_str
            path = ref_str[1:]
            parts = path.split(".", 1)
            data = scope_vars.get(parts[0])
            if data is None:
                return ref_str
            if len(parts) > 1:
                return data.get(parts[1], ref_str) if isinstance(data, dict) else ref_str
            return data

        def _truthy(value: Any) -> bool:
            if isinstance(value, dict):
                if "bool" in value:
                    return _truthy(value.get("bool"))
                if "result" in value:
                    return _truthy(value.get("result"))
                if "content" in value:
                    return _truthy(value.get("content"))
                if "items" in value:
                    return _truthy(value.get("items"))
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
            if text in {"false", "no", "0", "fail"}:
                return False
            if text.startswith("$"):
                return False
            return True

        async def _execute_steps(
            step_list: list[dict],
            scope_vars: dict[str, Any],
            step_prefix: str = "",
        ) -> dict | None:
            pending = list(enumerate(step_list))
            max_iterations = len(step_list) * 2 + 10  # safety limit
            iteration = 0
            while pending and iteration < max_iterations:
                iteration += 1
                progress = False
                next_pending = []
                for i, step in pending:
                    deps = step.get("on", [])
                    if deps and not all(d.lstrip("$") in scope_vars for d in deps):
                        next_pending.append((i, step))
                        continue
                    tool = step.get("tool", "")
                    params = _resolve_params(step.get("params", {}), scope_vars)
                    params = _scope_inject_context(step, params, scope_vars)
                    role = step.get("role", "generator")
                    out = step.get("out")
                    try:
                        result = _scope_run_factory_step(step, params, scope_vars)
                        if result is None:
                            result = _run_atomic_tool(tool, params, workers, settings, role)
                            if asyncio.iscoroutine(result):
                                result = await result
                        if out:
                            scope_vars[out] = result
                        _scope_apply_context_growth(step, result, scope_vars)
                        dep_str = f" (on: {', '.join(deps)})" if deps else ""
                        prefix = f"{step_prefix}" if step_prefix else ""
                        context_name = str(step.get("context") or "").strip()
                        context_suffix = f" [ctx:{context_name}]" if context_name else ""
                        log.append(
                            f"{prefix}[{i+1}] {tool}({', '.join(f'{k}={str(v)[:30]}' for k,v in params.items() if k != 'text')}){dep_str}{context_suffix}"
                            + (f" → ${out}" if out else "")
                        )
                        progress = True
                    except Exception as e:
                        log.append(f"{step_prefix}[{i+1}] {tool} ERROR: {e}")
                        return {"status": "error", "error": str(e), "step": i + 1, "log": log}
                pending = next_pending
                if not progress and pending:
                    unmet = [(i, s.get("on", [])) for i, s in pending]
                    log.append(f"{step_prefix}DEADLOCK: {len(pending)} steps waiting — {unmet}")
                    return {"status": "error", "error": "dependency deadlock", "log": log}
            return None

        error = await _execute_steps(steps, local_vars)
        if error:
            return error

        # Export: list format ["name1"] or dict format {"out": {"field": "$ref.field"}}
        exported = {}
        if isinstance(export_names, list):
            for name in export_names:
                if name in local_vars:
                    exported[name] = local_vars[name]
        elif isinstance(export_names, dict):
            for out_name, mapping in export_names.items():
                if isinstance(mapping, dict):
                    # Compose: {"entities": "$ent.items", "axioms": "$ax.items"}
                    composed = {}
                    for field, ref in mapping.items():
                        composed[field] = _scope_resolve_ref(ref, local_vars) if isinstance(ref, str) else ref
                    exported[out_name] = composed
                elif isinstance(mapping, str):
                    # Simple: {"input_constraints": "$ent"}
                    exported[out_name] = _scope_resolve_ref(mapping, local_vars)

        return {"status": "ok", "exported": exported, "log": log, "contexts": _scope_contexts(local_vars)}

    @app.post("/api/atomic/loop")
    async def atomic_loop(request: Request) -> dict:
        """Execute setup once, then loop body while a local condition remains truthy.

        Body:
          setup: [{tool, params, role?, out?, on?, context?, context_grow?}, ...]
          loop: [{tool, params, role?, out?, on?, context?, context_grow?}, ...]
          while: "$var" or "$var.field"
          max_iters: 8
          export: ["name1"] or {"out": {"field": "$ref.field"}}
          contexts: {name: text}
          workers: {role: url}
          settings: {temperature, max_tokens, ...}
        """
        body = await request.json()
        setup_steps = body.get("setup", [])
        loop_steps = body.get("loop", [])
        while_ref = body.get("while")
        max_iters = int(body.get("max_iters", 8) or 8)
        export_names = body.get("export", [])
        workers = body.get("workers", {})
        settings = body.get("settings", {})
        initial_contexts = body.get("contexts", {})

        if not loop_steps:
            raise HTTPException(400, "loop is required")
        if not while_ref:
            raise HTTPException(400, "while is required")

        local_vars: dict[str, Any] = {}
        if isinstance(initial_contexts, dict):
            for context_name, context_text in initial_contexts.items():
                _scope_set_context(local_vars, str(context_name), context_text)
        log: list[str] = []

        def _resolve_params(params_raw: dict, scope_vars: dict[str, Any]) -> dict:
            params = dict(params_raw)
            for k, v in params.items():
                if isinstance(v, str) and v.startswith("$"):
                    ref_name = v[1:]
                    ref_field = None
                    if "." in ref_name:
                        ref_name, ref_field = ref_name.split(".", 1)
                    if ref_name in scope_vars:
                        ref_data = scope_vars[ref_name]
                        if ref_field:
                            params[k] = ref_data.get(ref_field, v)
                        else:
                            params[k] = ref_data.get("content") or ref_data.get("items") or ref_data
                        if isinstance(params[k], list):
                            params[k] = "\n".join(str(x) for x in params[k])
            return params

        def _resolve_ref(ref_str: str, scope_vars: dict[str, Any]) -> Any:
            if not isinstance(ref_str, str) or not ref_str.startswith("$"):
                return ref_str
            path = ref_str[1:]
            parts = path.split(".", 1)
            data = scope_vars.get(parts[0])
            if data is None:
                return ref_str
            if len(parts) > 1:
                return data.get(parts[1], ref_str) if isinstance(data, dict) else ref_str
            return data

        def _truthy(value: Any) -> bool:
            if isinstance(value, dict):
                if "bool" in value:
                    return _truthy(value.get("bool"))
                if "result" in value:
                    return _truthy(value.get("result"))
                if "content" in value:
                    return _truthy(value.get("content"))
                if "items" in value:
                    return _truthy(value.get("items"))
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
            if text in {"false", "no", "0", "fail"}:
                return False
            if text.startswith("$"):
                return False
            return True

        async def _execute_steps(
            step_list: list[dict],
            scope_vars: dict[str, Any],
            step_prefix: str = "",
        ) -> dict | None:
            pending = list(enumerate(step_list))
            guard_limit = len(step_list) * 2 + 10
            passes = 0
            while pending and passes < guard_limit:
                passes += 1
                progress = False
                next_pending = []
                for i, step in pending:
                    deps = step.get("on", [])
                    if deps and not all(d.lstrip("$") in scope_vars for d in deps):
                        next_pending.append((i, step))
                        continue
                    tool = step.get("tool", "")
                    params = _resolve_params(step.get("params", {}), scope_vars)
                    params = _scope_inject_context(step, params, scope_vars)
                    role = step.get("role", "generator")
                    out = step.get("out")
                    try:
                        result = _scope_run_factory_step(step, params, scope_vars)
                        if result is None:
                            result = _run_atomic_tool(tool, params, workers, settings, role)
                            if asyncio.iscoroutine(result):
                                result = await result
                        if out:
                            scope_vars[out] = result
                        _scope_apply_context_growth(step, result, scope_vars)
                        dep_str = f" (on: {', '.join(deps)})" if deps else ""
                        context_name = str(step.get("context") or "").strip()
                        context_suffix = f" [ctx:{context_name}]" if context_name else ""
                        log.append(
                            f"{step_prefix}[{i+1}] {tool}({', '.join(f'{k}={str(v)[:30]}' for k,v in params.items() if k != 'text')}){dep_str}{context_suffix}"
                            + (f" → ${out}" if out else "")
                        )
                        progress = True
                    except Exception as e:
                        log.append(f"{step_prefix}[{i+1}] {tool} ERROR: {e}")
                        return {"status": "error", "error": str(e), "step": i + 1, "log": log}
                pending = next_pending
                if not progress and pending:
                    unmet = [(i, s.get("on", [])) for i, s in pending]
                    log.append(f"{step_prefix}DEADLOCK: {len(pending)} steps waiting — {unmet}")
                    return {"status": "error", "error": "dependency deadlock", "log": log}
            return None

        if setup_steps:
            error = await _execute_steps(setup_steps, local_vars, step_prefix="setup ")
            if error:
                return error

        iterations = 0
        while _truthy(_scope_resolve_ref(while_ref, local_vars)):
            if iterations >= max_iters:
                log.append(f"LOOP LIMIT: max_iters={max_iters}")
                return {"status": "error", "error": "loop iteration limit reached", "log": log}
            error = await _execute_steps(loop_steps, local_vars, step_prefix=f"loop#{iterations + 1} ")
            if error:
                return error
            iterations += 1

        exported = {}
        if isinstance(export_names, list):
            for name in export_names:
                if name in local_vars:
                    exported[name] = local_vars[name]
        elif isinstance(export_names, dict):
            for out_name, mapping in export_names.items():
                if isinstance(mapping, dict):
                    composed = {}
                    for field, ref in mapping.items():
                        composed[field] = _scope_resolve_ref(ref, local_vars) if isinstance(ref, str) else ref
                    exported[out_name] = composed
                elif isinstance(mapping, str):
                    exported[out_name] = _scope_resolve_ref(mapping, local_vars)

        return {
            "status": "ok",
            "iterations": iterations,
            "exported": exported,
            "log": log,
            "contexts": _scope_contexts(local_vars),
        }

    def _run_atomic_tool(
        tool: str,
        params: dict,
        workers: dict,
        settings: dict,
        role: str,
    ) -> dict:
        """Dispatch atomic tool. Returns dict with tool-specific results."""
        if tool == "slice":
            return _atomic_slice(params)
        elif tool == "split":
            return _atomic_split(params)
        elif tool == "parse":
            return _atomic_parse(params)
        elif tool == "generate":
            return _atomic_generate(params, workers, settings, role)
        elif tool == "claims":
            return _atomic_claims(params, workers, settings, role)
        elif tool == "render":
            return _atomic_render(params)
        elif tool == "tag":
            return _atomic_tag(params)
        elif tool in ("remove_tag", "untag"):
            return _atomic_remove_tag(params)
        elif tool == "set_text":
            return _atomic_set_text(params)
        elif tool == "append_text":
            return _atomic_append_text(params)
        elif tool == "table_header":
            return _atomic_table_header(params)
        elif tool == "reshape_grid":
            return _atomic_reshape_grid(params)
        elif tool in ("join", "join_list"):
            return _atomic_join(params)
        else:
            raise ValueError(f"Unknown tool: {tool}")

    def _atomic_slice(params: dict) -> dict:
        """Slice text between two delimiters.
        params: {text, from_delim, to_delim?}
        """
        text = params.get("text", "")
        from_delim = params.get("from_delim", "")
        to_delim = params.get("to_delim")

        if not text:
            raise ValueError("text is required")
        if not from_delim:
            raise ValueError("from_delim is required")

        from_idx = text.find(from_delim)
        if from_idx < 0:
            raise ValueError(f'delimiter "{from_delim}" not found')

        content_start = from_idx + len(from_delim)
        content_end = len(text)
        if to_delim:
            to_idx = text.find(to_delim, content_start)
            if to_idx >= 0:
                content_end = to_idx

        sliced = text[content_start:content_end].strip()
        return {"content": sliced, "from_delim": from_delim, "to_delim": to_delim}

    def _atomic_split(params: dict) -> dict:
        """Split text into items. Auto-detects [a,b] or - item format.
        params: {text, separator?}
        """
        text = params.get("text", "")
        if not text:
            raise ValueError("text is required")

        _re = re

        # Try bracket list: [a, b, c]
        bracket = _re.search(r"\[([^\]]+)\]", text)
        if bracket:
            items = [s.strip() for s in bracket.group(1).split(",") if s.strip()]
            return {"items": items, "format": "bracket"}

        # Try bullet list: - item or • item
        lines = text.strip().split("\n")
        items = []
        for line in lines:
            cleaned = _re.sub(r"^[-•*]\s*", "", line.strip())
            if cleaned:
                items.append(cleaned)
        return {"items": items, "format": "lines"}

    def _atomic_parse(params: dict) -> dict:
        """Slice between delimiters + split into items. Combines slice+split.
        params: {text, from_delim, to_delim?}
        Returns: {content (raw slice), items (parsed list), format}
        """
        # Step 1: slice
        sliced = _atomic_slice(params)
        # Step 2: split the sliced content
        split_result = _atomic_split({"text": sliced["content"]})
        return {
            "content": sliced["content"],
            "items": split_result["items"],
            "format": split_result["format"],
            "from_delim": params.get("from_delim"),
            "to_delim": params.get("to_delim"),
        }

    def _atomic_render(params: dict) -> dict:
        """Pure text template rendering with slot substitution.
        params: {template, slots: {key: value, ...}}
        Replaces @key in template with corresponding value.
        """
        template = params.get("template", "")
        slots = params.get("slots", {})
        if not template:
            raise ValueError("template is required")
        import re
        result = template
        for _pass in range(3):  # multi-pass for nested refs
            changed = False
            for key, val in slots.items():
                pattern = re.compile(r"@" + re.escape(key) + r"\b")
                new_result = pattern.sub(str(val), result)
                if new_result != result:
                    result = new_result
                    changed = True
            if not changed:
                break
        return {"content": result, "slots_applied": list(slots.keys())}

    def _atomic_tag(params: dict) -> dict:
        """Add tag to entity. params: {entity, key, value}"""
        entity = params.get("entity", "")
        key = params.get("key", "")
        value = params.get("value", "")
        if not entity or not key:
            raise ValueError("entity and key are required")
        return {"entity": entity, "tag": {"key": key, "value": value}}

    def _atomic_remove_tag(params: dict) -> dict:
        """Remove tag from entity. params: {entity, key}"""
        entity = params.get("entity", "")
        key = params.get("key", "")
        if not entity or not key:
            raise ValueError("entity and key are required")
        return {"entity": entity, "removed_key": key}

    def _atomic_set_text(params: dict) -> dict:
        """Set text area content. params: {entity, area, text}"""
        entity = params.get("entity", "")
        area = params.get("area", "content")
        text = params.get("text", "")
        if not entity:
            raise ValueError("entity is required")
        return {"entity": entity, "area": area, "text": text}

    def _atomic_append_text(params: dict) -> dict:
        """Append to text area. params: {entity, area, text}"""
        entity = params.get("entity", "")
        area = params.get("area", "content")
        text = params.get("text", "")
        if not entity:
            raise ValueError("entity is required")
        return {"entity": entity, "area": area, "text": text, "mode": "append"}

    def _atomic_table_header(params: dict) -> dict:
        """Build table header from entity lists.
        params: {columns: [...], rows: [...]}
        Returns: {headers: [...], template_rows: [...]}
        """
        columns = params.get("columns", [])
        rows = params.get("rows", [])
        if not columns:
            raise ValueError("columns list is required")
        # Build header row + empty template rows
        template_rows = []
        for row_label in rows:
            template_rows.append([row_label] + ["" for _ in columns])
        return {
            "headers": [""] + columns,
            "rows": template_rows,
            "cols_count": len(columns),
            "rows_count": len(rows)
        }

    def _atomic_reshape_grid(params: dict) -> dict:
        """Reshape flat list into grid. params: {items: [...], cols: N}"""
        items = params.get("items", [])
        cols = int(params.get("cols", 2))
        if cols < 1:
            cols = 1
        grid = []
        for i in range(0, len(items), cols):
            grid.append(items[i:i + cols])
        # Pad last row if needed
        if grid and len(grid[-1]) < cols:
            grid[-1].extend([""] * (cols - len(grid[-1])))
        return {"grid": grid, "cols": cols, "rows": len(grid), "total": len(items)}

    def _atomic_join(params: dict) -> dict:
        """Join list items into string. params: {items: [...], sep: str}"""
        items = params.get("items", [])
        sep = params.get("sep", ", ")
        result = sep.join(str(i) for i in items)
        return {"content": result, "count": len(items)}

    async def _atomic_generate(
        params: dict, workers: dict, settings: dict, role: str
    ) -> dict:
        """Generate via LLM worker.
        params: {messages, mode?, grammar?, stop?, capture?, coerce?, format?}
        """
        messages = params.get("messages", [])
        if not messages:
            raise ValueError("messages is required")

        base_url = workers.get(role, "").rstrip("/")
        if not base_url:
            raise ValueError(f"No worker for role '{role}'")

        temperature = float(settings.get("temperature", 0.6))
        max_tokens = int(settings.get("max_tokens", 2048))
        no_think = settings.get("no_think", True)
        max_cont = int(settings.get("max_continue", 20))
        continue_on = settings.get("continue", no_think)
        grammar = params.get("grammar")
        prompt_mode = str(params.get("format") or params.get("prompt_mode") or "auto").strip().lower()
        stop = params.get("stop")
        if stop and not isinstance(stop, list):
            stop = [stop]

        # until_contains / until_regex / min_chars — post-loop conditions
        until_contains = params.get("until_contains")
        if until_contains is None and params.get("until") is not None:
            until_contains = params.get("until")
        if isinstance(until_contains, str):
            until_contains = [until_contains]
        elif not isinstance(until_contains, list):
            until_contains = []
        until_regex = params.get("until_regex")
        min_chars = int(params.get("min_chars", 0) or 0)
        has_post_conditions = bool(until_contains or until_regex or min_chars)

        def _continue_conditions_met(text: str) -> bool:
            if min_chars and len(text or "") < min_chars:
                return False
            if until_contains and not all(str(needle) in (text or "") for needle in until_contains):
                return False
            if until_regex and not re.search(until_regex, text or ""):
                return False
            return True

        # If there are post-conditions, we need a custom loop; otherwise delegate fully
        if has_post_conditions:
            # Custom loop: keep calling until post-conditions met OR max_continue
            res = llm_call_with_continue(
                base_url, messages,
                temperature=temperature, max_tokens=max_tokens,
                no_think=no_think, max_continue=0,  # single shot first
                continue_on_length=False,
                stop=stop, grammar=grammar,
                prompt_mode=prompt_mode,
            )
            result = res.raw
            raw_responses = list(res.raw_responses)
            finish = res.finish_reason

            if continue_on:
                for i in range(max_cont):
                    if not (finish in ("length", "max_tokens") or not _continue_conditions_met(result)):
                        break
                    next_res = llm_call_with_continue(
                        base_url,
                        [*messages, {"role": "assistant", "content": result}],
                        temperature=temperature, max_tokens=max_tokens,
                        no_think=False,  # prefill already in result
                        max_continue=0, continue_on_length=False,
                        stop=stop, grammar=grammar,
                        extra_payload={"continue_assistant_turn": True},
                        prompt_mode=prompt_mode,
                    )
                    result += next_res.raw
                    raw_responses.extend(next_res.raw_responses)
                    finish = next_res.finish_reason

            answer, think = strip_think(result)
            latency_ms = res.latency_ms
        else:
            res = llm_call_with_continue(
                base_url, messages,
                temperature=temperature, max_tokens=max_tokens,
                no_think=no_think, max_continue=max_cont,
                continue_on_length=bool(continue_on),
                stop=stop, grammar=grammar,
                prompt_mode=prompt_mode,
            )
            result = res.raw
            raw_responses = res.raw_responses
            answer, think = res.answer, res.think
            latency_ms = res.latency_ms

        # Apply capture regex
        captured = None
        if params.get("capture"):
            m = re.search(params["capture"], result)
            if m:
                captured = m.group(0)
                if params.get("coerce") == "int":
                    captured = int(captured)

        usage = raw_responses[-1].get("usage", {}) if raw_responses else {}
        return {
            "content": answer,
            "think": think,
            "captured": captured,
            "continues": max(0, len(raw_responses) - 1),
            "latency_ms": latency_ms,
            "prompt_mode": res.prompt_mode,
            "tokens": {
                "prompt": usage.get("prompt_tokens"),
                "completion": usage.get("completion_tokens"),
            },
        }

    async def _atomic_claims(
        params: dict, workers: dict, settings: dict, role: str
    ) -> dict:
        """Extract claims via LLM. Returns parsed entities/axioms/hypotheses.
        params: {text, prompt_template?}
        """
        text = params.get("text", "")
        if not text:
            raise ValueError("text is required")

        prompt_template = params.get("prompt_template",
            "Ты — логический аналитик. Извлеки все атомарные утверждения/факты из текста.\n"
            "Верни ТОЛЬКО в формате:\nENTITIES: [сущность1, сущность2, ...]\n"
            "AXIOMS:\n- утверждение 1\n- утверждение 2\n"
            "HYPOTHESES:\n- гипотеза 1\n\n"
            "Требования:\n- AXIOMS = факты, данные как условие.\n"
            "- HYPOTHESES = выводы, предположения.\n"
            "- Каждое утверждение атомарное и короткое.\n"
            "- Не выводи прозу или JSON.\n- Отвечай на языке текста.\n\n"
            "Текст для анализа:\n@input"
        )
        prompt = prompt_template.replace("@input", text)

        gen_result = await _atomic_generate(
            {"messages": [{"role": "user", "content": prompt}], "mode": "prompt"},
            workers, {**settings, "temperature": 0.1, "no_think": True}, role or "analyzer"
        )
        answer = gen_result.get("content", "")

        # Parse sections from answer
        _re = re
        sections = {}
        # Find all SECTION_NAME: headers
        header_pattern = _re.compile(r"^([A-Z_]+)\s*:", _re.MULTILINE)
        matches = list(header_pattern.finditer(answer))
        for i, m in enumerate(matches):
            name = m.group(1).lower()
            start = m.end()
            end = matches[i + 1].start() if i + 1 < len(matches) else len(answer)
            section_text = answer[start:end].strip()
            # Parse bracket or bullet list
            bracket = _re.search(r"\[([^\]]+)\]", section_text)
            if bracket:
                items = [s.strip() for s in bracket.group(1).split(",") if s.strip()]
            else:
                items = [_re.sub(r"^[-•*]\s*", "", l.strip()) for l in section_text.split("\n") if l.strip()]
            sections[name] = items

        return {
            "content": answer,
            "sections": sections,
            "latency_ms": gen_result.get("latency_ms"),
            "tokens": gen_result.get("tokens"),
        }

    ui_proto_root = Path(root).resolve() / "ui_proto"
    ui_proto_layout_path = ui_proto_root / "layout.yaml"
    ui_proto_nodes_dir = ui_proto_root / "nodes"
    ui_proto_undo_stack: list[tuple[LayoutDocument, dict[str, NodeMeta], str | None]] = []
    ui_proto_last_diff: list[dict[str, Any]] = []
    ui_proto_last_snap_debug: dict[str, Any] = {}
    ui_proto2_root = Path(root).resolve() / "ui_proto_reactive"
    ui_proto2_undo_stack: list[tuple[dict[str, Any], str | None, str | None]] = []
    ui_proto2_last_diff: list[dict[str, Any]] = []

    def _default_ui_proto_docs() -> tuple[LayoutDocument, dict[str, NodeMeta]]:
        layout_doc = LayoutDocument(
            screen=ScreenSpec(cols=120, rows=36, root="root"),
            nodes={
                "root": LayoutNode(
                    id="root",
                    kind="screen",
                    rect=Rect(0, 0, 120, 36),
                    parent=None,
                    children=["status_bar", "worker_panel", "chat_feed", "chat_input", "send_button"],
                ),
                "status_bar": LayoutNode(
                    id="status_bar",
                    kind="panel",
                    rect=Rect(0, 0, 120, 3),
                    parent="root",
                    children=[],
                ),
                "worker_panel": LayoutNode(
                    id="worker_panel",
                    kind="panel",
                    rect=Rect(0, 3, 30, 29),
                    parent="root",
                    children=[],
                ),
                "chat_feed": LayoutNode(
                    id="chat_feed",
                    kind="panel",
                    rect=Rect(30, 3, 90, 29),
                    parent="root",
                    children=[],
                ),
                "chat_input": LayoutNode(
                    id="chat_input",
                    kind="panel",
                    rect=Rect(0, 32, 104, 4),
                    parent="root",
                    children=[],
                ),
                "send_button": LayoutNode(
                    id="send_button",
                    kind="panel",
                    rect=Rect(104, 32, 16, 4),
                    parent="root",
                    children=[],
                ),
            },
        )
        node_meta = {
            "root": NodeMeta(title="Root", role="screen.root", kind="screen"),
            "status_bar": NodeMeta(
                title="Status",
                role="panel.status",
                kind="panel",
                renderer="utf_panel",
                props={"preview_lines": ["thin client / utf proto", "worker + chat skeleton"]},
            ),
            "worker_panel": NodeMeta(
                title="Workers",
                role="panel.workers",
                kind="panel",
                renderer="utf_list",
                data={"workers": {"method": "GET", "path": "/api/behavior/agents"}},
                bind={"items": "workers.agents"},
                props={"bullet": "•", "preview_lines": ["items <- workers.agents"]},
            ),
            "chat_feed": NodeMeta(
                title="Chat",
                role="panel.chat_feed",
                kind="panel",
                renderer="utf_log",
                data={"chat_log": {"method": "GET", "path": "/api/chat/log", "query": {"session_id": "default"}}},
                bind={"items": "chat_log.entries"},
                props={"preview_lines": ["log <- chat_log.entries"]},
            ),
            "chat_input": NodeMeta(
                title="Input",
                role="input.chat",
                kind="panel",
                renderer="utf_input",
                props={"placeholder": "Describe your task...", "value": ""},
            ),
            "send_button": NodeMeta(
                title="Send",
                role="action.send",
                kind="panel",
                renderer="utf_button",
                props={"text": "Send"},
                actions={
                    "press": {
                        "method": "POST",
                        "path": "/api/chat",
                        "body": {"session_id": "default", "message_from_panel": "chat_input"},
                        "after": [
                            {"refresh_panel": "chat_feed"},
                            {"set_panel_prop": {"panel": "chat_input", "key": "value", "value": ""}},
                        ],
                    }
                },
            ),
        }
        return layout_doc, node_meta

    def _ensure_ui_proto_files() -> None:
        if ui_proto_layout_path.exists():
            return
        ui_proto_root.mkdir(parents=True, exist_ok=True)
        layout_doc, node_meta = _default_ui_proto_docs()
        save_ui(ui_proto_layout_path, ui_proto_nodes_dir, layout_doc, node_meta)

    def _load_ui_proto_runtime() -> tuple[LayoutDocument, dict[str, NodeMeta], UiRuntime]:
        _ensure_ui_proto_files()
        loaded = load_ui(ui_proto_layout_path, ui_proto_nodes_dir)
        runtime = build_ui_runtime(loaded.layout_doc, loaded.node_meta)
        return loaded.layout_doc, loaded.node_meta, runtime

    def _ui_proto_depth(runtime: UiRuntime, node_id: str) -> int:
        depth = 0
        current = runtime.nodes.get(node_id)
        while current is not None and current.parent is not None:
            depth += 1
            current = runtime.nodes.get(current.parent)
        return depth

    def _ui_proto_pick(runtime: UiRuntime, x: int, y: int) -> str | None:
        hits: list[tuple[int, int, str]] = []
        for node in runtime.nodes.values():
            if node.kind == "screen":
                continue
            if node.rect.x <= x < node.rect.right and node.rect.y <= y < node.rect.bottom:
                area = node.rect.w * node.rect.h
                depth = _ui_proto_depth(runtime, node.id)
                hits.append((area, -depth, node.id))
        if not hits:
            return None
        hits.sort()
        return hits[0][2]

    def _ui_proto_is_descendant(layout_doc: LayoutDocument, node_id: str, ancestor_id: str) -> bool:
        current = layout_doc.nodes.get(node_id)
        while current is not None:
            if current.id == ancestor_id:
                return True
            if current.parent is None:
                return False
            current = layout_doc.nodes.get(current.parent)
        return False

    def _ui_proto_resolve_focus(layout_doc: LayoutDocument, focus_id: str | None) -> str:
        if focus_id and focus_id in layout_doc.nodes:
            return focus_id
        return layout_doc.screen.root

    def _ui_proto_local_rect(rect: Rect, focus_rect: Rect) -> list[int]:
        return [rect.x - focus_rect.x, rect.y - focus_rect.y, rect.w, rect.h]

    def _ui_proto_meta_yaml(node_meta: dict[str, NodeMeta], node_id: str | None) -> str:
        if not node_id:
            return ""
        meta = node_meta.get(node_id, NodeMeta())
        payload = {
            "title": meta.title,
            "role": meta.role,
            "kind": meta.kind,
            "renderer": meta.renderer,
            "data": dict(meta.data),
            "bind": dict(meta.bind),
            "actions": dict(meta.actions),
            "view": dict(meta.view),
            "binding": dict(meta.binding),
            "events": dict(meta.events),
            "nlp": {
                "synonyms": list(meta.nlp.synonyms),
                "description": meta.nlp.description,
                "tags": list(meta.nlp.tags),
            },
            "props": dict(meta.props),
        }
        return yaml.safe_dump(payload, sort_keys=False, allow_unicode=True)

    def _ui_proto_tree_payload(layout_doc: LayoutDocument, focus_id: str) -> list[dict[str, Any]]:
        ordered: list[dict[str, Any]] = []
        focus_rect = layout_doc.nodes[focus_id].rect

        def visit(node_id: str, depth: int) -> None:
            node = layout_doc.nodes[node_id]
            ordered.append(
                {
                    "id": node.id,
                    "kind": node.kind,
                    "depth": depth,
                    "children": list(node.children),
                    "rect": _ui_proto_local_rect(node.rect, focus_rect),
                }
            )
            for child_id in node.children:
                if child_id in layout_doc.nodes:
                    visit(child_id, depth + 1)

        visit(focus_id, 0)
        return ordered

    def _ui_proto_diff_payload() -> list[dict[str, Any]]:
        return list(ui_proto_last_diff)

    def _ui_proto_snap_rect(
        layout_doc: LayoutDocument,
        *,
        node_id: str | None,
        parent_id: str | None,
        rect: Rect,
        threshold: int = 1,
    ) -> tuple[Rect, dict[str, Any]]:
        snapped = Rect(rect.x, rect.y, rect.w, rect.h)
        targets: list[dict[str, Any]] = []
        if parent_id and parent_id in layout_doc.nodes:
            parent = layout_doc.nodes[parent_id]
            if abs(snapped.x - parent.rect.x) <= threshold:
                snapped = Rect(parent.rect.x, snapped.y, snapped.w, snapped.h)
                targets.append({"side": "left", "target": f"{parent.id}.left"})
            if abs(snapped.y - parent.rect.y) <= threshold:
                snapped = Rect(snapped.x, parent.rect.y, snapped.w, snapped.h)
                targets.append({"side": "top", "target": f"{parent.id}.top"})
            if abs(snapped.right - parent.rect.right) <= threshold:
                snapped = Rect(parent.rect.right - snapped.w, snapped.y, snapped.w, snapped.h)
                targets.append({"side": "right", "target": f"{parent.id}.right"})
            if abs(snapped.bottom - parent.rect.bottom) <= threshold:
                snapped = Rect(snapped.x, parent.rect.bottom - snapped.h, snapped.w, snapped.h)
                targets.append({"side": "bottom", "target": f"{parent.id}.bottom"})
            for sibling_id in parent.children:
                if sibling_id == node_id or sibling_id not in layout_doc.nodes:
                    continue
                sibling = layout_doc.nodes[sibling_id]
                overlap_y = min(snapped.bottom, sibling.rect.bottom) - max(snapped.y, sibling.rect.y)
                overlap_x = min(snapped.right, sibling.rect.right) - max(snapped.x, sibling.rect.x)
                if overlap_y >= 1:
                    if abs(snapped.x - sibling.rect.right) <= threshold:
                        snapped = Rect(sibling.rect.right, snapped.y, snapped.w, snapped.h)
                        targets.append({"side": "left", "target": f"{sibling.id}.right"})
                    if abs(snapped.right - sibling.rect.x) <= threshold:
                        snapped = Rect(sibling.rect.x - snapped.w, snapped.y, snapped.w, snapped.h)
                        targets.append({"side": "right", "target": f"{sibling.id}.left"})
                if overlap_x >= 1:
                    if abs(snapped.y - sibling.rect.bottom) <= threshold:
                        snapped = Rect(snapped.x, sibling.rect.bottom, snapped.w, snapped.h)
                        targets.append({"side": "top", "target": f"{sibling.id}.bottom"})
                    if abs(snapped.bottom - sibling.rect.y) <= threshold:
                        snapped = Rect(snapped.x, sibling.rect.y - snapped.h, snapped.w, snapped.h)
                        targets.append({"side": "bottom", "target": f"{sibling.id}.top"})
        return snapped, {
            "applied": bool(targets),
            "raw_rect": rect.to_list(),
            "snapped_rect": snapped.to_list(),
            "targets": targets,
        }

    def _ui_proto_parse_rect(raw_rect: list[int] | None) -> Rect:
        if not isinstance(raw_rect, list) or len(raw_rect) != 4 or not all(isinstance(v, int) for v in raw_rect):
            raise HTTPException(status_code=400, detail="rect must be [x, y, w, h]")
        rect = Rect(x=raw_rect[0], y=raw_rect[1], w=raw_rect[2], h=raw_rect[3])
        if rect.w <= 0 or rect.h <= 0:
            raise HTTPException(status_code=400, detail="rect must have positive width and height")
        return rect

    def _ui_proto_global_rect(layout_doc: LayoutDocument, focus_id: str, local_rect: Rect) -> Rect:
        focus_rect = layout_doc.nodes[focus_id].rect
        return Rect(
            x=focus_rect.x + local_rect.x,
            y=focus_rect.y + local_rect.y,
            w=local_rect.w,
            h=local_rect.h,
        )

    def _ui_proto_next_id(layout_doc: LayoutDocument, base: str = "panel") -> str:
        candidate_base = re.sub(r"[^a-zA-Z0-9_]+", "_", base).strip("_") or "panel"
        if candidate_base not in layout_doc.nodes:
            return candidate_base
        index = 1
        while f"{candidate_base}_{index}" in layout_doc.nodes:
            index += 1
        return f"{candidate_base}_{index}"

    def _ui_proto_node_meta_to_patch(meta: NodeMeta) -> dict[str, Any]:
        return {
            "title": meta.title,
            "role": meta.role,
            "kind": meta.kind,
            "renderer": meta.renderer,
            "data": dict(meta.data),
            "bind": dict(meta.bind),
            "actions": dict(meta.actions),
            "view": dict(meta.view),
            "binding": dict(meta.binding),
            "events": dict(meta.events),
            "nlp": {
                "synonyms": list(meta.nlp.synonyms),
                "description": meta.nlp.description,
                "tags": list(meta.nlp.tags),
            },
            "props": dict(meta.props),
        }

    def _ui_proto_parse_meta_yaml(yaml_text: str) -> NodeMeta:
        try:
            data = yaml.safe_load(yaml_text) or {}
        except yaml.YAMLError as exc:
            raise HTTPException(status_code=400, detail=f"invalid YAML: {exc}") from exc
        if not isinstance(data, dict):
            raise HTTPException(status_code=400, detail="meta YAML must be a mapping")
        nlp_raw = data.get("nlp") or {}
        if not isinstance(nlp_raw, dict):
            raise HTTPException(status_code=400, detail="nlp must be a mapping")
        synonyms = nlp_raw.get("synonyms") or []
        tags = nlp_raw.get("tags") or []
        if not isinstance(synonyms, list) or not all(isinstance(v, str) for v in synonyms):
            raise HTTPException(status_code=400, detail="nlp.synonyms must be a list of strings")
        if not isinstance(tags, list) or not all(isinstance(v, str) for v in tags):
            raise HTTPException(status_code=400, detail="nlp.tags must be a list of strings")
        for key in ("data", "bind", "actions", "view", "binding", "events", "props"):
            value = data.get(key) or {}
            if not isinstance(value, dict):
                raise HTTPException(status_code=400, detail=f"{key} must be a mapping")
        return NodeMeta(
            title=str(data.get("title") or ""),
            role=str(data.get("role") or "node.unknown"),
            kind=str(data.get("kind") or "panel"),
            renderer=str(data.get("renderer") or "utf_panel"),
            data=dict(data.get("data") or {}),
            bind=dict(data.get("bind") or {}),
            actions=dict(data.get("actions") or {}),
            view=dict(data.get("view") or {}),
            binding=dict(data.get("binding") or {}),
            events=dict(data.get("events") or {}),
            nlp=NlpMeta(
                synonyms=list(synonyms),
                description=str(nlp_raw.get("description") or ""),
                tags=list(tags),
            ),
            props=dict(data.get("props") or {}),
        )

    def _ui_proto_response(
        layout_doc: LayoutDocument,
        node_meta: dict[str, NodeMeta],
        runtime: UiRuntime,
        *,
        selected_id: str | None,
        focus_id: str | None = None,
        message: str | None = None,
    ) -> dict[str, Any]:
        resolved_focus = _ui_proto_resolve_focus(layout_doc, focus_id)
        if selected_id in runtime.nodes and _ui_proto_is_descendant(layout_doc, selected_id, resolved_focus):
            resolved_selected = selected_id
        else:
            resolved_selected = resolved_focus
        render = render_utf_runtime(runtime, resolved_selected, root_id=resolved_focus)
        selected_node = runtime.nodes.get(resolved_selected)
        focus_node = runtime.nodes.get(resolved_focus)
        focus_rect = focus_node.rect if focus_node is not None else Rect(0, 0, runtime.cols, runtime.rows)
        return {
            "ok": True,
            "message": message or "",
            "selected_id": resolved_selected,
            "focus_id": resolved_focus,
            "screen": {"cols": render.cols, "rows": render.rows},
            "render": {"lines": render.lines},
            "tree": _ui_proto_tree_payload(layout_doc, resolved_focus),
            "selected": {
                "id": resolved_selected,
                "kind": selected_node.kind if selected_node else "",
                "title": selected_node.title if selected_node else "",
                "role": selected_node.role if selected_node else "",
                "renderer": selected_node.renderer if selected_node else "",
                "rect": _ui_proto_local_rect(selected_node.rect, focus_rect) if selected_node else [0, 0, 0, 0],
                "meta_yaml": _ui_proto_meta_yaml(node_meta, resolved_selected),
                "meta_json": _serialize(_ui_proto_node_meta_to_patch(node_meta.get(resolved_selected, NodeMeta()))),
                "resolved": _serialize(selected_node.resolved if selected_node else {}),
            },
            "focus": {
                "id": resolved_focus,
                "title": focus_node.title if focus_node else "",
            },
            "latest_diff": _ui_proto_diff_payload(),
            "snap_debug": dict(ui_proto_last_snap_debug),
        }

    @app.get("/api/ui-proto/state")
    def ui_proto_state(selected_id: str | None = None, focus_id: str | None = None) -> dict[str, Any]:
        if not _UI_PROTO_AVAILABLE:
            raise _legacy_ui_unavailable("/api/ui-proto/*")
        layout_doc, node_meta, runtime = _load_ui_proto_runtime()
        return _ui_proto_response(layout_doc, node_meta, runtime, selected_id=selected_id, focus_id=focus_id)

    @app.post("/api/ui-proto/select")
    def ui_proto_select(request: UiProtoSelectRequest) -> dict[str, Any]:
        if not _UI_PROTO_AVAILABLE:
            raise _legacy_ui_unavailable("/api/ui-proto/*")
        layout_doc, node_meta, runtime = _load_ui_proto_runtime()
        resolved_focus = _ui_proto_resolve_focus(layout_doc, request.focus_id)
        focus_rect = layout_doc.nodes[resolved_focus].rect
        picked = _ui_proto_pick(runtime, focus_rect.x + request.x, focus_rect.y + request.y)
        selected_id = picked or request.selected_id or resolved_focus
        return _ui_proto_response(layout_doc, node_meta, runtime, selected_id=selected_id, focus_id=resolved_focus)

    @app.post("/api/ui-proto/gui-action")
    def ui_proto_gui_action(request: UiProtoGuiActionRequest) -> dict[str, Any]:
        if not _UI_PROTO_AVAILABLE:
            raise _legacy_ui_unavailable("/api/ui-proto/*")
        nonlocal ui_proto_last_diff, ui_proto_last_snap_debug
        layout_doc, node_meta, runtime = _load_ui_proto_runtime()
        resolved_focus = _ui_proto_resolve_focus(layout_doc, request.focus_id)
        action = request.action.strip().lower()
        ops: list[Any] = []
        next_selected = request.selected_id or resolved_focus

        if action == "move":
            node_id = request.selected_id or ""
            if node_id not in layout_doc.nodes:
                raise HTTPException(status_code=400, detail="selected_id is required for move")
            rect = _ui_proto_global_rect(layout_doc, resolved_focus, _ui_proto_parse_rect(request.rect))
            current = layout_doc.nodes[node_id]
            snapped_rect, ui_proto_last_snap_debug = _ui_proto_snap_rect(
                layout_doc,
                node_id=node_id,
                parent_id=current.parent,
                rect=rect,
            )
            dx = snapped_rect.x - current.rect.x
            dy = snapped_rect.y - current.rect.y
            ops = [MoveNodeOp(node_id, dx, dy)]
            next_selected = node_id
        elif action == "resize":
            node_id = request.selected_id or ""
            if node_id not in layout_doc.nodes:
                raise HTTPException(status_code=400, detail="selected_id is required for resize")
            rect = _ui_proto_global_rect(layout_doc, resolved_focus, _ui_proto_parse_rect(request.rect))
            current = layout_doc.nodes[node_id]
            snapped_rect, ui_proto_last_snap_debug = _ui_proto_snap_rect(
                layout_doc,
                node_id=node_id,
                parent_id=current.parent,
                rect=rect,
            )
            ops = [SetNodeRectOp(node_id, snapped_rect)]
            next_selected = node_id
        elif action == "create":
            rect = _ui_proto_global_rect(layout_doc, resolved_focus, _ui_proto_parse_rect(request.rect))
            parent_id = request.parent_id or request.selected_id or resolved_focus
            if parent_id not in layout_doc.nodes:
                raise HTTPException(status_code=400, detail=f"unknown parent_id '{parent_id}'")
            node_id = request.node_id or _ui_proto_next_id(layout_doc, request.kind)
            snapped_rect, ui_proto_last_snap_debug = _ui_proto_snap_rect(
                layout_doc,
                node_id=None,
                parent_id=parent_id,
                rect=rect,
            )
            ops = [AddNodeOp(node_id, parent_id, request.kind or "panel", snapped_rect)]
            next_selected = node_id
        else:
            raise HTTPException(status_code=400, detail=f"unsupported gui action '{request.action}'")

        ui_proto_undo_stack.append((copy.deepcopy(layout_doc), copy.deepcopy(node_meta), request.selected_id))
        try:
            applied = apply_patch_ops(layout_doc, node_meta, ops)
        except UiLayoutError as exc:
            ui_proto_undo_stack.pop()
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        save_ui(ui_proto_layout_path, ui_proto_nodes_dir, applied.layout_doc, applied.node_meta)
        ui_proto_last_diff = [_serialize(op) for op in ops]
        return _ui_proto_response(
            applied.layout_doc,
            applied.node_meta,
            applied.runtime,
            selected_id=next_selected,
            focus_id=resolved_focus,
            message=f"gui {action} applied",
        )

    @app.post("/api/ui-proto/meta")
    def ui_proto_save_meta(request: UiProtoMetaSaveRequest) -> dict[str, Any]:
        if not _UI_PROTO_AVAILABLE:
            raise _legacy_ui_unavailable("/api/ui-proto/*")
        nonlocal ui_proto_last_diff, ui_proto_last_snap_debug
        layout_doc, node_meta, runtime = _load_ui_proto_runtime()
        if request.selected_id not in layout_doc.nodes:
            raise HTTPException(status_code=400, detail=f"unknown node '{request.selected_id}'")
        meta = _ui_proto_parse_meta_yaml(request.yaml_text)
        op = UpdateNodeMetaOp(request.selected_id, _ui_proto_node_meta_to_patch(meta))
        ui_proto_undo_stack.append((copy.deepcopy(layout_doc), copy.deepcopy(node_meta), request.selected_id))
        try:
            applied = apply_patch_ops(layout_doc, node_meta, [op])
        except UiLayoutError as exc:
            ui_proto_undo_stack.pop()
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        save_ui(ui_proto_layout_path, ui_proto_nodes_dir, applied.layout_doc, applied.node_meta)
        ui_proto_last_diff = [_serialize(op)]
        ui_proto_last_snap_debug = {}
        return _ui_proto_response(
            applied.layout_doc,
            applied.node_meta,
            applied.runtime,
            selected_id=request.selected_id,
            focus_id=request.focus_id,
            message="meta saved",
        )

    @app.post("/api/ui-proto/command")
    def ui_proto_command(request: UiProtoCommandRequest) -> dict[str, Any]:
        if not _UI_PROTO_AVAILABLE:
            raise _legacy_ui_unavailable("/api/ui-proto/*")
        nonlocal ui_proto_last_diff, ui_proto_last_snap_debug
        layout_doc, node_meta, runtime = _load_ui_proto_runtime()
        context = ConsolePatchContext(selected_id=request.selected_id)
        resolved_focus = _ui_proto_resolve_focus(layout_doc, request.focus_id)
        try:
            compiled = compile_console_command(request.command, layout_doc, context)
        except (ConsoleCommandError, UiLayoutError) as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc

        if compiled.control == "undo":
            if not ui_proto_undo_stack:
                return _ui_proto_response(
                    layout_doc,
                    node_meta,
                    runtime,
                    selected_id=request.selected_id or resolved_focus,
                    focus_id=resolved_focus,
                    message="undo stack is empty",
                )
            prev_layout, prev_meta, prev_selected = ui_proto_undo_stack.pop()
            save_ui(ui_proto_layout_path, ui_proto_nodes_dir, prev_layout, prev_meta)
            ui_proto_last_diff = []
            ui_proto_last_snap_debug = {}
            prev_runtime = build_ui_runtime(prev_layout, prev_meta)
            return _ui_proto_response(
                prev_layout,
                prev_meta,
                prev_runtime,
                selected_id=prev_selected or prev_runtime.root_id,
                focus_id=request.focus_id,
                message="undo applied",
            )

        if compiled.control in {"preview", "diff", "apply"}:
            ui_proto_last_snap_debug = {}
            return _ui_proto_response(
                layout_doc,
                node_meta,
                runtime,
                selected_id=request.selected_id or resolved_focus,
                focus_id=resolved_focus,
                message=f"{compiled.control} is passive in this build",
            )

        if not compiled.ops:
            ui_proto_last_snap_debug = {}
            return _ui_proto_response(
                layout_doc,
                node_meta,
                runtime,
                selected_id=compiled.context.selected_id or runtime.root_id,
                focus_id=resolved_focus,
            )

        ui_proto_undo_stack.append((copy.deepcopy(layout_doc), copy.deepcopy(node_meta), request.selected_id))
        try:
            normalized_ops = []
            for op in compiled.ops:
                if isinstance(op, AddNodeOp):
                    local_rect = op.rect
                    global_rect = _ui_proto_global_rect(layout_doc, resolved_focus, local_rect)
                    normalized_ops.append(AddNodeOp(op.id, op.parent, op.kind, global_rect))
                else:
                    normalized_ops.append(op)
            compiled.ops = normalized_ops
            applied = apply_patch_ops(layout_doc, node_meta, compiled.ops)
        except UiLayoutError as exc:
            ui_proto_undo_stack.pop()
            raise HTTPException(status_code=400, detail=str(exc)) from exc

        save_ui(ui_proto_layout_path, ui_proto_nodes_dir, applied.layout_doc, applied.node_meta)
        ui_proto_last_diff = [_serialize(op) for op in compiled.ops]
        ui_proto_last_snap_debug = {}
        return _ui_proto_response(
            applied.layout_doc,
            applied.node_meta,
            applied.runtime,
            selected_id=compiled.context.selected_id or applied.runtime.root_id,
            focus_id=resolved_focus,
            message="applied",
        )

    def _load_ui_proto2_project() -> dict[str, Any]:
        reactive_ensure_project(ui_proto2_root)
        return reactive_load_project(ui_proto2_root)

    def _ui_proto2_response(
        project: dict[str, Any],
        *,
        selected_id: str | None,
        focus_id: str | None,
        message: str = "",
    ) -> dict[str, Any]:
        resolved_focus = reactive_resolve_focus(project, focus_id)
        by_id = {node["id"]: node for node in project["nodes"]}
        if selected_id and selected_id in by_id and selected_id in {item["id"] for item in reactive_project_tree(project, resolved_focus)}:
            resolved_selected = selected_id
        else:
            resolved_selected = resolved_focus
        return {
            "ok": True,
            "message": message,
            "selected_id": resolved_selected,
            "focus_id": resolved_focus,
            "screen": {"cols": by_id[resolved_focus]["rect"][2], "rows": by_id[resolved_focus]["rect"][3]},
            "render": {"lines": reactive_compose_layers(project, resolved_focus)},
            "tree": reactive_project_tree(project, resolved_focus),
            "selected": {
                "id": resolved_selected,
                "yaml": reactive_selected_node_yaml(project, resolved_selected),
                "json": reactive_selected_node_json(project, resolved_selected),
                "rect": reactive_local_rect(project, by_id[resolved_selected]["rect"], resolved_focus),
                "name": by_id[resolved_selected].get("name") or "",
                "alias": by_id[resolved_selected].get("alias") or "",
            },
            "focus": {"id": resolved_focus},
            "layers": {
                "base": project["layers"].get("base") or "",
                "base_json": reactive_build_base_json(project),
                "events_dsl": project.get("events_dsl") or "",
            },
            "latest_diff": list(ui_proto2_last_diff),
        }

    def _ui_proto2_parse_rect(raw_rect: list[int] | None) -> list[int]:
        if not isinstance(raw_rect, list) or len(raw_rect) != 4 or not all(isinstance(v, int) for v in raw_rect):
            raise HTTPException(status_code=400, detail="rect must be [x, y, w, h]")
        if raw_rect[2] <= 0 or raw_rect[3] <= 0:
            raise HTTPException(status_code=400, detail="rect must have positive width and height")
        return list(raw_rect)

    def _ui_proto2_apply_command(project: dict[str, Any], command: str, focus_id: str, selected_id: str | None) -> tuple[str | None, list[dict[str, Any]]]:
        text = str(command or "").strip()
        lowered = text.lower()
        if lowered == "undo":
            return selected_id, []
        if lowered.startswith("select "):
            node_id = text.split(" ", 1)[1].strip()
            if not any(node["id"] == node_id for node in project["nodes"]):
                raise ReactiveUiError(f"unknown node '{node_id}'")
            return node_id, []
        if lowered == "delete":
            if not selected_id:
                raise ReactiveUiError("no selected node")
            reactive_delete_node(project, selected_id, delete_subtree=False)
            parent_id = next((node.get("parent") for node in project["nodes"] if node["id"] == selected_id), None)
            return parent_id or focus_id, [{"op": "delete_node", "id": selected_id}]
        if lowered == "delete subtree":
            if not selected_id:
                raise ReactiveUiError("no selected node")
            parent_id = next((node.get("parent") for node in project["nodes"] if node["id"] == selected_id), None)
            reactive_delete_node(project, selected_id, delete_subtree=True)
            return parent_id or focus_id, [{"op": "delete_subtree", "id": selected_id}]
        if lowered.startswith("add "):
            rest = text[4:].strip()
            head, sep, raw_rect = rest.partition(":")
            if not sep:
                raise ReactiveUiError("Usage: add <id>: [x, y, w, h] | add <kind> <id>: [x, y, w, h]")
            head_tokens = head.strip().split()
            if len(head_tokens) == 1:
                kind = "panel"
                node_id = head_tokens[0]
            elif len(head_tokens) == 2:
                kind, node_id = head_tokens
            else:
                raise ReactiveUiError("Usage: add <id>: [x, y, w, h] | add <kind> <id>: [x, y, w, h]")
            rect_value = yaml.safe_load(raw_rect.strip())
            if not isinstance(rect_value, list) or len(rect_value) != 4 or not all(isinstance(v, int) for v in rect_value):
                raise ReactiveUiError("add rect must be [x, y, w, h]")
            parent_id = selected_id or focus_id
            reactive_add_node(project, parent_id, node_id, reactive_global_rect(project, rect_value, focus_id), kind=kind)
            return node_id, [{"op": "add_node", "id": node_id, "parent": parent_id, "kind": kind, "rect": rect_value}]
        raise ReactiveUiError(f"unsupported command '{command}'")

    @app.get("/api/ui-proto2/state")
    def ui_proto2_state(selected_id: str | None = None, focus_id: str | None = None) -> dict[str, Any]:
        if not _UI_PROTO_REACTIVE_AVAILABLE:
            raise _legacy_ui_unavailable("/api/ui-proto2/*")
        project = _load_ui_proto2_project()
        return _ui_proto2_response(project, selected_id=selected_id, focus_id=focus_id)

    @app.post("/api/ui-proto2/select")
    def ui_proto2_select(request: UiProto2SelectRequest) -> dict[str, Any]:
        if not _UI_PROTO_REACTIVE_AVAILABLE:
            raise _legacy_ui_unavailable("/api/ui-proto2/*")
        project = _load_ui_proto2_project()
        resolved_focus = reactive_resolve_focus(project, request.focus_id)
        selected_id = reactive_pick_node(project, request.x, request.y, resolved_focus) or request.selected_id or resolved_focus
        return _ui_proto2_response(project, selected_id=selected_id, focus_id=resolved_focus)

    @app.post("/api/ui-proto2/gui-action")
    def ui_proto2_gui_action(request: UiProto2GuiActionRequest) -> dict[str, Any]:
        if not _UI_PROTO_REACTIVE_AVAILABLE:
            raise _legacy_ui_unavailable("/api/ui-proto2/*")
        nonlocal ui_proto2_last_diff
        project = _load_ui_proto2_project()
        resolved_focus = reactive_resolve_focus(project, request.focus_id)
        action = request.action.strip().lower()
        selected_id = request.selected_id or resolved_focus
        local_rect = _ui_proto2_parse_rect(request.rect)
        global_rect = reactive_global_rect(project, local_rect, resolved_focus)
        ui_proto2_undo_stack.append((copy.deepcopy(project), request.selected_id, request.focus_id))
        try:
            if action == "move":
                reactive_move_node(project, selected_id, global_rect)
                ui_proto2_last_diff = [{"op": "move_node", "id": selected_id, "rect": local_rect}]
            elif action == "resize":
                reactive_resize_node(project, selected_id, global_rect)
                ui_proto2_last_diff = [{"op": "resize_node", "id": selected_id, "rect": local_rect}]
            elif action == "create":
                parent_id = request.parent_id or request.selected_id or resolved_focus
                node_id = request.node_id or reactive_next_id(project, request.kind or "panel")
                reactive_add_node(project, parent_id, node_id, global_rect, kind=request.kind or "panel")
                selected_id = node_id
                ui_proto2_last_diff = [{"op": "add_node", "id": node_id, "parent": parent_id, "kind": request.kind or "panel", "rect": local_rect}]
            else:
                raise ReactiveUiError(f"unsupported gui action '{request.action}'")
        except ReactiveUiError as exc:
            ui_proto2_undo_stack.pop()
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        reactive_save_project(ui_proto2_root, project)
        return _ui_proto2_response(project, selected_id=selected_id, focus_id=resolved_focus, message=f"gui {action} applied")

    @app.post("/api/ui-proto2/node/save")
    def ui_proto2_node_save(request: UiProto2NodeSaveRequest) -> dict[str, Any]:
        if not _UI_PROTO_REACTIVE_AVAILABLE:
            raise _legacy_ui_unavailable("/api/ui-proto2/*")
        nonlocal ui_proto2_last_diff
        project = _load_ui_proto2_project()
        ui_proto2_undo_stack.append((copy.deepcopy(project), request.selected_id, request.focus_id))
        try:
            reactive_replace_node_from_yaml(project, request.selected_id, request.yaml_text)
        except ReactiveUiError as exc:
            ui_proto2_undo_stack.pop()
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        reactive_save_project(ui_proto2_root, project)
        ui_proto2_last_diff = [{"op": "update_node", "id": request.selected_id}]
        return _ui_proto2_response(project, selected_id=request.selected_id, focus_id=request.focus_id, message="node saved")

    @app.post("/api/ui-proto2/files/save")
    def ui_proto2_files_save(request: UiProto2FilesSaveRequest) -> dict[str, Any]:
        if not _UI_PROTO_REACTIVE_AVAILABLE:
            raise _legacy_ui_unavailable("/api/ui-proto2/*")
        nonlocal ui_proto2_last_diff
        project = _load_ui_proto2_project()
        ui_proto2_undo_stack.append((copy.deepcopy(project), request.selected_id, request.focus_id))
        reactive_save_layers(
            project,
            base=request.base_text,
            events_dsl=request.events_dsl,
        )
        reactive_save_project(ui_proto2_root, project)
        ui_proto2_last_diff = [{"op": "save_layers"}]
        return _ui_proto2_response(project, selected_id=request.selected_id, focus_id=request.focus_id, message="layers saved")

    @app.post("/api/ui-proto2/command")
    def ui_proto2_command(request: UiProto2CommandRequest) -> dict[str, Any]:
        if not _UI_PROTO_REACTIVE_AVAILABLE:
            raise _legacy_ui_unavailable("/api/ui-proto2/*")
        nonlocal ui_proto2_last_diff
        if request.command.strip().lower() == "undo":
            if not ui_proto2_undo_stack:
                project = _load_ui_proto2_project()
                return _ui_proto2_response(project, selected_id=request.selected_id, focus_id=request.focus_id, message="undo stack is empty")
            prev_project, prev_selected, prev_focus = ui_proto2_undo_stack.pop()
            reactive_save_project(ui_proto2_root, prev_project)
            ui_proto2_last_diff = []
            return _ui_proto2_response(prev_project, selected_id=prev_selected, focus_id=prev_focus, message="undo applied")
        project = _load_ui_proto2_project()
        resolved_focus = reactive_resolve_focus(project, request.focus_id)
        ui_proto2_undo_stack.append((copy.deepcopy(project), request.selected_id, request.focus_id))
        try:
            next_selected, diff = _ui_proto2_apply_command(project, request.command, resolved_focus, request.selected_id)
        except ReactiveUiError as exc:
            ui_proto2_undo_stack.pop()
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        reactive_save_project(ui_proto2_root, project)
        ui_proto2_last_diff = diff
        return _ui_proto2_response(project, selected_id=next_selected, focus_id=resolved_focus, message="applied")

    def _serialize(v: Any) -> Any:
        if isinstance(v, (str, int, float, bool, type(None))):
            return v
        if is_dataclass(v):
            return _serialize(asdict(v))
        if isinstance(v, list):
            return [_serialize(x) for x in v]
        if isinstance(v, dict):
            return {k: _serialize(val) for k, val in v.items()}
        return str(v)

    @app.get("/reactive-chat", response_class=HTMLResponse)
    def reactive_chat_page() -> str:
        html_path = Path(__file__).resolve().parents[2] / "tools" / "reactive_chat.html"
        return html_path.read_text(encoding="utf-8")

    @app.get("/gui-builder", response_class=HTMLResponse)
    def gui_builder_page() -> str:
        html_path = Path(__file__).resolve().parents[2] / "tools" / "gui_builder.html"
        return html_path.read_text(encoding="utf-8")

    @app.get("/aabb", response_class=HTMLResponse)
    def aabb_page() -> str:
        html_path = Path(__file__).resolve().parents[2] / "tools" / "aabb.html"
        return html_path.read_text(encoding="utf-8")

    @app.get("/api/aabb/project")
    def get_aabb_project() -> dict:
        """Serve the AABB project JSON."""
        import json
        proj_path = Path(__file__).resolve().parents[2] / "tools" / "aabb_project.json"
        if proj_path.exists():
            return json.loads(proj_path.read_text(encoding="utf-8"))
        return {"data": {}, "panels": []}

    @app.post("/api/aabb/project")
    async def save_aabb_project(request: Request) -> dict:
        """Save the AABB project JSON."""
        import json
        body = await request.json()
        proj_path = Path(__file__).resolve().parents[2] / "tools" / "aabb_project.json"
        proj_path.write_text(json.dumps(body, indent=2, ensure_ascii=False), encoding="utf-8")
        return {"ok": True}

    @app.get("/aabb-pipeline", response_class=HTMLResponse)
    def aabb_pipeline_page() -> str:
        html_path = Path(__file__).resolve().parents[2] / "tools" / "aabb_pipeline.html"
        return html_path.read_text(encoding="utf-8")

    @app.get("/api/aabb-pipeline/replay")
    def get_aabb_pipeline_replay() -> list:
        """Serve the AABB pipeline replay."""
        import json
        replay_path = Path(__file__).resolve().parents[2] / "tools" / "aabb_pipeline_replay.jsonl"
        if replay_path.exists():
            lines = replay_path.read_text(encoding="utf-8").strip().split('\n')
            return [json.loads(l) for l in lines if l.strip()]
        return []

    @app.post("/api/aabb-pipeline/replay")
    async def save_aabb_pipeline_replay(request: Request) -> dict:
        """Save the AABB pipeline replay."""
        import json
        body = await request.json()
        replay_path = Path(__file__).resolve().parents[2] / "tools" / "aabb_pipeline_replay.jsonl"
        replay_path.write_text('\n'.join(json.dumps(cmd, ensure_ascii=False) for cmd in body) + '\n', encoding="utf-8")
        return {"ok": True, "steps": len(body)}

    @app.get("/workflow", response_class=HTMLResponse)
    def workflow_page() -> str:
        html_path = Path(__file__).resolve().parents[2] / "tools" / "workflow.html"
        return html_path.read_text(encoding="utf-8")

    # ── Workflow v3: Gateway Runtime ────────────────────────
    from .gateway_runtime import GatewayRuntime, GatewayEvent

    _v3_runtimes: dict[str, GatewayRuntime] = {}
    _v3_lock = threading.Lock()

    @app.post("/api/workflow/v3/run")
    async def run_workflow_v3(request: Request) -> dict:
        body = await request.json()
        yaml_text = body.get("yaml", "")
        worker_map = body.get("workers", {})
        if not worker_map:
            worker_map = {w.get("role", "generator"): w.get("url", "") for w in body.get("worker_list", [])}
        settings = body.get("settings", {})

        run_id = f"v3_{int(time.time()*1000)}"
        events_log: list[dict] = []
        thread: list[dict] = []

        def on_event(e: GatewayEvent):
            events_log.append({"job_id": e.job_id, "type": e.event_type, "ts": e.timestamp})

        def on_thread(role, name, content, extra=None):
            thread.append({"role": role, "name": name, "content": str(content)[:500], **(extra or {})})

        try:
            runtime = GatewayRuntime.from_yaml(
                yaml_text, workers=worker_map, settings=settings,
                on_event=on_event, on_thread=on_thread,
            )
        except Exception as exc:
            return {"status": "error", "error": str(exc)}

        with _v3_lock:
            _v3_runtimes[run_id] = runtime

        return {"status": "started", "run_id": run_id}

    @app.get("/api/workflow/v3/status")
    def get_workflow_v3_status(run_id: str) -> dict:
        with _v3_lock:
            runtime = _v3_runtimes.get(run_id)
        if not runtime:
            return {"error": "run not found"}
        return runtime.get_status()

    @app.post("/api/workflow/v3/cancel")
    async def cancel_workflow_v3(request: Request) -> dict:
        body = await request.json()
        run_id = body.get("run_id", "")
        job_id = body.get("job_id", "")
        with _v3_lock:
            runtime = _v3_runtimes.get(run_id)
        if not runtime:
            return {"error": "run not found"}
        ok = runtime.cancel(job_id)
        return {"ok": ok}

    @app.get("/static/{filename:path}")
    def serve_static(filename: str):
        from fastapi.responses import Response
        file_path = Path(__file__).resolve().parents[2] / "tools" / filename
        if not file_path.exists() or not file_path.is_file():
            return Response(status_code=404, content="Not found")
        ct = "application/javascript" if filename.endswith(".js") else "text/css" if filename.endswith(".css") else "text/plain"
        return Response(content=file_path.read_text(encoding="utf-8"), media_type=ct)

    @app.get("/tpl/{filename:path}")
    def serve_template_file(filename: str):
        """Serve files from root/templates/ — views, schemas, JS."""
        from fastapi.responses import Response
        file_path = Path(root) / "root" / "templates" / filename
        if not file_path.exists() or not file_path.is_file():
            return Response(status_code=404, content="Not found")
        ext = file_path.suffix.lower()
        ct_map = {".js": "application/javascript", ".css": "text/css", ".html": "text/html", ".json": "application/json"}
        ct = ct_map.get(ext, "text/plain")
        return Response(content=file_path.read_text(encoding="utf-8"), media_type=ct)

    @app.get("/workflow-v3", response_class=HTMLResponse)
    def workflow_v3_page() -> str:
        html_path = Path(__file__).resolve().parents[2] / "tools" / "workflow_v3.html"
        return html_path.read_text(encoding="utf-8")

    @app.get("/workflow-v3-compact", response_class=HTMLResponse)
    def workflow_v3_compact_page() -> str:
        html_path = Path(__file__).resolve().parents[2] / "tools" / "workflow_v3_compact.html"
        return html_path.read_text(encoding="utf-8")

    @app.get("/component-builder", response_class=HTMLResponse)
    def component_builder_page() -> str:
        html_path = Path(__file__).resolve().parents[2] / "tools" / "component_builder.html"
        return html_path.read_text(encoding="utf-8")

    @app.get("/card-builder", response_class=HTMLResponse)
    def card_builder_page() -> str:
        html_path = Path(__file__).resolve().parents[2] / "tools" / "card_builder.html"
        return html_path.read_text(encoding="utf-8")

    # ── Component Builder: save/load component bundles ──

    @app.get("/api/component-builder/components")
    def get_component_bundle() -> dict:
        """Load saved component bundle (components + views + replay)."""
        import json
        bundle_path = Path(__file__).resolve().parents[2] / "tools" / "v3_component_bundle.json"
        if bundle_path.exists():
            return json.loads(bundle_path.read_text(encoding="utf-8"))
        return {"components": {}, "views": {}, "replay": []}

    @app.post("/api/component-builder/components")
    async def save_component_bundle(request: Request) -> dict:
        """Save component bundle (components + views + replay)."""
        import json
        body = await request.json()
        bundle_path = Path(__file__).resolve().parents[2] / "tools" / "v3_component_bundle.json"
        bundle_path.write_text(json.dumps(body, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
        comp_count = len(body.get("components", {}))
        view_count = len(body.get("views", {}))
        replay_count = len(body.get("replay", []))
        return {"ok": True, "components": comp_count, "views": view_count, "replay": replay_count}

    @app.get("/aabb", response_class=HTMLResponse)
    def aabb_page() -> str:
        html_path = Path(__file__).resolve().parents[2] / "tools" / "aabb.html"
        return html_path.read_text(encoding="utf-8")

    @app.get("/aabb-test", response_class=HTMLResponse)
    def aabb_test_page() -> str:
        html_path = Path(__file__).resolve().parents[2] / "tools" / "aabb_test.html"
        return html_path.read_text(encoding="utf-8")

    @app.get("/aabb-symbolic", response_class=HTMLResponse)
    def aabb_symbolic_page() -> str:
        html_path = Path(__file__).resolve().parents[2] / "tools" / "aabb_symbolic.html"
        return html_path.read_text(encoding="utf-8")

    @app.get("/ui-proto", response_class=HTMLResponse)
    @app.get("/ui_proto", response_class=HTMLResponse)
    def ui_proto_page() -> str:
        html_path = Path(__file__).resolve().parents[2] / "tools" / "ui_proto.html"
        return html_path.read_text(encoding="utf-8")

    @app.get("/think-lab", response_class=HTMLResponse)
    def think_lab_page() -> str:
        html_path = Path(__file__).resolve().parents[2] / "tools" / "think_lab.html"
        return html_path.read_text(encoding="utf-8")

    @app.get("/atomic-dsl", response_class=HTMLResponse)
    def atomic_dsl_page() -> str:
        html_path = Path(__file__).resolve().parents[2] / "tools" / "atomic_dsl.html"
        return html_path.read_text(encoding="utf-8")

    @app.get("/dsl-pipeline", response_class=HTMLResponse)
    def dsl_pipeline_page() -> str:
        html_path = Path(__file__).resolve().parents[2] / "tools" / "dsl_pipeline_chat.html"
        return html_path.read_text(encoding="utf-8")

    @app.get("/pipeline-chat", response_class=HTMLResponse)
    def pipeline_chat_page() -> str:
        html_path = Path(__file__).resolve().parents[2] / "tools" / "pipeline_chat.html"
        return html_path.read_text(encoding="utf-8")

    @app.get("/data-store", response_class=HTMLResponse)
    def data_store_page() -> str:
        html_path = Path(__file__).resolve().parents[2] / "tools" / "data_store" / "index.html"
        return html_path.read_text(encoding="utf-8")

    @app.get("/atomic-wiki", response_class=HTMLResponse)
    def atomic_wiki_page() -> str:
        """Inline wiki viewer — lists pages from /api/atomic-wiki/pages."""
        return """<!DOCTYPE html>
<html><head><meta charset="UTF-8"><title>Atomic Wiki</title>
<style>
:root { --bg:#1a1b26; --surface:#24283b; --border:#3b3d57; --text:#c0caf5; --dim:#565f89; --accent:#7aa2f7; --green:#9ece6a; --mono:'Cascadia Code','Fira Code',monospace; }
* { box-sizing:border-box; margin:0; padding:0; }
body { background:var(--bg); color:var(--text); font:13px/1.5 var(--mono); height:100vh; display:flex; flex-direction:column; overflow:hidden; }
.topbar { display:flex; align-items:center; gap:12px; padding:8px 16px; background:var(--surface); border-bottom:1px solid var(--border); }
.topbar h1 { font-size:16px; color:var(--accent); }
.topbar .count { font-size:12px; color:var(--dim); }
.main { flex:1; display:flex; min-height:0; }
.sidebar { width:240px; border-right:1px solid var(--border); overflow-y:auto; padding:8px; }
.page-item { padding:6px 8px; border-radius:4px; cursor:pointer; font-size:12px; margin:2px 0; }
.page-item:hover { background:var(--surface); }
.page-item.active { background:var(--accent); color:#000; }
.page-item .kind { font-size:10px; color:var(--dim); }
.page-item.active .kind { color:rgba(0,0,0,.5); }
.content { flex:1; overflow-y:auto; padding:16px; }
.content h2 { color:var(--accent); margin-bottom:8px; }
.content .meta { font-size:11px; color:var(--dim); margin-bottom:12px; }
.content pre { background:var(--surface); padding:12px; border-radius:6px; white-space:pre-wrap; word-break:break-word; font-size:12px; line-height:1.5; }
.empty { color:var(--dim); font-style:italic; padding:40px; text-align:center; }
</style></head><body>
<div class="topbar"><h1>Atomic Wiki</h1><span class="count" id="count"></span></div>
<div class="main">
  <div class="sidebar" id="sidebar"></div>
  <div class="content" id="content"><div class="empty">Select a page</div></div>
</div>
<script>
let pages = [];
async function load() {
  const r = await fetch('/api/atomic-wiki/pages');
  const d = await r.json();
  pages = d.pages || [];
  document.getElementById('count').textContent = pages.length + ' pages';
  const sb = document.getElementById('sidebar');
  sb.innerHTML = pages.map((p,i) => `<div class="page-item" onclick="show(${i})"><div>${p.title || p.slug}</div><div class="kind">${p.item_kind} / ${p.page_kind}</div></div>`).join('');
}
async function show(i) {
  document.querySelectorAll('.page-item').forEach((el,j) => el.classList.toggle('active', j===i));
  const slug = pages[i].slug;
  const r = await fetch('/api/atomic-wiki/pages/' + slug);
  const p = await r.json();
  const c = document.getElementById('content');
  const tags = (p.tags||[]).map(t => '<span style="background:var(--surface);padding:2px 6px;border-radius:3px;font-size:10px;margin-right:4px">'+t+'</span>').join('');
  c.innerHTML = '<h2>'+esc(p.title||p.slug)+'</h2><div class="meta">'+esc(p.item_kind)+' / '+esc(p.page_kind)+' '+tags+'</div><pre>'+esc(p.message?.text||JSON.stringify(p.blocks,null,2))+'</pre>';
}
function esc(s){const d=document.createElement('div');d.textContent=String(s);return d.innerHTML;}
load();
</script></body></html>"""

    @app.get("/chat", response_class=HTMLResponse)
    def chat_page() -> str:
        return _chat_page_html()

    @app.get("/api/chat/log")
    def get_chat_log(session_id: str | None = None) -> dict:
        session = ensure_session(session_id)
        return {"entries": session["chat_log"], "session_id": session["id"]}

    @app.get("/api/chat/history")
    def get_chat_history(session_id: str | None = None) -> dict:
        session = ensure_session(session_id)
        return {"messages": session["chat_history"], "session_id": session["id"]}

    @app.get("/api/chat/sessions")
    def get_chat_sessions() -> dict:
        ordered = list(sessions.values())
        return {
            "sessions": [
                {
                    "id": item["id"],
                    "title": item["title"],
                    "message_count": len(item["chat_history"]),
                }
                for item in ordered
            ]
        }

    @app.post("/api/chat/sessions")
    def create_chat_session(request: ChatSessionCreateRequest) -> dict:
        session_id = f"chat-{uuid.uuid4().hex[:8]}"
        title = (request.title or "").strip() or f"Chat {len(sessions) + 1}"
        sessions[session_id] = {
            "id": session_id,
            "title": title,
            "chat_log": [],
            "chat_history": [],
        }
        return {"session": {"id": session_id, "title": title, "message_count": 0}}

    @app.post("/api/chat/reset")
    def reset_chat(session_id: str | None = None) -> dict:
        session = ensure_session(session_id)
        session["chat_history"].clear()
        session["chat_log"].clear()
        return {"ok": True, "session_id": session["id"]}

    @app.post("/api/chat")
    def chat(request: ChatRequest) -> dict:
        session = ensure_session(request.session_id)
        client = resolve_client()
        prompt = _compose_chat_prompt(request, session["chat_history"])
        raw = client.chat(
            prompt=prompt,
            model=request.model or resolve_default_model(),
            system_prompt=request.system_prompt,
        )
        response_text = client.extract_chat_text(raw)
        session["chat_history"].append({"role": "user", "content": request.message})
        session["chat_history"].append({"role": "assistant", "content": response_text})
        if len(session["chat_history"]) == 2 and session["title"].startswith("Chat "):
            session["title"] = request.message.strip()[:40] or session["title"]
        entry = {
            "kind": "chat",
            "session_id": session["id"],
            "request": request.model_dump(),
            "composed_prompt": prompt,
            "response_text": response_text,
            "raw_response": raw,
            "history_size": len(session["chat_history"]),
        }
        session["chat_log"].append(entry)
        return entry

    # ------------------------------------------------------------------
    # Pipeline Chat — FS-first workspace with shell commands
    # ------------------------------------------------------------------
    import shlex

    class ConsoleScope:
        """One virtual terminal: own cwd, own log, own redo."""

        def __init__(self, name: str, root: Path, redo: bool = True):
            self.name = name
            self.cwd = root       # current active object (result accumulator)
            self.log: list[dict] = []   # FIFO cmd history, JSON-serializable
            self.redo = redo
            self.redo_stack: list[dict] = []

        def record(self, cmd: str, user: str, result: dict):
            entry = {"cmd": cmd, "user": user, "ts": utc_now(), "result": result}
            self.log.append(entry)
            if self.redo:
                self.redo_stack.clear()  # new action clears redo

        def to_dict(self) -> dict:
            return {
                "name": self.name,
                "cwd": str(self.cwd),
                "log_size": len(self.log),
                "redo": self.redo,
                "redo_size": len(self.redo_stack),
            }

    class PChatWorkspace:
        """Filesystem-backed chat workspace with shell commands + git versioning."""

        def __init__(self, fs_root: Path):
            self.root = fs_root / "root"
            self.root.mkdir(exist_ok=True)
            self.templates_dir = self.root / "templates"
            self.templates_dir.mkdir(exist_ok=True)
            self.runtime_dir = self.root / "runtime"
            self.runtime_dir.mkdir(exist_ok=True)
            self.containers_dir = self.runtime_dir / "containers"
            self.containers_dir.mkdir(parents=True, exist_ok=True)
            self.sandboxes_dir = self.runtime_dir / "sandboxes"
            self.sandboxes_dir.mkdir(parents=True, exist_ok=True)
            self.pchat_dir = self.root / "pchat"
            self.pchat_dir.mkdir(exist_ok=True)
            self.log_path = self.root / "log.jsonl"
            self.scopes: dict[str, ConsoleScope] = {}
            self.atomic_runtime_objects: dict[str, dict] = {}
            self.atomic_runtime_index: dict[str, list[dict[str, Any]]] = {}

            # Git versioning for pchat FS
            from .data_store.git_history import DataStoreGit
            self._git = DataStoreGit(self.pchat_dir, self.pchat_dir)
            self._git.init()

            # Root _meta.json
            root_meta = self.root / "_meta.json"
            if not root_meta.exists():
                root_meta.write_text(json.dumps({"type": "root"}, indent=2), encoding="utf-8")

            # Ensure pchat has meta
            pchat_meta = self.pchat_dir / "_meta.json"
            if not pchat_meta.exists():
                pchat_meta.write_text(json.dumps({"type": "pchat", "name": "pchat"}, indent=2), encoding="utf-8")
            pchat_data = self.pchat_dir / "_data.json"
            if not pchat_data.exists():
                pchat_data.write_text("{}", encoding="utf-8")

            # Default templates
            self._init_templates()
            self._init_runtime_containers()

            # Precompile + preload all template commands
            import compileall
            compileall.compile_dir(str(self.templates_dir), quiet=2)
            self._preload_commands()

        def _dump_tree(self):
            """Serialize full FS tree to root/tree.json."""
            tree = self._read_tree(self.root, depth=10, limit=500)
            tree_path = self.root / "tree.json"
            tree_path.write_text(json.dumps(tree, indent=2, ensure_ascii=False), encoding="utf-8")

        def _init_templates(self):
            """Create default templates if missing."""
            for tpl_name, schema in [
                ("root", {"fields": {}, "commands": ["materialize", "cselect", "cpost", "cmkchannel", "cpatch", "cedit", "cdelete", "creact"], "panels": [], "renders": []}),
                ("channels", {"fields": {}, "commands": ["add_channel"], "panels": [], "renders": []}),
                ("channel", {"fields": {"name": "str"}, "commands": ["post", "select", "rename"], "panels": ["panel_sidebar"], "renders": []}),
                ("message", {"fields": {"content": "str"}, "commands": ["edit"], "panels": ["panel_compact"], "renders": []}),
            ]:
                tpl_dir = self.templates_dir / tpl_name
                tpl_dir.mkdir(exist_ok=True)
                schema_path = tpl_dir / "schema.json"
                if not schema_path.exists():
                    schema_path.write_text(json.dumps(schema, indent=2), encoding="utf-8")
                # Create subdirs
                for sub in ("commands", "panels", "renders", "views"):
                    (tpl_dir / sub).mkdir(exist_ok=True)
            self._sync_default_templates()

        def _sync_default_templates(self):
            """Copy built-in template files from the checkout if they are missing in the workspace root."""
            defaults_root = Path(__file__).resolve().parents[2] / "root" / "templates"
            if not defaults_root.is_dir():
                return
            for src_path in defaults_root.rglob("*"):
                if src_path.is_dir():
                    continue
                rel = src_path.relative_to(defaults_root)
                dst_path = self.templates_dir / rel
                if not dst_path.exists():
                    dst_path.parent.mkdir(parents=True, exist_ok=True)
                    shutil.copy2(src_path, dst_path)

        def _init_runtime_containers(self):
            """Create default runtime container manifests for generic materialization."""
            for container_id in ("channels_selector", "current_channel", "current_channel_messages"):
                meta, state = self._load_default_container_spec(container_id)
                self._ensure_container(container_id, meta, state)

        def _load_default_container_spec(self, container_id: str) -> tuple[dict, dict]:
            """Load default container manifest/state from the checkout's root/runtime tree."""
            defaults_root = Path(__file__).resolve().parents[2] / "root" / "runtime" / "containers" / container_id
            meta = self._read_json(defaults_root / "_meta.json")
            state = self._read_json(defaults_root / "state.json")
            if isinstance(meta, dict) and isinstance(state, dict):
                return meta, state
            raise RuntimeError(f"missing default runtime container spec for {container_id}")

        def _ensure_container(self, container_id: str, meta: dict, state: dict):
            cdir = self.containers_dir / container_id
            cdir.mkdir(parents=True, exist_ok=True)
            meta_path = cdir / "_meta.json"
            state_path = cdir / "state.json"
            log_path = cdir / "cmd_log.jsonl"
            if not meta_path.exists():
                meta_path.write_text(json.dumps(meta, indent=2, ensure_ascii=False), encoding="utf-8")
            if not state_path.exists():
                state_path.write_text(json.dumps(state, indent=2, ensure_ascii=False), encoding="utf-8")
            if not log_path.exists():
                log_path.write_text("", encoding="utf-8")

        def get_scope(self, name: str = "CMD") -> "ConsoleScope":
            """Get or create a named scope. Root = root dir (virtual root node)."""
            if name not in self.scopes:
                redo = name == "CMD"  # only user CMD gets redo
                self.scopes[name] = ConsoleScope(name, self.root, redo=redo)
            return self.scopes[name]

        def _resolve_template_cmd(self, command: str, scope: "ConsoleScope"):
            """Find a command .py file by walking the template inheritance chain.
            Returns loaded module's execute function, or None."""
            # Determine type of current node
            meta = self._read_meta(scope.cwd)
            node_type = (meta or {}).get("type", "")
            if not node_type:
                return None

            # Walk inheritance: node_type -> schema.inherits -> ... -> None
            visited = set()
            current_type = node_type
            while current_type and current_type not in visited:
                visited.add(current_type)
                cmd_path = self.templates_dir / current_type / "commands" / f"{command}.py"
                if cmd_path.is_file():
                    return self._load_cmd_module(cmd_path)
                # Follow inheritance
                schema_path = self.templates_dir / current_type / "schema.json"
                if schema_path.is_file():
                    try:
                        schema = json.loads(schema_path.read_text(encoding="utf-8"))
                        current_type = schema.get("inherits", "")
                    except Exception:
                        break
                else:
                    break
            return None

        # ── Exec-as-capability ────────────────────────────

        def _get_node_schema(self, node_dir: Path) -> dict:
            """Get merged schema for node by walking template inheritance chain."""
            meta = self._read_meta(node_dir)
            node_type = (meta or {}).get("type", "")
            if not node_type:
                return {}
            merged: dict[str, Any] = {}
            visited = set()
            current_type = node_type
            while current_type and current_type not in visited:
                visited.add(current_type)
                schema_path = self.templates_dir / current_type / "schema.json"
                if schema_path.is_file():
                    try:
                        schema = json.loads(schema_path.read_text(encoding="utf-8"))
                        # Earlier in chain = more specific, takes priority
                        for k, v in schema.items():
                            if k not in merged:
                                merged[k] = v
                            elif k == "children" and isinstance(v, dict):
                                # Merge children from parent into child (child overrides)
                                parent_children = dict(v)
                                parent_children.update(merged.get("children", {}))
                                merged["children"] = parent_children
                        current_type = schema.get("inherits", "")
                    except Exception:
                        break
                else:
                    break
            return merged

        def _node_has_exec(self, node_dir: Path) -> bool:
            """Check if node's template declares exec capability."""
            schema = self._get_node_schema(node_dir)
            return bool(schema.get("exec", False))

        def _node_can_append(self, node_dir: Path, child_type: str) -> bool:
            """Check if node allows appending children of given type."""
            schema = self._get_node_schema(node_dir)
            children = schema.get("children", {})
            if not children:
                return False
            # Check exact type or wildcard
            spec = children.get(child_type, children.get("*"))
            if not spec:
                return False
            if isinstance(spec, dict):
                return bool(spec.get("append", False))
            return bool(spec)

        _cmd_cache: dict[str, tuple] = {}  # path_str -> (execute_fn, mtime)

        def _preload_commands(self):
            """Load all template command .py files into cache at startup."""
            count = 0
            for tpl_dir in self.templates_dir.iterdir():
                if not tpl_dir.is_dir():
                    continue
                cmd_dir = tpl_dir / "commands"
                if not cmd_dir.is_dir():
                    continue
                for py_file in cmd_dir.glob("*.py"):
                    if self._load_cmd_module(py_file):
                        count += 1
            return count

        def _load_cmd_module(self, path: Path):
            """Load a .py command file. Hot-reloads if mtime changed."""
            key = str(path)
            try:
                mtime = path.stat().st_mtime
            except OSError:
                return None
            cached = self._cmd_cache.get(key)
            if cached and cached[1] >= mtime:
                return cached[0]
            # (Re)load
            import importlib.util
            spec = importlib.util.spec_from_file_location(f"cmd_{path.stem}_{id(self)}", str(path))
            if spec is None or spec.loader is None:
                return None
            mod = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(mod)
            fn = getattr(mod, "execute", None)
            self._cmd_cache[key] = (fn, mtime)
            return fn

        def exec_cmd(self, cmd_str: str, user: str = "anon", log: bool = True, scope_name: str = "CMD") -> dict:
            """Parse and execute a shell command in a named scope.
            Resolution order: template command .py (by inheritance) -> hardcoded cmd_* method.
            Supports -- raw tail: everything after -- is passed as single last arg."""
            # Raw tail mode: split at -- before shlex
            raw_tail = None
            if " -- " in cmd_str:
                head, raw_tail = cmd_str.split(" -- ", 1)
                cmd_str = head

            try:
                parts = shlex.split(cmd_str)
            except ValueError as e:
                return {"error": f"parse error: {e}"}
            if not parts:
                return {"error": "empty command"}
            command = parts[0].lstrip("/").lower()
            args = parts[1:]
            if raw_tail is not None:
                args.append(raw_tail)
            scope = self.get_scope(scope_name)

            # 1. Try template command (from .py files)
            tpl_execute = self._resolve_template_cmd(command, scope)
            if tpl_execute:
                result = tpl_execute(args, user, scope, self)
            else:
                # 2. Fallback to hardcoded handler
                handler = getattr(self, f"cmd_{command}", None)
                if not handler:
                    return {"error": f"unknown command: /{command}"}
                result = handler(args, user, scope)

            # Record in scope log + global audit log
            if log and command not in ("dir", "cat", "query", "ls", "list"):
                scope.record(cmd_str, user, result)
                self._log(cmd_str, user)
                try:
                    self._git.commit_all(f"{user}: {cmd_str}")
                except Exception:
                    pass
            return result

        def _log(self, cmd: str, user: str):
            line = json.dumps({"cmd": cmd, "ts": utc_now(), "user": user}, ensure_ascii=False, default=str)
            with open(self.log_path, "a", encoding="utf-8") as f:
                f.write(line + "\n")

        def _read_meta(self, path: Path) -> dict | None:
            meta_path = path / "_meta.json"
            if meta_path.exists():
                return json.loads(meta_path.read_text(encoding="utf-8"))
            return None

        def _write_meta(self, path: Path, meta: dict):
            (path / "_meta.json").write_text(json.dumps(meta, indent=2), encoding="utf-8")

        def _read_data(self, path: Path) -> dict | None:
            data_path = path / "_data.json"
            if data_path.exists():
                return json.loads(data_path.read_text(encoding="utf-8"))
            return None

        def _write_data(self, path: Path, data: dict):
            (path / "_data.json").write_text(json.dumps(data, indent=2), encoding="utf-8")

        # ── L0: Exec log (append-only per node) ──────────────

        def _exec_log_path(self, node_dir: Path) -> Path:
            return node_dir / "_exec.jsonl"

        def _append_exec_entry(self, node_dir: Path, entry: dict):
            log_path = self._exec_log_path(node_dir)
            log_path.parent.mkdir(parents=True, exist_ok=True)
            with open(log_path, "a", encoding="utf-8") as f:
                f.write(json.dumps(entry, ensure_ascii=False) + "\n")

        def _read_exec_log(self, node_dir: Path) -> list[dict]:
            log_path = self._exec_log_path(node_dir)
            if not log_path.exists():
                return []
            entries = []
            for line in log_path.read_text(encoding="utf-8").splitlines():
                line = line.strip()
                if line:
                    try:
                        entries.append(json.loads(line))
                    except json.JSONDecodeError:
                        pass
            return entries

        # ── Patch-only response builder ───────────────────

        def _build_patch_response(self, before: dict, after: dict, prefix: str = "") -> list[dict]:
            """Diff two state dicts, return list of patches [{path, value, op}]."""
            patches: list[dict] = []
            all_keys = set(list(before.keys()) + list(after.keys()))
            for key in all_keys:
                path = f"{prefix}.{key}" if prefix else key
                old_val = before.get(key)
                new_val = after.get(key)
                if key not in before:
                    patches.append({"path": path, "value": new_val, "op": "add"})
                elif key not in after:
                    patches.append({"path": path, "value": None, "op": "remove"})
                elif isinstance(old_val, dict) and isinstance(new_val, dict):
                    patches.extend(self._build_patch_response(old_val, new_val, path))
                elif isinstance(old_val, list) and isinstance(new_val, list):
                    if old_val != new_val:
                        patches.append({"path": path, "value": new_val, "op": "update"})
                elif old_val != new_val:
                    patches.append({"path": path, "value": new_val, "op": "update"})
            return patches

        # ── L1: Projection / flat_store ──────────────────────

        def _field_type_name(self, value: Any) -> str:
            if value is None:
                return "null"
            if isinstance(value, bool):
                return "bool"
            if isinstance(value, int) and not isinstance(value, bool):
                return "int"
            if isinstance(value, float):
                return "float"
            if isinstance(value, str):
                return "str"
            if isinstance(value, list):
                return "list"
            if isinstance(value, dict):
                return "dict"
            return type(value).__name__

        def _projection_hash(self, source_path: str, field_path: str) -> str:
            raw = f"{source_path}::{field_path}".encode("utf-8")
            return hashlib.sha1(raw).hexdigest()[:12]

        def _projection_field_entry(self, source_path: str, scope: str, key: str, value: Any) -> dict:
            field_path = f"{scope}.{key}"
            bind = f"{source_path}.{field_path}"
            field_hash = self._projection_hash(source_path, field_path)
            return {
                "hash": field_hash,
                "scope": scope,
                "path": field_path,
                "full_relative_path": field_path,
                "bind": bind,
                "value": value,
                "value_type": self._field_type_name(value),
            }

        def _projection_views(self, flat_store: dict[str, list[Any]], view_filters: dict[str, list[str]]) -> dict[str, list[dict[str, Any]]]:
            views: dict[str, list[dict[str, Any]]] = {}
            for view_name, paths in view_filters.items():
                rows: list[dict[str, Any]] = []
                for path in paths:
                    item = flat_store.get(path)
                    if not item:
                        continue
                    rows.append({"hash": item[0], "path": item[1], "value": item[2]})
                views[view_name] = rows
            return views

        def _build_message_projection(self, msg_dir: Path) -> dict:
            """Build L1 projection for a message node: flat_store + views."""
            source_path = self._rel_path(msg_dir)
            meta = self._read_meta(msg_dir) or {}
            data = self._read_data(msg_dir) or {}
            fields = []
            flat_store: dict[str, list[Any]] = {}
            view_filters: dict[str, list[str]] = {"all": [], "_meta": [], "_data": []}

            for key, value in meta.items():
                entry = self._projection_field_entry(source_path, "_meta", key, value)
                fields.append(entry)
                flat_store[entry["full_relative_path"]] = [entry["hash"], entry["full_relative_path"], entry["value"]]
                view_filters["all"].append(entry["full_relative_path"])
                view_filters["_meta"].append(entry["full_relative_path"])

            for key, value in data.items():
                entry = self._projection_field_entry(source_path, "_data", key, value)
                fields.append(entry)
                flat_store[entry["full_relative_path"]] = [entry["hash"], entry["full_relative_path"], entry["value"]]
                view_filters["all"].append(entry["full_relative_path"])
                view_filters["_data"].append(entry["full_relative_path"])

            return {
                "source_node": source_path,
                "_meta": {"global_path": f"{source_path}.(_meta.json)", "schema": {k: k for k in meta.keys()}, "value": meta},
                "_data": {"global_path": f"{source_path}.(_data.json)", "schema": {k: k for k in data.keys()}, "value": data},
                "fields": fields,
                "flat_store": flat_store,
                "view_filters": view_filters,
                "views": self._projection_views(flat_store, view_filters),
            }

        # ── JSONata eval over projection ─────────────────────

        def _build_jsonata_bindings(self, projection: dict) -> dict[str, Any]:
            flat_store = projection.get("flat_store") or {}
            views = projection.get("views") or {}

            def field(path: str) -> dict[str, Any] | None:
                item = flat_store.get(str(path))
                if not item:
                    return None
                return {"hash": item[0], "path": item[1], "value": item[2]}

            def value(path: str) -> Any:
                item = flat_store.get(str(path))
                return item[2] if item else None

            def view(name: str) -> list[dict[str, Any]]:
                return list(views.get(str(name)) or [])

            return {
                "projection": projection,
                "flat_store": flat_store,
                "views": views,
                "field": field,
                "value": value,
                "view": view,
            }

        def eval_message_projection_jsonata(self, msg_dir: Path, expr: str, *, view_name: str = "all", input_name: str = "view") -> dict:
            """Evaluate JSONata expression against a message projection."""
            if not _HAS_JSONATA:
                return {"error": "jsonata-python not installed (pip install jsonata)"}
            if not msg_dir.is_dir():
                return {"error": f"not found: {self._rel_path(msg_dir)}"}
            meta = self._read_meta(msg_dir) or {}
            if meta.get("type") != "message":
                return {"error": f"not a message node: {self._rel_path(msg_dir)}"}

            projection = self._build_message_projection(msg_dir)
            input_map = {
                "projection": projection,
                "flat_store": projection.get("flat_store") or {},
                "view": (projection.get("views") or {}).get(view_name) or [],
            }
            if input_name not in input_map:
                return {"error": f"unsupported input '{input_name}'"}

            expression = _jsonata_mod.Jsonata(expr)
            bindings = self._build_jsonata_bindings(projection)
            expression.assign("projection", bindings["projection"])
            expression.assign("flat_store", bindings["flat_store"])
            expression.assign("views", bindings["views"])
            expression.register_lambda("field", bindings["field"])
            expression.register_lambda("value", bindings["value"])
            expression.register_lambda("view", bindings["view"])
            result = expression.evaluate(input_map[input_name])
            return {
                "ok": True,
                "source": self._rel_path(msg_dir),
                "input": input_name,
                "view": view_name,
                "expr": expr,
                "result": result,
                "projection": projection,
            }

        # ── Checkpoint ───────────────────────────────────────

        def create_message_checkpoint(self, msg_dir: Path, user: str) -> dict:
            """Create child checkpoint node capturing message projection state."""
            if not msg_dir.is_dir():
                return {"error": f"not found: {self._rel_path(msg_dir)}"}
            meta = self._read_meta(msg_dir) or {}
            if meta.get("type") != "message":
                return {"error": f"not a message node: {self._rel_path(msg_dir)}"}

            projection = self._build_message_projection(msg_dir)
            checkpoint_name = self._next_slot_id(msg_dir, "checkpoint")
            checkpoint_dir = msg_dir / checkpoint_name
            checkpoint_dir.mkdir()

            checkpoint_meta = {
                "type": "message", "kind": "checkpoint",
                "user": user, "ts": utc_now(),
                "source": projection["source_node"],
            }
            checkpoint_data = {
                "projection": projection,
                "resolved": {"meta": projection["_meta"]["value"], "data": projection["_data"]["value"]},
            }
            self._write_meta(checkpoint_dir, checkpoint_meta)
            self._write_data(checkpoint_dir, checkpoint_data)
            self._append_exec_entry(msg_dir, {
                "op": "checkpoint", "user": user, "ts": checkpoint_meta["ts"],
                "checkpoint": self._rel_path(checkpoint_dir),
                "source": projection["source_node"],
                "resolved": checkpoint_data["resolved"],
            })
            return {
                "ok": True, "source": self._rel_path(msg_dir),
                "projection": projection,
                "checkpoint": {"path": self._rel_path(checkpoint_dir), "meta": checkpoint_meta, "data": checkpoint_data},
            }

        # ── Template aggregation ──────────────────────────

        def _build_template_aggregation(self, template_type: str, scope_dir: Path) -> dict:
            """Aggregate projection of all instances matching template type.
            e.g. type='msg' finds all msg_* dirs, builds projection for each, unions flat_stores."""
            prefix = f"{template_type}_"
            instances = []
            merged_flat_store: dict[str, list[Any]] = {}
            merged_fields: list[dict] = []
            instance_views: dict[str, dict] = {}

            for child in sorted(scope_dir.iterdir(), key=lambda p: p.name):
                if not child.is_dir() or child.name.startswith("_"):
                    continue
                if not child.name.startswith(prefix):
                    continue
                meta = self._read_meta(child)
                if not meta or meta.get("type") != template_type:
                    # Also check by prefix match even without exact type
                    if meta and meta.get("type"):
                        continue

                projection = self._build_message_projection(child)
                instance_id = child.name
                instances.append({
                    "id": instance_id,
                    "path": self._rel_path(child),
                    "meta": meta or {},
                })

                # Namespace fields under instance_id
                for field_path, entry in projection.get("flat_store", {}).items():
                    namespaced = f"{instance_id}.{field_path}"
                    merged_flat_store[namespaced] = [entry[0], namespaced, entry[2]]
                    merged_fields.append({
                        "instance": instance_id,
                        "path": field_path,
                        "namespaced_path": namespaced,
                        "hash": entry[0],
                        "value": entry[2],
                    })

                # Per-instance views
                instance_views[instance_id] = projection.get("views", {})

            return {
                "ok": True,
                "type": template_type,
                "scope": self._rel_path(scope_dir),
                "count": len(instances),
                "instances": instances,
                "flat_store": merged_flat_store,
                "fields": merged_fields,
                "instance_views": instance_views,
            }

        def _read_json(self, path: Path):
            if path.exists():
                return json.loads(path.read_text(encoding="utf-8"))
            return None

        def _write_json(self, path: Path, data: Any):
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")

        def _container_dir(self, container_id: str) -> Path:
            return self.containers_dir / container_id

        def _read_container_meta(self, container_id: str) -> dict:
            return self._read_json(self._container_dir(container_id) / "_meta.json") or {}

        def _read_container_state(self, container_id: str) -> dict:
            """Read container state. Try state.json cache first, fallback to log replay."""
            cached = self._read_json(self._container_dir(container_id) / "state.json")
            if cached:
                return cached
            return self._container_state_from_log(container_id)

        def _container_state_from_log(self, container_id: str) -> dict:
            """Replay cmd_log.jsonl to rebuild container state."""
            log_path = self._container_dir(container_id) / "cmd_log.jsonl"
            if not log_path.exists():
                return {}
            state: dict[str, Any] = {}
            for line in log_path.read_text(encoding="utf-8").splitlines():
                line = line.strip()
                if not line:
                    continue
                try:
                    entry = json.loads(line)
                except json.JSONDecodeError:
                    continue
                # Replay state mutations from log entries
                cmd = entry.get("cmd", "")
                if cmd == "cselect" and entry.get("args"):
                    state["selected"] = entry["args"][0]
                elif "state_patch" in entry:
                    # Generic state patch entry
                    for k, v in entry["state_patch"].items():
                        self._set_by_dotpath(state, k, v)
            return state

        def _write_container_state(self, container_id: str, state: dict):
            """Write container state cache + append to exec log."""
            self._write_json(self._container_dir(container_id) / "state.json", state)

        def _append_container_log(self, container_id: str, entry: dict):
            path = self._container_dir(container_id) / "cmd_log.jsonl"
            with open(path, "a", encoding="utf-8") as f:
                f.write(json.dumps(entry, ensure_ascii=False) + "\n")

        def _projection_field_name(self, source_path: str, canonical_path: str) -> str:
            normalized_source = str(source_path or "").replace("\\", "/").strip(".")
            normalized_path = self._normalize_atomic_path(canonical_path)
            if normalized_source and normalized_path.startswith(normalized_source + "."):
                return normalized_path[len(normalized_source) + 1:]
            return normalized_path.split(".")[-1]

        def _projection_bind_entry(self, source_path: str, local_root: str, canonical_path: str, local_path: str | None = None) -> dict:
            normalized_bind = self._normalize_atomic_path(canonical_path)
            resolved_local_path = str(local_path or self._projection_field_name(source_path, canonical_path)).strip(".")
            read = self.atomic_read(normalized_bind)
            entry = {
                "kind": "field",
                "path": f"{local_root}.{resolved_local_path}" if local_root else resolved_local_path,
                "local_name": resolved_local_path.split(".")[-1],
                "bind": normalized_bind,
                "atomic_path": normalized_bind,
            }
            if read.get("error"):
                entry["value"] = None
                entry["value_type"] = "null"
                entry["error"] = read.get("error")
            else:
                entry["value"] = read.get("value")
                entry["value_type"] = type(read.get("value")).__name__ if read.get("value") is not None else "null"
            return entry

        def _projection_local_key(self, local_root: str, field_path: str) -> str:
            path = str(field_path or "").strip(".")
            prefix = f"{local_root}."
            if local_root and path.startswith(prefix):
                return path[len(prefix):]
            return path

        def _projection_op_path(self, op: str) -> Path:
            return self.templates_dir / "root" / "runtime" / "projection-ops" / f"{op}.py"

        def _resolve_projection_op(self, op: str):
            op_name = str(op or "").strip().lower()
            if not op_name:
                return None
            op_path = self._projection_op_path(op_name)
            if not op_path.is_file():
                return None
            return self._load_cmd_module(op_path)

        def _table_op_path(self, op: str) -> Path:
            return self.templates_dir / "root" / "runtime" / "table-ops" / f"{op}.py"

        def _resolve_table_op(self, op: str):
            op_name = str(op or "").strip().lower()
            if not op_name:
                return None
            op_path = self._table_op_path(op_name)
            if not op_path.is_file():
                return None
            return self._load_cmd_module(op_path)

        def _projection_rule_entry(self, local_root: str, rule: dict, value_map: dict[str, Any]) -> dict:
            field_path = str(rule.get("path") or "").strip(".")
            op = str(rule.get("op") or "").strip().lower()
            args = rule.get("args") or []
            if not field_path:
                return {
                    "kind": "field",
                    "path": f"{local_root}.invalid_rule" if local_root else "invalid_rule",
                    "local_name": "invalid_rule",
                    "value": None,
                    "value_type": "null",
                    "error": "projection rule path is required",
                    "rule": rule,
                }
            if not isinstance(args, list):
                args = []

            value = None
            error = None
            op_execute = self._resolve_projection_op(op)
            if op_execute:
                try:
                    op_result = op_execute(rule, local_root, value_map, self)
                except Exception as exc:
                    op_result = {"error": str(exc)}
                if isinstance(op_result, dict):
                    error = op_result.get("error")
                    value = op_result.get("value")
                else:
                    value = op_result
            else:
                error = f"unsupported projection rule op: {op}"

            entry = {
                "kind": "field",
                "path": f"{local_root}.{field_path}" if local_root else field_path,
                "local_name": field_path.split(".")[-1],
                "rule": rule,
                "value": value,
                "value_type": type(value).__name__ if value is not None else "null",
            }
            if error:
                entry["error"] = error
            return entry

        def _get_by_dotpath(self, data: Any, path: str):
            cur = data
            for part in path.split("."):
                if isinstance(cur, dict):
                    cur = cur.get(part)
                else:
                    return None
            return cur

        def _set_by_dotpath(self, data: dict, path: str, value: Any):
            parts = [p for p in path.split(".") if p]
            if not parts:
                return
            cur = data
            for part in parts[:-1]:
                if part not in cur or not isinstance(cur[part], dict):
                    cur[part] = {}
                cur = cur[part]
            cur[parts[-1]] = value

        def _render_source_template(self, template: str) -> str:
            def repl(match):
                expr = match.group(1)
                parts = expr.split(".")
                if len(parts) >= 4 and parts[0] == "containers" and parts[2] == "state":
                    container_id = parts[1]
                    state = self._read_container_state(container_id)
                    return str(self._get_by_dotpath(state, ".".join(parts[3:])) or "")
                return ""

            return re.sub(r"\{([^{}]+)\}", repl, template)

        def _container_selected_ref(self, container_id: str) -> tuple[str | None, str | None]:
            meta = self._read_container_meta(container_id)
            selected_from = meta.get("selected_from", {})
            if isinstance(selected_from, dict):
                ref_container = selected_from.get("container")
                ref_path = selected_from.get("state_path")
                if isinstance(ref_container, str) and isinstance(ref_path, str):
                    return ref_container, ref_path
            return None, None

        def _container_selected_value(self, container_id: str):
            ref_container, ref_path = self._container_selected_ref(container_id)
            if ref_container and ref_path:
                ref_state = self._read_container_state(ref_container)
                return self._get_by_dotpath(ref_state, ref_path)
            state = self._read_container_state(container_id)
            return self._get_by_dotpath(state, "selected")

        def _read_node_object(self, rel_path: str, include_children: str = "none") -> dict:
            path = self.root / Path(rel_path)
            if not path.is_dir():
                return {"error": f"not found: {rel_path}"}

            node = {
                "id": path.name,
                "path": self._rel_path(path),
                "meta": self._read_meta(path) or {},
                "data": self._read_data(path) or {},
            }

            if include_children == "direct":
                children = []
                for child in sorted(path.iterdir(), key=lambda p: p.name):
                    if not child.is_dir() or child.name.startswith("_"):
                        continue
                    children.append({
                        "id": child.name,
                        "path": self._rel_path(child),
                        "meta": self._read_meta(child) or {},
                        "data": self._read_data(child) or {},
                    })
                node["children"] = children

            return node

        def _atomic_field(self, name: str, path: str, value_type: str, value: Any, origin: str, atomic_root: str, extra: dict | None = None) -> dict:
            normalized_root = atomic_root.replace("\\", "/")
            normalized_path = str(path or "").replace("\\", "/")
            bind = normalized_root if not normalized_path else f"{normalized_root}.{normalized_path}"
            field = {
                "kind": "field",
                "name": name,
                "path": path,
                "value_type": value_type,
                "value": value,
                "origin": origin,
                "atomic_root": normalized_root,
                "bind": bind,
                "atomic_path": bind,
            }
            if extra:
                field.update(extra)
            return field

        def _append_json_fields(self, atomic_root: str, prefix: str, value: Any, origin: str, out: list[dict]):
            if isinstance(value, dict):
                out.append(self._atomic_field(prefix.split(".")[-1], prefix, "object", None, origin, atomic_root))
                for key, child in value.items():
                    child_path = f"{prefix}.{key}" if prefix else key
                    self._append_json_fields(atomic_root, child_path, child, origin, out)
                return
            if isinstance(value, list):
                out.append(self._atomic_field(prefix.split(".")[-1], prefix, "list", value, origin, atomic_root))
                return
            out.append(self._atomic_field(prefix.split(".")[-1], prefix, type(value).__name__ if value is not None else "null", value, origin, atomic_root))

        def _build_fs_node_fields(self, rel_path: str, node: dict, include_children: bool) -> list[dict]:
            atomic_root = rel_path.replace("\\", "/")
            fields: list[dict] = []
            fields.append(self._atomic_field("_meta", "_meta", "object", None, "json_file", atomic_root))
            meta = node.get("meta") or {}
            for key, value in meta.items():
                self._append_json_fields(atomic_root, f"_meta.{key}", value, "json_field", fields)

            fields.append(self._atomic_field("_data", "_data", "object", None, "json_file", atomic_root))
            data = node.get("data") or {}
            for key, value in data.items():
                self._append_json_fields(atomic_root, f"_data.{key}", value, "json_field", fields)

            if include_children:
                for child in node.get("children", []):
                    child_id = child.get("id")
                    if not child_id:
                        continue
                    fields.append(self._atomic_field(
                        child_id,
                        child_id,
                        "node",
                        None,
                        "fs_child",
                        atomic_root,
                        extra={"child_path": child.get("path"), "child_type": child.get("meta", {}).get("type")},
                    ))
            return fields

        def _normalize_atomic_path(self, atomic_path: str) -> str:
            path = str(atomic_path or "").strip().replace("\\", "/")
            if path.startswith("root."):
                path = path[len("root."):]
            if "/" not in path and "._" in path:
                # Support dot notation like pchat.channels.general._data.content
                parts = path.split(".")
                special_idx = next((i for i, part in enumerate(parts) if part in ("_meta", "_data", "_rows")), -1)
                if special_idx >= 0:
                    fs_part = "/".join(parts[:special_idx])
                    rest = ".".join(parts[special_idx:])
                    path = f"{fs_part}.{rest}" if rest else fs_part
            return path

        def _resolve_atomic_target(self, atomic_path: str) -> dict:
            path = self._normalize_atomic_path(atomic_path)
            if not path:
                return {"error": "empty atomic_path"}
            if "._" in path:
                fs_part, field_part = path.split("._", 1)
                special, _, field_path = field_part.partition(".")
                file_kind = f"_{special}"
            else:
                fs_part, file_kind, field_path = path, "", ""
            node_dir = self.root / Path(fs_part)
            if not node_dir.is_dir():
                return {"error": f"atomic node not found: {fs_part}"}
            if file_kind not in ("_meta", "_data"):
                return {"error": f"unsupported atomic target: {atomic_path}"}
            return {
                "ok": True,
                "node_dir": node_dir,
                "node_path": self._rel_path(node_dir),
                "file_kind": file_kind,
                "field_path": field_path,
            }

        def atomic_patch(self, atomic_path: str, value: Any) -> dict:
            target = self._resolve_atomic_target(atomic_path)
            if not target.get("ok"):
                return target
            node_dir: Path = target["node_dir"]
            file_kind = target["file_kind"]
            field_path = target["field_path"]

            if file_kind == "_meta":
                obj = self._read_meta(node_dir) or {}
            else:
                obj = self._read_data(node_dir) or {}

            if not field_path:
                return {"error": f"atomic patch requires field path: {atomic_path}"}
            self._set_by_dotpath(obj, field_path, value)

            if file_kind == "_meta":
                self._write_meta(node_dir, obj)
            else:
                self._write_data(node_dir, obj)

            self._sync_runtime_atomic_path(atomic_path, value)

            return {
                "ok": True,
                "atomic_path": self._normalize_atomic_path(atomic_path),
                "node_path": target["node_path"],
                "file_kind": file_kind,
                "field_path": field_path,
                "value": value,
            }

        def atomic_read(self, atomic_path: str) -> dict:
            target = self._resolve_atomic_target(atomic_path)
            if not target.get("ok"):
                return target
            node_dir: Path = target["node_dir"]
            file_kind = target["file_kind"]
            field_path = target["field_path"]

            if file_kind == "_meta":
                obj = self._read_meta(node_dir) or {}
            else:
                obj = self._read_data(node_dir) or {}

            if not field_path:
                value = obj
            else:
                value = self._get_by_dotpath(obj, field_path)

            return {
                "ok": True,
                "atomic_path": self._normalize_atomic_path(atomic_path),
                "node_path": target["node_path"],
                "file_kind": file_kind,
                "field_path": field_path,
                "value": value,
            }

        def atomic_define_field(self, atomic_path: str, value_type: str | None = None, default: Any = None) -> dict:
            target = self._resolve_atomic_target(atomic_path)
            if not target.get("ok"):
                return target
            node_dir: Path = target["node_dir"]
            file_kind = target["file_kind"]
            field_path = target["field_path"]

            if not field_path:
                return {"error": f"atomic define requires field path: {atomic_path}"}

            if file_kind == "_meta":
                obj = self._read_meta(node_dir) or {}
            else:
                obj = self._read_data(node_dir) or {}

            existing = self._get_by_dotpath(obj, field_path)
            if existing is None:
                if default is not None:
                    value = default
                elif value_type == "object":
                    value = {}
                elif value_type == "list":
                    value = []
                elif value_type == "str":
                    value = ""
                elif value_type == "bool":
                    value = False
                elif value_type in ("int", "float", "number"):
                    value = 0
                else:
                    value = None
                self._set_by_dotpath(obj, field_path, value)
                if file_kind == "_meta":
                    self._write_meta(node_dir, obj)
                else:
                    self._write_data(node_dir, obj)
                self._sync_runtime_atomic_path(atomic_path, value)
                created = True
            else:
                value = existing
                created = False

            return {
                "ok": True,
                "created": created,
                "atomic_path": self._normalize_atomic_path(atomic_path),
                "node_path": target["node_path"],
                "file_kind": file_kind,
                "field_path": field_path,
                "value_type": value_type,
                "value": value,
            }

        def _runtime_atomic_view_path(self, node_type: str, view_name: str) -> Path:
            return self.templates_dir / node_type / "runtime" / "atomic-dsl" / f"{view_name}.json"

        def _atomic_runtime_object_id(self, path_str: str, view_name: str) -> str:
            return f"{path_str.replace('\\', '/')}::{view_name}"

        def _clear_atomic_runtime_refs(self, object_id: str):
            empty_keys: list[str] = []
            for atomic_path, refs in self.atomic_runtime_index.items():
                kept = [ref for ref in refs if ref.get("object_id") != object_id]
                if kept:
                    self.atomic_runtime_index[atomic_path] = kept
                else:
                    empty_keys.append(atomic_path)
            for atomic_path in empty_keys:
                self.atomic_runtime_index.pop(atomic_path, None)

        def _register_atomic_runtime_object(self, object_id: str, payload: dict):
            self.atomic_runtime_objects[object_id] = payload
            self._clear_atomic_runtime_refs(object_id)

            obj = payload.get("object")
            if isinstance(obj, dict):
                for idx, field in enumerate(obj.get("fields", [])):
                    bind = field.get("bind") or field.get("atomic_path")
                    if not bind:
                        continue
                    self.atomic_runtime_index.setdefault(bind, []).append({
                        "object_id": object_id,
                        "kind": "object_field",
                        "field_index": idx,
                    })

            table = payload.get("table")
            if isinstance(table, dict):
                for row_idx, row in enumerate(table.get("rows", [])):
                    for cell_idx, cell in enumerate(row.get("cells", [])):
                        bind = cell.get("bind") or cell.get("atomic_path")
                        if not bind:
                            continue
                        self.atomic_runtime_index.setdefault(bind, []).append({
                            "object_id": object_id,
                            "kind": "table_cell",
                            "row_index": row_idx,
                            "cell_index": cell_idx,
                        })

        def _sync_runtime_atomic_path(self, atomic_path: str, value: Any):
            normalized = self._normalize_atomic_path(atomic_path)
            for ref in list(self.atomic_runtime_index.get(normalized, [])):
                payload = self.atomic_runtime_objects.get(ref.get("object_id"))
                if not payload:
                    continue
                if ref.get("kind") == "object_field":
                    fields = payload.get("object", {}).get("fields", [])
                    idx = ref.get("field_index")
                    if isinstance(idx, int) and 0 <= idx < len(fields):
                        fields[idx]["value"] = value
                elif ref.get("kind") == "table_cell":
                    rows = payload.get("table", {}).get("rows", [])
                    row_idx = ref.get("row_index")
                    cell_idx = ref.get("cell_index")
                    if isinstance(row_idx, int) and 0 <= row_idx < len(rows):
                        cells = rows[row_idx].get("cells", [])
                        if isinstance(cell_idx, int) and 0 <= cell_idx < len(cells):
                            cells[cell_idx]["value"] = value

        def _load_atomic_view_spec(self, path_str: str, view_name: str) -> dict:
            node_path = self.root / Path(path_str)
            if not node_path.is_dir():
                return {"error": f"not found: {path_str}"}
            meta = self._read_meta(node_path) or {}
            node_type = meta.get("type")
            if not node_type:
                return {"error": f"node has no type: {path_str}"}
            spec_path = self._runtime_atomic_view_path(node_type, view_name)
            spec = self._read_json(spec_path)
            if not isinstance(spec, dict):
                return {"error": f"atomic view not found: {node_type}/{view_name}"}
            return {"ok": True, "node_type": node_type, "spec": spec}

        def load_atomic_view(self, path_str: str, view_name: str = "object") -> dict:
            loaded = self._load_atomic_view_spec(path_str, view_name)
            if not loaded.get("ok"):
                return loaded

            spec = loaded["spec"]
            kind = spec.get("kind")
            if kind == "object_view":
                include_children = "direct" if spec.get("include", {}).get("children") else "none"
                node = self._read_node_object(path_str, include_children=include_children)
                if node.get("error"):
                    return node
                fields = self._build_fs_node_fields(path_str, node, include_children == "direct")
                result = {
                    "ok": True,
                    "path": path_str,
                    "view": view_name,
                    "node_type": loaded["node_type"],
                    "spec": spec,
                    "object": {
                        "kind": "object",
                        "atomic_root": path_str.replace("\\", "/"),
                        "node": node,
                        "fields": fields,
                    },
                }
                result["object_id"] = self._atomic_runtime_object_id(path_str, view_name)
                self._register_atomic_runtime_object(result["object_id"], result)
                return result

            if kind == "children_table":
                node = self._read_node_object(path_str, include_children="direct")
                if node.get("error"):
                    return node
                rows = []
                lift = spec.get("lift", [])
                for child in node.get("children", []):
                    row_root = child.get("path", "").replace("\\", "/")
                    row = {
                        "row_key": child.get("id"),
                        "path": child.get("path"),
                        "row_root": row_root,
                        "row_bind": row_root,
                    }
                    cells = [
                        self._atomic_field(
                            child.get("id") or "row",
                            "",
                            "node",
                            None,
                            "fs_child",
                            row_root,
                            extra={"child_path": child.get("path"), "child_type": child.get("meta", {}).get("type")},
                        )
                    ]
                    for field_path in lift:
                        if field_path.startswith("_meta."):
                            value = self._get_by_dotpath(child.get("meta", {}), field_path[len("_meta."):])
                            row[field_path] = value
                            cells.append(self._atomic_field(field_path.split(".")[-1], field_path, type(value).__name__ if value is not None else "null", value, "lifted_meta", row_root))
                        elif field_path.startswith("_data."):
                            value = self._get_by_dotpath(child.get("data", {}), field_path[len("_data."):])
                            row[field_path] = value
                            cells.append(self._atomic_field(field_path.split(".")[-1], field_path, type(value).__name__ if value is not None else "null", value, "lifted_data", row_root))
                    row["cells"] = cells
                    rows.append(row)
                result = {
                    "ok": True,
                    "path": path_str,
                    "view": view_name,
                    "node_type": loaded["node_type"],
                    "spec": spec,
                    "table": {
                        "kind": "table",
                        "atomic_root": path_str.replace("\\", "/"),
                        "columns": ["row_key"] + lift,
                        "rows": rows,
                    },
                }
                result["object_id"] = self._atomic_runtime_object_id(path_str, view_name)
                self._register_atomic_runtime_object(result["object_id"], result)
                return result

            return {"error": f"unsupported atomic view kind: {kind}"}

        def _container_has_selection(self, meta: dict) -> bool:
            selected_from = meta.get("selected_from", {})
            if not isinstance(selected_from, dict):
                return True
            ref_container = selected_from.get("container")
            ref_path = selected_from.get("state_path")
            if not (ref_container and ref_path):
                return True
            ref_state = self._read_container_state(ref_container)
            selected_value = self._get_by_dotpath(ref_state, ref_path)
            return selected_value not in (None, "")

        def _resolve_container_source(self, meta: dict, state: dict) -> str:
            if not self._container_has_selection(meta):
                return ""
            resolve = meta.get("resolve", {})
            if "source_root" in resolve:
                return resolve["source_root"]
            if "source_template" in resolve:
                return self._render_source_template(resolve["source_template"])
            raise ValueError("container resolve source is missing")

        def _build_resolved_object(self, container_id: str, meta: dict, state: dict, source_path: str, source_node: dict) -> dict:
            resolved = {
                "container_id": container_id,
                "state": state,
                "source": {
                    "path": source_path,
                    "meta": source_node.get("meta", {}),
                    "data": source_node.get("data", {}),
                },
            }
            if "children" in source_node:
                resolved["items"] = source_node["children"]
            else:
                resolved["item"] = {
                    "id": source_node.get("id"),
                    "path": source_node.get("path"),
                    "meta": source_node.get("meta", {}),
                    "data": source_node.get("data", {}),
                }
            return resolved

        def _collect_source_refs(self, resolved: dict) -> list[dict]:
            refs = []
            src = resolved.get("source")
            if src:
                refs.append({"path": src.get("path"), "hash": src.get("meta", {}).get("hash")})
            for item in resolved.get("items", []):
                refs.append({"path": item.get("path"), "hash": item.get("meta", {}).get("hash")})
            item = resolved.get("item")
            if item:
                refs.append({"path": item.get("path"), "hash": item.get("meta", {}).get("hash")})
            return refs

        def _materialize_projection_container(self, container_id: str, meta: dict, state: dict, persist: bool = True) -> dict:
            projection = meta.get("projection", {}) if isinstance(meta.get("projection"), dict) else {}
            source_path = str(projection.get("source_path") or "").replace("\\", "/")
            local_root = str(projection.get("local_root") or "projection")
            fields = projection.get("fields") or []
            rules = projection.get("rules") or []
            if not isinstance(fields, list):
                fields = []
            if not isinstance(rules, list):
                rules = []

            resolved_fields = []
            value_map: dict[str, Any] = {}
            for field_spec in fields:
                if isinstance(field_spec, str) and field_spec.strip():
                    entry = self._projection_bind_entry(source_path, local_root, field_spec)
                elif isinstance(field_spec, dict):
                    bind = str(field_spec.get("bind") or "").strip()
                    if not bind:
                        continue
                    entry = self._projection_bind_entry(source_path, local_root, bind, field_spec.get("path"))
                else:
                    continue
                resolved_fields.append(entry)
                local_key = self._projection_local_key(local_root, entry.get("path", ""))
                value_map[local_key] = entry.get("value")
                value_map[entry.get("local_name", local_key)] = entry.get("value")

            for rule in rules:
                if not isinstance(rule, dict):
                    continue
                entry = self._projection_rule_entry(local_root, rule, value_map)
                resolved_fields.append(entry)
                local_key = self._projection_local_key(local_root, entry.get("path", ""))
                value_map[local_key] = entry.get("value")
                value_map[entry.get("local_name", local_key)] = entry.get("value")

            resolved = {
                "container_id": container_id,
                "state": state,
                "source": {
                    "path": source_path or None,
                    "meta": meta,
                    "data": {},
                },
                "projection": {
                    "kind": "projection_object",
                    "local_root": local_root,
                    "source_path": source_path or None,
                    "fields": resolved_fields,
                },
            }
            rows = flatten_json(resolved, object_name=container_id)
            refs = [{"path": source_path, "hash": None}] if source_path else []
            if persist:
                sdir = self._sandbox_dir(container_id)
                sdir.mkdir(parents=True, exist_ok=True)
                self._write_json(sdir / "_meta.json", {
                    "container_id": container_id,
                    "source_path": source_path or None,
                    "kind": "projection",
                })
                self._write_json(sdir / "resolved.json", resolved)
                self._write_json(sdir / "rows.json", {"rows": rows})
                self._write_json(sdir / "source_refs.json", {"refs": refs})
            return {
                "ok": True,
                "container_id": container_id,
                "sandbox": self._rel_path(self._sandbox_dir(container_id)),
                "resolved": resolved,
                "rows": rows,
                "refs": refs,
            }

        def _materialize_table_container(self, container_id: str, meta: dict, state: dict, persist: bool = True) -> dict:
            runtime_meta = json.loads(json.dumps(meta))
            table_meta = runtime_meta.get("table", {}) if isinstance(runtime_meta.get("table"), dict) else {}
            autoload = table_meta.get("autoload") if isinstance(table_meta.get("autoload"), dict) else None
            if autoload:
                autoload_spec = json.loads(json.dumps(autoload))
                pagination = state.get("pagination") if isinstance(state.get("pagination"), dict) else {}
                for key in ("limit", "offset", "before_ref", "after_ref", "from_end", "visible_only"):
                    if key in pagination:
                        autoload_spec[key] = pagination.get(key)
                source_template = str(autoload_spec.pop("source_path_template", "") or "").strip()
                if source_template and not autoload_spec.get("source_path"):
                    autoload_spec["source_path"] = self._render_source_template(source_template)
                source_path = str(autoload_spec.get("source_path") or "").strip()
                if source_path:
                    execute = self._resolve_table_op(str(autoload_spec.get("op") or ""))
                    if execute:
                        try:
                            result = execute(autoload_spec, runtime_meta, self)
                        except Exception as exc:
                            return {"error": str(exc)}
                        if isinstance(result, dict) and result.get("error"):
                            return result
                        next_meta = result.get("meta") if isinstance(result, dict) else None
                        if isinstance(next_meta, dict):
                            runtime_meta = next_meta
                            table_meta = runtime_meta.get("table", {}) if isinstance(runtime_meta.get("table"), dict) else {}

            local_root = str(table_meta.get("local_root") or "table")
            columns = table_meta.get("columns") or []
            rows_meta = table_meta.get("rows") or []
            if not isinstance(columns, list):
                columns = []
            if not isinstance(rows_meta, list):
                rows_meta = []

            resolved_rows = []
            refs = []
            for idx, row_meta in enumerate(rows_meta):
                if not isinstance(row_meta, dict):
                    continue
                projection_id = str(row_meta.get("projection") or "").strip()
                row_key = str(row_meta.get("row_key") or projection_id or idx)
                if not projection_id:
                    continue
                projection = self.materialize_container(projection_id, persist=False)
                if projection.get("error"):
                    resolved_rows.append({
                        "row_key": row_key,
                        "projection": projection_id,
                        "error": projection.get("error"),
                        "cells": [],
                    })
                    continue
                proj = projection.get("resolved", {}).get("projection", {})
                proj_fields = proj.get("fields", []) if isinstance(proj, dict) else []
                field_map = {}
                for field in proj_fields:
                    if not isinstance(field, dict):
                        continue
                    key = field.get("local_name") or self._projection_local_key(str(proj.get("local_root") or ""), field.get("path", ""))
                    field_map[str(key)] = field
                cells = []
                for col in columns:
                    col_name = str(col)
                    source_field = field_map.get(col_name)
                    if source_field:
                        cell = {
                            "kind": "field",
                            "path": f"{local_root}.{row_key}.{col_name}",
                            "local_name": col_name,
                            "bind": source_field.get("bind"),
                            "atomic_path": source_field.get("atomic_path"),
                            "value": source_field.get("value"),
                            "value_type": source_field.get("value_type", "null"),
                        }
                        if source_field.get("rule"):
                            cell["rule"] = source_field.get("rule")
                    else:
                        cell = {
                            "kind": "field",
                            "path": f"{local_root}.{row_key}.{col_name}",
                            "local_name": col_name,
                            "value": None,
                            "value_type": "null",
                        }
                    cells.append(cell)
                resolved_rows.append({
                    "row_key": row_key,
                    "projection": projection_id,
                    "ref": row_meta.get("ref"),
                    "cells": cells,
                })
                refs.append({"path": projection_id, "hash": None})

            resolved = {
                "container_id": container_id,
                "state": state,
                "source": {
                    "path": None,
                    "meta": runtime_meta,
                    "data": {},
                },
                "table": {
                    "kind": "virtual_table",
                    "local_root": local_root,
                    "columns": columns,
                    "rows": resolved_rows,
                },
            }
            rows = flatten_json(resolved, object_name=container_id)
            if persist:
                sdir = self._sandbox_dir(container_id)
                sdir.mkdir(parents=True, exist_ok=True)
                self._write_json(sdir / "_meta.json", {
                    "container_id": container_id,
                    "source_path": None,
                    "kind": "table",
                })
                self._write_json(sdir / "resolved.json", resolved)
                self._write_json(sdir / "rows.json", {"rows": rows})
                self._write_json(sdir / "source_refs.json", {"refs": refs})
            return {
                "ok": True,
                "container_id": container_id,
                "sandbox": self._rel_path(self._sandbox_dir(container_id)),
                "resolved": resolved,
                "rows": rows,
                "refs": refs,
            }

        def _sandbox_dir(self, container_id: str) -> Path:
            return self.sandboxes_dir / container_id

        def _container_action_spec(self, container_id: str, action: str) -> dict:
            meta = self._read_container_meta(container_id)
            defaults = meta.get("action_defaults", {})
            actions = meta.get("actions", {})
            spec = actions.get(action, {})
            merged = {}
            if isinstance(defaults, dict):
                merged.update(defaults)
            if isinstance(spec, dict):
                merged.update(spec)
            return merged

        def _rebuild_many(self, container_ids: list[str]) -> dict[str, dict]:
            return {container_id: self.materialize_container(container_id, persist=False) for container_id in container_ids}

        def _run_action_rebuilds(self, container_id: str, action: str, fallback: list[str]) -> dict[str, dict]:
            spec = self._container_action_spec(container_id, action)
            targets = spec.get("rebuild_containers", fallback)
            if not isinstance(targets, list):
                targets = fallback
            return self._rebuild_many(targets)

        def _action_target_dir(self, container_id: str, action: str) -> Path:
            spec = self._container_action_spec(container_id, action)
            template = spec.get("target_template")
            if template:
                return self.root / Path(self._render_source_template(template))
            raise ValueError(f"container action target_template missing: {container_id}.{action}")

        def materialize_container(self, container_id: str, persist: bool = True) -> dict:
            meta = self._read_container_meta(container_id)
            if not meta:
                return {"error": f"unknown container: {container_id}"}
            state = self._read_container_state(container_id)
            if meta.get("kind") == "projection":
                return self._materialize_projection_container(container_id, meta, state, persist=persist)
            if meta.get("kind") == "table":
                return self._materialize_table_container(container_id, meta, state, persist=persist)
            try:
                source_path = self._resolve_container_source(meta, state)
            except Exception as e:
                return {"error": str(e)}
            if not source_path:
                resolved = {
                    "container_id": container_id,
                    "state": state,
                    "source": {
                        "path": None,
                        "meta": {},
                        "data": {},
                    },
                    "items": [],
                }
                rows = flatten_json(resolved, object_name=container_id)
                refs = []
                if persist:
                    sdir = self._sandbox_dir(container_id)
                    sdir.mkdir(parents=True, exist_ok=True)
                    self._write_json(sdir / "_meta.json", {
                        "container_id": container_id,
                        "source_path": None,
                    })
                    self._write_json(sdir / "resolved.json", resolved)
                    self._write_json(sdir / "rows.json", {"rows": rows})
                    self._write_json(sdir / "source_refs.json", {"refs": refs})
                else:
                    sdir = self._sandbox_dir(container_id)
                return {
                    "ok": True,
                    "container_id": container_id,
                    "sandbox": self._rel_path(sdir),
                    "resolved": resolved,
                    "rows": rows,
                    "refs": refs,
                    "empty": True,
                }
            source_node = self._read_node_object(
                source_path,
                include_children=meta.get("resolve", {}).get("children", "none"),
            )
            if source_node.get("error"):
                return source_node

            resolved = self._build_resolved_object(container_id, meta, state, source_path, source_node)
            rows = flatten_json(resolved, object_name=container_id)
            refs = self._collect_source_refs(resolved)

            sdir = self._sandbox_dir(container_id)
            if persist:
                sdir.mkdir(parents=True, exist_ok=True)
                self._write_json(sdir / "_meta.json", {
                    "container_id": container_id,
                    "source_path": source_path,
                })
                self._write_json(sdir / "resolved.json", resolved)
                self._write_json(sdir / "rows.json", {"rows": rows})
                self._write_json(sdir / "source_refs.json", {"refs": refs})

            return {
                "ok": True,
                "container_id": container_id,
                "sandbox": self._rel_path(sdir),
                "resolved": resolved,
                "rows": rows,
                "refs": refs,
            }

        def container_select_channel(self, name: str, user: str) -> dict:
            container_id = "channels_selector"
            spec = self._container_action_spec(container_id, "select")
            state_path = spec.get("state_path", "selected")
            state = self._read_container_state(container_id)
            self._set_by_dotpath(state, state_path, name)
            self._write_container_state(container_id, state)
            self._append_container_log("channels_selector", {
                "cmd": "cselect",
                "args": [name],
                "user": user,
                "ts": utc_now(),
            })
            mats = self._run_action_rebuilds(container_id, "select", [container_id, "current_channel", "current_channel_messages"])
            return {
                "ok": True,
                "selected": name,
                "selector": mats.get("channels_selector"),
                "current_channel": mats.get("current_channel"),
                "current_channel_messages": mats.get("current_channel_messages"),
            }

        def container_post_selected(self, text: str, user: str) -> dict:
            channel_name = self._container_selected_value("current_channel")
            if not channel_name:
                return {"error": "no selected channel"}
            ch_dir = self._action_target_dir("current_channel", "post")
            if not ch_dir.is_dir():
                return {"error": f"selected channel not found: {channel_name}"}

            ch_scope = self.get_scope(f"channel:{channel_name}")
            ch_scope.cwd = ch_dir
            post_result = self.cmd_post([text], user, ch_scope)
            self._append_container_log("current_channel", {
                "cmd": "cpost",
                "args": [text],
                "user": user,
                "ts": utc_now(),
                "selected": channel_name,
            })
            mats = self._run_action_rebuilds("current_channel", "post", ["channels_selector", "current_channel", "current_channel_messages"])
            return {
                "ok": bool(post_result.get("ok")),
                "selected": channel_name,
                "post": post_result,
                "selector": mats.get("channels_selector"),
                "current_channel": mats.get("current_channel"),
                "current_channel_messages": mats.get("current_channel_messages"),
            }

        def container_create_channel(self, name: str, user: str, scope: "ConsoleScope") -> dict:
            mk_result = self.cmd_mkchannel([name], user, scope)
            if mk_result.get("error"):
                return mk_result

            spec = self._container_action_spec("channels_selector", "create_channel")
            selector_state = self._read_container_state("channels_selector")
            if spec.get("select_new", True):
                selector_state["selected"] = name
            self._write_container_state("channels_selector", selector_state)
            self._append_container_log("channels_selector", {
                "cmd": "cmkchannel",
                "args": [name],
                "user": user,
                "ts": utc_now(),
            })
            mats = self._run_action_rebuilds("channels_selector", "create_channel", ["channels_selector", "current_channel", "current_channel_messages"])
            return {
                "ok": True,
                "selected": name,
                "channel": mk_result,
                "selector": mats.get("channels_selector"),
                "current_channel": mats.get("current_channel"),
                "current_channel_messages": mats.get("current_channel_messages"),
            }

        def container_create_projection(self, container_id: str, source_path: str, local_root: str, fields: list[str], user: str) -> dict:
            if not container_id:
                return {"error": "container_id is required"}
            if not source_path:
                return {"error": "source_path is required"}
            if not local_root:
                return {"error": "local_root is required"}
            normalized_fields = [str(field).strip() for field in fields if str(field).strip()]
            if not normalized_fields:
                return {"error": "at least one canonical field is required"}

            meta = {
                "id": container_id,
                "kind": "projection",
                "projection": {
                    "source_path": source_path.replace("\\", "/"),
                    "local_root": local_root,
                    "fields": normalized_fields,
                },
            }
            state = {
                "local_root": local_root,
            }
            self._ensure_container(container_id, meta, state)
            self._write_json(self._container_dir(container_id) / "_meta.json", meta)
            self._write_container_state(container_id, state)
            self._append_container_log(container_id, {
                "cmd": "mkprojection",
                "user": user,
                "ts": utc_now(),
                "source_path": source_path,
                "local_root": local_root,
                "fields": normalized_fields,
            })
            materialized = self.materialize_container(container_id, persist=False)
            return {
                "ok": True,
                "container_id": container_id,
                "projection": materialized,
            }

        def container_add_projection_rule(self, container_id: str, rule: dict, user: str) -> dict:
            if not container_id:
                return {"error": "container_id is required"}
            if not isinstance(rule, dict):
                return {"error": "projection rule must be an object"}
            field_path = str(rule.get("path") or "").strip()
            op = str(rule.get("op") or "").strip().lower()
            args = rule.get("args") or []
            if not field_path:
                return {"error": "projection rule path is required"}
            if not op:
                return {"error": "projection rule op is required"}
            if not isinstance(args, list):
                return {"error": "projection rule args must be a list"}
            normalized_rule = dict(rule)
            normalized_rule["path"] = field_path
            normalized_rule["op"] = op
            normalized_rule["args"] = [str(arg).strip() for arg in args if str(arg).strip()]

            meta = self._read_container_meta(container_id)
            if not meta:
                return {"error": f"unknown container: {container_id}"}
            if meta.get("kind") != "projection":
                return {"error": f"container is not a projection: {container_id}"}

            projection = meta.get("projection", {}) if isinstance(meta.get("projection"), dict) else {}
            rules = projection.get("rules") or []
            if not isinstance(rules, list):
                rules = []
            rules.append(normalized_rule)
            projection["rules"] = rules
            meta["projection"] = projection
            self._write_json(self._container_dir(container_id) / "_meta.json", meta)
            self._append_container_log(container_id, {
                "cmd": "projectionexec",
                "user": user,
                "ts": utc_now(),
                "rule": normalized_rule,
            })
            materialized = self.materialize_container(container_id, persist=False)
            return {
                "ok": True,
                "container_id": container_id,
                "projection": materialized,
                "rule": normalized_rule,
            }

        def container_add_projection_concat_rule(self, container_id: str, field_path: str, args: list[str], sep: str, user: str) -> dict:
            return self.container_add_projection_rule(container_id, {
                "path": field_path,
                "op": "concat",
                "args": args,
                "sep": sep,
            }, user)

        def container_create_table(self, container_id: str, local_root: str, columns: list[str], user: str) -> dict:
            if not container_id:
                return {"error": "container_id is required"}
            if not local_root:
                return {"error": "local_root is required"}
            normalized_columns = [str(col).strip() for col in columns if str(col).strip()]
            meta = {
                "id": container_id,
                "kind": "table",
                "table": {
                    "local_root": local_root,
                    "columns": normalized_columns,
                    "rows": [],
                },
            }
            state = {"local_root": local_root}
            self._ensure_container(container_id, meta, state)
            self._write_json(self._container_dir(container_id) / "_meta.json", meta)
            self._write_container_state(container_id, state)
            self._append_container_log(container_id, {
                "cmd": "mktable",
                "user": user,
                "ts": utc_now(),
                "local_root": local_root,
                "columns": normalized_columns,
            })
            materialized = self.materialize_container(container_id, persist=False)
            return {
                "ok": True,
                "container_id": container_id,
                "table": materialized,
            }

        def container_add_table_op(self, container_id: str, op_spec: dict, user: str) -> dict:
            if not container_id:
                return {"error": "container_id is required"}
            if not isinstance(op_spec, dict):
                return {"error": "table op must be an object"}
            op = str(op_spec.get("op") or "").strip().lower()
            if not op:
                return {"error": "table op is required"}

            meta = self._read_container_meta(container_id)
            if not meta:
                return {"error": f"unknown container: {container_id}"}
            if meta.get("kind") != "table":
                return {"error": f"container is not a table: {container_id}"}

            execute = self._resolve_table_op(op)
            if not execute:
                return {"error": f"unsupported table op: {op}"}

            try:
                result = execute(op_spec, meta, self)
            except Exception as exc:
                return {"error": str(exc)}
            if isinstance(result, dict) and result.get("error"):
                return result
            if not isinstance(result, dict):
                return {"error": f"invalid table op result: {op}"}

            next_meta = result.get("meta")
            if not isinstance(next_meta, dict):
                return {"error": f"table op did not return meta: {op}"}
            self._write_json(self._container_dir(container_id) / "_meta.json", next_meta)
            self._append_container_log(container_id, {
                "cmd": "tableexec",
                "user": user,
                "ts": utc_now(),
                "op": op_spec,
            })
            materialized = self.materialize_container(container_id, persist=False)
            return {
                "ok": True,
                "container_id": container_id,
                "table": materialized,
                "op": op_spec,
            }

        def container_set_table_window(self, container_id: str, limit: int | None = None, offset: int | None = None, before_ref: str = "", after_ref: str = "", user: str = "system") -> dict:
            if not container_id:
                return {"error": "container_id is required"}
            meta = self._read_container_meta(container_id)
            if not meta:
                return {"error": f"unknown container: {container_id}"}
            if meta.get("kind") != "table":
                return {"error": f"container is not a table: {container_id}"}

            state = self._read_container_state(container_id)
            pagination = state.get("pagination") if isinstance(state.get("pagination"), dict) else {}
            if limit is not None:
                pagination["limit"] = max(0, int(limit))
            if offset is not None:
                pagination["offset"] = max(0, int(offset))
            pagination["before_ref"] = str(before_ref or "").strip()
            pagination["after_ref"] = str(after_ref or "").strip()
            if pagination["before_ref"]:
                pagination["after_ref"] = ""
            if pagination["after_ref"]:
                pagination["before_ref"] = ""
            state["pagination"] = pagination
            self._write_container_state(container_id, state)
            self._append_container_log(container_id, {
                "cmd": "tablewindow",
                "user": user,
                "ts": utc_now(),
                "pagination": pagination,
            })
            materialized = self.materialize_container(container_id, persist=False)
            return {
                "ok": True,
                "container_id": container_id,
                "table": materialized,
                "pagination": pagination,
            }

        def container_patch_selected(self, raw_path: str, value: Any, user: str) -> dict:
            channel_name = self._container_selected_value("current_channel")
            if not channel_name:
                return {"error": "no selected channel"}
            channel_dir = self._action_target_dir("current_channel", "patch")
            if not channel_dir.is_dir():
                return {"error": f"selected channel not found: {channel_name}"}

            target_dir = channel_dir
            field_path = raw_path
            parts = raw_path.split(".")
            candidate = channel_dir / parts[0]
            if candidate.is_dir() and len(parts) > 1:
                target_dir = candidate
                field_path = ".".join(parts[1:])

            if field_path.startswith("meta."):
                atomic_path = f"{self._rel_path(target_dir)}._meta.{field_path[len('meta.'):]}"
                patch_result = self.atomic_patch(atomic_path, value)
                if patch_result.get("error"):
                    return patch_result
                target_kind = "meta"
            else:
                atomic_path = f"{self._rel_path(target_dir)}._data.{field_path}"
                patch_result = self.atomic_patch(atomic_path, value)
                if patch_result.get("error"):
                    return patch_result
                target_kind = "data"

            if target_dir != channel_dir and target_dir.is_dir():
                self._append_exec_entry(target_dir, {
                    "op": "patch",
                    "user": user,
                    "ts": utc_now(),
                    "target": raw_path,
                    "target_kind": target_kind,
                    "field_path": field_path,
                    "atomic_path": atomic_path,
                    "value": value,
                })

            self._append_container_log("current_channel", {
                "cmd": "cpatch",
                "args": [raw_path],
                "user": user,
                "ts": utc_now(),
                "selected": channel_name,
                "target": raw_path,
                "atomic_path": atomic_path,
                "value": value,
            })
            mats = self._run_action_rebuilds("current_channel", "patch", ["channels_selector", "current_channel", "current_channel_messages"])
            return {
                "ok": True,
                "selected": channel_name,
                "path": self._rel_path(target_dir),
                "target": raw_path,
                "atomic_path": atomic_path,
                "target_kind": target_kind,
                "value": value,
                "selector": mats.get("channels_selector"),
                "current_channel": mats.get("current_channel"),
                "current_channel_messages": mats.get("current_channel_messages"),
            }

        def container_react_selected(self, msg_id: str, emoji: str, user: str) -> dict:
            channel_name = self._container_selected_value("current_channel")
            if not channel_name:
                return {"error": "no selected channel"}
            base_dir = self._action_target_dir("current_channel", "react")
            msg_dir = base_dir / msg_id
            if not msg_dir.is_dir():
                return {"error": f"message not found: {msg_id}"}

            atomic_path = f"{self._rel_path(msg_dir)}._data.reactions"
            current = self.atomic_read(atomic_path)
            if current.get("error"):
                return current

            reactions = current.get("value")
            if not isinstance(reactions, dict):
                reactions = {}
            entry = reactions.get(emoji)
            if not isinstance(entry, dict):
                entry = {"users": [], "count": 0}
            users = entry.get("users")
            if not isinstance(users, list):
                users = []

            if user in users:
                users = [u for u in users if u != user]
            else:
                users = users + [user]

            if users:
                reactions[emoji] = {"users": users, "count": len(users)}
            else:
                reactions.pop(emoji, None)

            patch_result = self.atomic_patch(atomic_path, reactions)
            if patch_result.get("error"):
                return patch_result
            self._append_exec_entry(msg_dir, {
                "op": "react",
                "user": user,
                "ts": utc_now(),
                "emoji": emoji,
                "atomic_path": patch_result.get("atomic_path"),
                "value": reactions,
            })
            self._append_container_log("current_channel", {
                "cmd": "creact",
                "args": [msg_id, emoji],
                "user": user,
                "ts": utc_now(),
                "selected": channel_name,
                "atomic_path": patch_result.get("atomic_path"),
            })
            mats = self._run_action_rebuilds("current_channel", "react", ["channels_selector", "current_channel", "current_channel_messages"])
            return {
                "ok": True,
                "selected": channel_name,
                "message": msg_id,
                "emoji": emoji,
                "atomic_path": patch_result.get("atomic_path"),
                "reactions": reactions,
                "selector": mats.get("channels_selector"),
                "current_channel": mats.get("current_channel"),
                "current_channel_messages": mats.get("current_channel_messages"),
            }

        def _next_slot_id(self, parent: Path, type_prefix: str) -> str:
            """Find next sequential slot: msg_1, msg_2, ..."""
            existing = []
            for d in parent.iterdir():
                if d.is_dir() and d.name.startswith(type_prefix + "_"):
                    try:
                        num = int(d.name.split("_", 1)[1])
                        existing.append(num)
                    except (ValueError, IndexError):
                        pass
            return f"{type_prefix}_{max(existing, default=0) + 1}"

        def _rel_path(self, path: Path) -> str:
            """Path relative to root."""
            try:
                return str(path.relative_to(self.root)).replace("\\", "/")
            except ValueError:
                return str(path)

        def _children_log_path(self, parent: Path) -> Path:
            return parent / "_children.jsonl"

        def _append_child_ref(self, parent: Path, child: Path):
            rel_child = self._rel_path(child)
            entry = {
                "ref": rel_child,
                "name": child.name,
                "ts": utc_now(),
            }
            meta = self._read_meta(child) or {}
            if meta:
                entry["meta"] = {
                    "type": meta.get("type"),
                    "name": meta.get("name"),
                    "user": meta.get("user"),
                    "ts": meta.get("ts"),
                }
            log_path = self._children_log_path(parent)
            log_path.parent.mkdir(parents=True, exist_ok=True)
            with open(log_path, "a", encoding="utf-8") as f:
                f.write(json.dumps(entry, ensure_ascii=False) + "\n")

        def _read_child_log(self, parent: Path) -> list[dict]:
            log_path = self._children_log_path(parent)
            if not log_path.exists():
                return []
            entries = []
            for line in log_path.read_text(encoding="utf-8").splitlines():
                line = line.strip()
                if not line:
                    continue
                try:
                    parsed = json.loads(line)
                except Exception:
                    continue
                if isinstance(parsed, dict):
                    entries.append(parsed)
            return entries

        # ── Commands ──────────────────────────────────────────

        def cmd_mktype(self, args: list[str], user: str, scope: "ConsoleScope") -> dict:
            """Create a template type."""
            if not args:
                return {"error": "usage: /mktype <name>"}
            name = args[0]
            tpl_dir = self.templates_dir / name
            tpl_dir.mkdir(exist_ok=True)
            for sub in ("commands", "panels", "renders", "views"):
                (tpl_dir / sub).mkdir(exist_ok=True)
            schema = {"fields": {}, "commands": [], "panels": [], "renders": []}
            schema_path = tpl_dir / "schema.json"
            if not schema_path.exists():
                schema_path.write_text(json.dumps(schema, indent=2), encoding="utf-8")
            return {"ok": True, "path": self._rel_path(tpl_dir)}

        def cmd_mkchannel(self, args: list[str], user: str, scope: "ConsoleScope") -> dict:
            """Create a channel (convenience). /mkchannel <name>"""
            if not args:
                return {"error": "usage: /mkchannel <name>"}
            name = args[0]
            # Ensure channels container exists
            channels_dir = self.pchat_dir / "channels"
            channels_dir.mkdir(exist_ok=True)
            if not (channels_dir / "_meta.json").exists():
                self._write_meta(channels_dir, {"type": "channels", "name": "channels"})
            # Create channel node
            ch_dir = channels_dir / name
            if ch_dir.exists():
                meta = self._read_meta(ch_dir) or {}
                return {"ok": True, "path": self._rel_path(ch_dir), "meta": meta, "existed": True}
            ch_dir.mkdir()
            meta = {"type": "channel", "user": user, "ts": utc_now(), "name": name}
            self._write_meta(ch_dir, meta)
            self._write_data(ch_dir, {})
            self._append_child_ref(channels_dir, ch_dir)
            self._append_exec_entry(ch_dir, {
                "op": "mkchannel", "user": user, "ts": meta["ts"], "name": name,
            })
            # Auto-create channel scope
            ch_scope = self.get_scope(f"channel:{name}")
            ch_scope.cwd = ch_dir
            return {"ok": True, "path": self._rel_path(ch_dir), "meta": meta, "scope": f"channel:{name}"}

        def cmd_mk(self, args: list[str], user: str, scope: "ConsoleScope") -> dict:
            """Create a node of given type in current scope. Checks children capability."""
            if len(args) < 2:
                return {"error": "usage: /mk <type> <name>"}
            node_type, name = args[0], args[1]
            # Capability check: can this container accept children of this type?
            if not self._node_can_append(scope.cwd, node_type):
                return {"error": f"cannot create {node_type} in {self._rel_path(scope.cwd)}: no children scope for this type"}
            node_dir = scope.cwd / name
            if node_dir.exists():
                meta = self._read_meta(node_dir) or {}
                return {"ok": True, "path": self._rel_path(node_dir), "meta": meta, "existed": True}
            node_dir.mkdir(parents=True)
            meta = {"type": node_type, "user": user, "ts": utc_now(), "name": name}
            self._write_meta(node_dir, meta)
            self._write_data(node_dir, {})
            self._append_child_ref(scope.cwd, node_dir)
            self._append_exec_entry(node_dir, {
                "op": "mk", "user": user, "ts": meta["ts"],
                "type": node_type, "name": name,
            })
            return {"ok": True, "path": self._rel_path(node_dir), "meta": meta}

        def cmd_cd(self, args: list[str], user: str, scope: "ConsoleScope") -> dict:
            """Navigate: cd name (down), cd .. (up)."""
            if not args:
                return {"ok": True, "path": self._rel_path(scope.cwd)}
            name = args[0]
            if name == "..":
                if scope.cwd == self.root:
                    return {"error": "already at root"}
                scope.cwd = scope.cwd.parent
                return {"ok": True, "path": self._rel_path(scope.cwd)}
            target = scope.cwd / name
            if not target.is_dir():
                # Try searching children by meta.name
                for d in scope.cwd.iterdir():
                    if d.is_dir() and not d.name.startswith("_"):
                        meta = self._read_meta(d)
                        if meta and meta.get("name") == name:
                            target = d
                            break
                if not target.is_dir():
                    return {"error": f"not found: {name}"}
            scope.cwd = target
            meta = self._read_meta(target) or {}
            return {"ok": True, "path": self._rel_path(target), "meta": meta}

        def cmd_select(self, args: list[str], user: str, scope: "ConsoleScope") -> dict:
            """Select a container: creates/updates a named scope with cwd = target node.
            /select <name> — find child by name, create scope 'channel:<name>' pointing to it."""
            if not args:
                return {"error": "usage: /select <name>"}
            name = args[0]
            # Find the target node — search in channels dir first, then scope.cwd
            channels_dir = self.pchat_dir / "channels"
            target = None
            if channels_dir.is_dir():
                candidate = channels_dir / name
                if candidate.is_dir():
                    target = candidate
            if target is None:
                # Fallback: search in current scope cwd
                candidate = scope.cwd / name
                if candidate.is_dir():
                    target = candidate
            if target is None:
                return {"error": f"not found: {name}"}
            # Create/update the channel scope
            scope_name = f"channel:{name}"
            ch_scope = self.get_scope(scope_name)
            ch_scope.cwd = target
            meta = self._read_meta(target) or {}
            return {"ok": True, "path": self._rel_path(target), "meta": meta, "scope": scope_name}

        def cmd_up(self, args: list[str], user: str, scope: "ConsoleScope") -> dict:
            """Alias for cd .. (backward compat)."""
            return self.cmd_cd([".."], user, scope)

        def cmd_dir(self, args: list[str], user: str, scope: "ConsoleScope") -> dict:
            """List children in current scope (compact)."""
            children = []
            for d in sorted(scope.cwd.iterdir(), key=lambda p: p.name):
                if d.is_dir() and not d.name.startswith("_"):
                    meta = self._read_meta(d)
                    entry = {"name": d.name, "path": self._rel_path(d)}
                    if meta:
                        entry["type"] = meta.get("type", "?")
                    children.append(entry)
            return {"children": children, "cwd": self._rel_path(scope.cwd)}

        def cmd_ls(self, args: list[str], user: str, scope: "ConsoleScope") -> dict:
            """List children (full, with data) in current scope."""
            sort_by = "name"
            for a in args:
                if a.startswith("--sort="):
                    sort_by = a.split("=", 1)[1]
            children = []
            for d in scope.cwd.iterdir():
                if d.is_dir() and not d.name.startswith("_"):
                    meta = self._read_meta(d)
                    data = self._read_data(d)
                    entry = {"path": self._rel_path(d), "name": d.name}
                    if meta:
                        entry["meta"] = meta
                    if data:
                        entry["data"] = data
                    children.append(entry)
            if sort_by == "date":
                children.sort(key=lambda c: c.get("meta", {}).get("ts", ""), reverse=True)
            else:
                children.sort(key=lambda c: c["name"])
            return {"children": children, "cwd": self._rel_path(scope.cwd)}

        def cmd_cat(self, args: list[str], user: str, scope: "ConsoleScope") -> dict:
            """Read a slot's content (meta + data)."""
            if not args:
                meta = self._read_meta(scope.cwd)
                data = self._read_data(scope.cwd)
                return {"path": self._rel_path(scope.cwd), "meta": meta, "data": data}
            name = args[0]
            target = scope.cwd / name
            if not target.is_dir():
                return {"error": f"not found: {name}"}
            meta = self._read_meta(target)
            data = self._read_data(target)
            return {"path": self._rel_path(target), "meta": meta, "data": data}

        def cmd_post(self, args: list[str], user: str, scope: "ConsoleScope") -> dict:
            """Create a message in current scope. Checks msg append capability."""
            if not self._node_can_append(scope.cwd, "msg"):
                # Fallback: allow if node type is channel/cards (backward compat)
                meta = self._read_meta(scope.cwd) or {}
                if meta.get("type") not in ("channel", "channels", "cards"):
                    return {"error": f"cannot post in {self._rel_path(scope.cwd)}: no msg children scope"}
            text = " ".join(args) if args else ""
            slot_name = self._next_slot_id(scope.cwd, "msg")
            slot_dir = scope.cwd / slot_name
            slot_dir.mkdir()
            meta = {"type": "message", "user": user, "ts": utc_now()}
            data = {"content": text}
            self._write_meta(slot_dir, meta)
            self._write_data(slot_dir, data)
            self._append_exec_entry(slot_dir, {
                "op": "post",
                "user": user,
                "ts": meta["ts"],
                "meta": meta,
                "data": data,
            })
            self._append_child_ref(scope.cwd, slot_dir)
            return {"ok": True, "path": self._rel_path(slot_dir), "meta": meta, "data": data}

        def cmd_rm(self, args: list[str], user: str, scope: "ConsoleScope") -> dict:
            """Delete a slot."""
            if not args:
                return {"error": "usage: /rm <name>"}
            name = args[0]
            target = scope.cwd / name
            if not target.is_dir():
                return {"error": f"not found: {name}"}
            # Log before deletion
            self._append_exec_entry(scope.cwd, {
                "op": "rm", "user": user, "ts": utc_now(),
                "target": name, "path": self._rel_path(target),
            })
            import shutil
            shutil.rmtree(target)
            return {"ok": True, "removed": name}

        def cmd_reset(self, args: list[str], user: str, scope: "ConsoleScope") -> dict:
            """Clear workspace — remove everything under pchat/."""
            import shutil
            if self.pchat_dir.exists():
                shutil.rmtree(self.pchat_dir)
            self.pchat_dir.mkdir(exist_ok=True)
            # Reset all scopes
            for s in self.scopes.values():
                s.cwd = self.pchat_dir
                s.log.clear()
                s.redo_stack.clear()
            if self.log_path.exists():
                self.log_path.write_text("", encoding="utf-8")
            return {"ok": True}

        def cmd_query(self, args: list[str], user: str, scope: "ConsoleScope") -> dict:
            """Read node by absolute path (relative to root). No cwd mutation.
            Usage: /query <path> [--depth=1] [--limit=50]
            Returns node meta+data and children up to depth/limit."""
            if not args:
                return {"error": "usage: /query <path> [--depth=1] [--limit=50]"}
            path_str = args[0]
            depth = 1
            limit = 50
            for a in args[1:]:
                if a.startswith("--depth="):
                    depth = int(a.split("=", 1)[1])
                elif a.startswith("--limit="):
                    limit = int(a.split("=", 1)[1])
            target = self.root / Path(path_str)
            if not target.is_dir():
                return {"error": f"not found: {path_str}"}
            return self._read_tree(target, depth, limit)

        # ── Projection commands ───────────────────────────

        def cmd_mcheckpoint(self, args: list[str], user: str, scope: "ConsoleScope") -> dict:
            """Create a child checkpoint node inside a message slot."""
            target = scope.cwd
            meta = self._read_meta(target) or {}
            if meta.get("type") == "message":
                if args:
                    return {"error": "usage: /mcheckpoint  (inside message) or /mcheckpoint <msg_id> (inside channel)"}
                return self.create_message_checkpoint(target, user)
            if not args:
                return {"error": "usage: /mcheckpoint <msg_id>"}
            msg_dir = scope.cwd / args[0]
            return self.create_message_checkpoint(msg_dir, user)

        def cmd_mjsonata(self, args: list[str], user: str, scope: "ConsoleScope") -> dict:
            """Evaluate a JSONata expression against a message projection."""
            view_name = "all"
            input_name = "view"
            positional: list[str] = []
            for arg in args:
                if arg.startswith("--view="):
                    view_name = arg.split("=", 1)[1].strip() or "all"
                    continue
                if arg.startswith("--input="):
                    input_name = arg.split("=", 1)[1].strip() or "view"
                    continue
                positional.append(arg)

            target = scope.cwd
            meta = self._read_meta(target) or {}
            if meta.get("type") == "message":
                if not positional:
                    return {"error": "usage: /mjsonata <expr> [--view=all|_meta|_data] [--input=view|projection|flat_store]"}
                expr = " ".join(positional)
                return self.eval_message_projection_jsonata(target, expr, view_name=view_name, input_name=input_name)

            if len(positional) < 2:
                return {"error": "usage: /mjsonata <msg_id> <expr> [--view=...] [--input=...]"}
            msg_dir = scope.cwd / positional[0]
            expr = " ".join(positional[1:])
            return self.eval_message_projection_jsonata(msg_dir, expr, view_name=view_name, input_name=input_name)

        def _read_tree(self, path: Path, depth: int, limit: int) -> dict:
            """Read a node and its children recursively up to depth/limit."""
            node: dict[str, Any] = {"path": self._rel_path(path), "name": path.name}
            meta = self._read_meta(path)
            if meta:
                node["meta"] = meta
            data = self._read_data(path)
            if data:
                node["data"] = data
            if depth > 0:
                children = []
                count = 0
                for d in sorted(path.iterdir(), key=lambda p: p.name):
                    if not d.is_dir() or d.name.startswith("_"):
                        continue
                    if count >= limit:
                        node["truncated"] = True
                        break
                    children.append(self._read_tree(d, depth - 1, limit))
                    count += 1
                node["children"] = children
            return node

        def cmd_session(self, args: list[str], user: str, scope: "ConsoleScope") -> dict:
            """Start a user session. Logs 'user joined' as a system event."""
            return {"ok": True, "user": user, "ts": utc_now(), "event": "session_start"}

        def replay(self, scope_name: str = "CMD") -> int:
            """Replay log to restore state in a scope."""
            if not self.log_path.exists():
                return 0
            scope = self.get_scope(scope_name)
            count = 0
            for line in self.log_path.read_text(encoding="utf-8").splitlines():
                line = line.strip()
                if not line:
                    continue
                try:
                    entry = json.loads(line)
                    cmd = entry.get("cmd", "")
                    cmd_user = entry.get("user", "anon")
                    parts = shlex.split(cmd)
                    if not parts:
                        continue
                    command = parts[0].lstrip("/").lower()
                    handler = getattr(self, f"cmd_{command}", None)
                    if handler:
                        handler(parts[1:], cmd_user, scope)
                        count += 1
                except Exception:
                    continue
            return count

    workspace = PChatWorkspace(Path(root))
    # No replay needed — FS IS the state. Log is for audit/migration only.

    # ── Endpoint logger: every API call → JSONL ──
    import traceback as _tb

    _endpoint_log_dir = workspace.root / "runtime" / "endpoint_logs"
    _endpoint_log_dir.mkdir(parents=True, exist_ok=True)

    def _json_log_safe(value):
        """Return a JSON-serializable copy without dropping runtime object shape."""
        if value is None or isinstance(value, (str, int, float, bool)):
            return value
        if isinstance(value, Path):
            return str(value)
        if isinstance(value, dict):
            return {str(k): _json_log_safe(v) for k, v in value.items()}
        if isinstance(value, (list, tuple, set)):
            return [_json_log_safe(v) for v in value]
        try:
            json.dumps(value, ensure_ascii=False)
            return value
        except TypeError:
            return str(value)

    def _log_endpoint(endpoint: str, req_data: dict, result: dict | None = None, error: str | None = None):
        log_path = _endpoint_log_dir / f"{endpoint}.jsonl"
        entry = {"ts": utc_now(), "endpoint": endpoint, "req": req_data}
        if result is not None:
            ok = result.get("ok")
            err = result.get("error")
            entry["ok"] = ok
            if err:
                entry["error"] = err
            entry["result"] = _json_log_safe(result)
        if error:
            entry["error"] = error
        with open(log_path, "a", encoding="utf-8") as f:
            f.write(json.dumps(entry, ensure_ascii=False, default=str) + "\n")

    def _safe_endpoint(endpoint: str, req_data: dict, fn):
        """Wrap endpoint: log request, catch errors, log result."""
        try:
            result = fn()
            _log_endpoint(endpoint, req_data, result=result if isinstance(result, dict) else {})
            return result
        except Exception as e:
            tb = _tb.format_exc()
            _log_endpoint(endpoint, req_data, error=f"{e}\n{tb}")
            raise

    @app.post("/api/pchat/exec")
    def pchat_exec(req: PChatExecRequest) -> dict:
        return _safe_endpoint("exec", {"cmd": req.cmd, "user": req.user, "scope": req.scope},
            lambda: workspace.exec_cmd(req.cmd, req.user, log=req.log, scope_name=req.scope))

    @app.post("/api/pchat/sys")
    def pchat_sys(req: PChatSysRequest) -> dict:
        """Non-user CMD: binds, triggers, auto-patches. Separate from user input."""
        return workspace.exec_cmd(req.cmd, req.user, log=True, scope_name=req.scope)

    @app.post("/api/pchat/batch")
    def pchat_batch(req: PChatBatchRequest) -> dict:
        """Execute multiple commands in one HTTP request. Returns list of results."""
        def run():
            results = []
            for cmd in req.cmds:
                results.append(workspace.exec_cmd(cmd, req.user, log=req.log, scope_name=req.scope))
            return {"results": results}
        return _safe_endpoint("batch", {"cmds": req.cmds, "user": req.user}, run)

    @app.post("/api/pchat/view")
    def pchat_view(req: PChatStateRequest) -> dict:
        """Return full chat state in one request: channels + messages for active channel."""
        return _safe_endpoint("view", {"channel": req.channel, "user": req.user},
            lambda: _pchat_build_state(req.channel, req.msg_limit, req.user))

    @app.get("/api/endpoint-logs/{endpoint}")
    def get_endpoint_log(endpoint: str, tail: int = 50) -> dict:
        """Read last N entries from endpoint log."""
        log_path = _endpoint_log_dir / f"{endpoint}.jsonl"
        if not log_path.exists():
            return {"endpoint": endpoint, "entries": [], "total": 0}
        lines = log_path.read_text(encoding="utf-8").splitlines()
        entries = []
        for line in lines[-tail:]:
            try:
                entries.append(json.loads(line))
            except json.JSONDecodeError:
                pass
        return {"endpoint": endpoint, "entries": entries, "total": len(lines)}

    @app.get("/api/endpoint-logs")
    def list_endpoint_logs() -> dict:
        """List all endpoint logs with sizes."""
        logs = []
        if _endpoint_log_dir.is_dir():
            for f in sorted(_endpoint_log_dir.glob("*.jsonl")):
                logs.append({"endpoint": f.stem, "size": f.stat().st_size, "lines": sum(1 for _ in open(f, encoding="utf-8"))})
        return {"logs": logs}

    @app.post("/api/pchat/projection")
    def pchat_projection(req: ProjectionRequest) -> dict:
        scope_dir = workspace.root / req.scope if req.scope else workspace.pchat_dir
        if not scope_dir.is_dir():
            scope_dir = workspace.pchat_dir
        return workspace._build_template_aggregation(req.template, scope_dir)

    @app.post("/api/pchat/message-projection")
    def pchat_message_projection(req: MessageProjectionRequest) -> dict:
        return _safe_endpoint(
            "message_projection",
            {"path": req.path},
            lambda: workspace._build_message_projection(workspace.root / Path(req.path)),
        )

    @app.post("/api/atomic/view")
    def atomic_view(req: AtomicViewRequest) -> dict:
        return workspace.load_atomic_view(req.path, req.view)

    @app.post("/api/atomic/patch")
    def atomic_patch(req: AtomicPatchRequest) -> dict:
        return workspace.atomic_patch(req.atomic_path, req.value)

    @app.post("/api/atomic/define-field")
    def atomic_define_field(req: AtomicDefineFieldRequest) -> dict:
        return workspace.atomic_define_field(req.atomic_path, req.value_type, req.default)

    @app.get("/api/pchat/state")
    def pchat_state_get(channel: str | None = None, msg_limit: int = 50, since: int | None = None) -> dict:
        """GET variant — returns channels + optional channel messages.
        since=N: return only exec entries after index N (inverted: 0=latest)."""
        state = _pchat_build_state(channel, msg_limit, "anon")
        if since is not None and isinstance(state.get("messages"), list):
            total = len(state["messages"])
            # since=0 means client has latest, return empty
            # since=5 means client is 5 behind, return last 5
            if since == 0:
                state["messages"] = []
            elif since < total:
                state["messages"] = state["messages"][-since:]
            state["since"] = since
            state["total"] = total
        return state

    def _pchat_build_state(channel: str | None, msg_limit: int, user: str) -> dict:
        selected = workspace._container_selected_value("current_channel")
        if selected and (channel is None or channel == selected):
            selector = workspace.materialize_container("channels_selector")
            current = workspace.materialize_container("current_channel")
            source_path = current.get("resolved", {}).get("source", {}).get("path")
            source_dir = workspace.root / Path(source_path) if source_path else None
            if selector.get("ok") and current.get("ok") and source_dir and source_dir.is_dir():
                state = selector["resolved"].get("state", {})
                channels = []
                for item in selector["resolved"].get("items", []):
                    channels.append({
                        "name": item.get("meta", {}).get("name") or item.get("id"),
                        "path": item.get("path"),
                        "meta": item.get("meta", {}),
                        "data": item.get("data", {}),
                    })
                messages = []
                for item in current["resolved"].get("items", []):
                    data = item.get("data", {}) or {}
                    if data.get("_deleted"):
                        continue
                    messages.append({
                        "name": item.get("id"),
                        "path": item.get("path"),
                        "meta": item.get("meta", {}),
                        "data": data,
                    })
                return {
                    "channels": channels,
                    "messages": messages[-msg_limit:],
                    "active_channel": state.get("selected"),
                    "user": user,
                    "ts": utc_now(),
                    "source": "containers",
                }

        channels_dir = workspace.pchat_dir / "channels"
        channels = []
        if channels_dir.is_dir():
            for d in sorted(channels_dir.iterdir(), key=lambda p: p.name):
                if d.is_dir() and not d.name.startswith("_"):
                    meta = workspace._read_meta(d)
                    entry = {"name": d.name, "path": workspace._rel_path(d)}
                    if meta:
                        entry["meta"] = meta
                    channels.append(entry)

        messages = []
        if channel:
            ch_dir = channels_dir / channel
            if ch_dir.is_dir():
                msg_dirs = [d for d in ch_dir.iterdir() if d.is_dir() and not d.name.startswith("_")]
                msg_dirs.sort(key=lambda d: d.name)
                for d in msg_dirs[-msg_limit:]:
                    meta = workspace._read_meta(d)
                    data = workspace._read_data(d)
                    entry = {"name": d.name, "path": workspace._rel_path(d)}
                    if meta:
                        entry["meta"] = meta
                    if data:
                        entry["data"] = data
                    messages.append(entry)

        return {
            "channels": channels,
            "messages": messages,
            "active_channel": channel,
            "user": user,
            "ts": utc_now(),
        }

    @app.get("/api/imagegen/samplers")
    def get_image_samplers() -> dict:
        return {"samplers": resolve_client().list_image_samplers()}

    @app.post("/api/imagegen")
    def generate_image(request: ImageGenerateRequest) -> dict:
        session = ensure_session(request.session_id)
        client = resolve_client()
        raw = client.generate_image(
            prompt=request.prompt,
            negative_prompt=request.negative_prompt,
            steps=request.steps,
            width=request.width,
            height=request.height,
            cfg_scale=request.cfg_scale,
            sampler_name=request.sampler_name,
            batch_size=request.batch_size,
        )
        preview_image = (raw.get("images") or [None])[0]
        entry = {
            "kind": "imagegen",
            "session_id": session["id"],
            "request": request.model_dump(),
            "response_text": f"Generated {len(raw.get('images') or [])} image(s).",
            "preview_image": preview_image,
            "raw_response": _summarize_image_response(raw),
        }
        session["chat_log"].append(entry)
        return entry

    @app.post("/api/logic/parse")
    def parse_logic(request: LogicParseRequest) -> dict:
        client = resolve_client()
        prompt = build_logic_manifest_prompt(request.analysis_text)
        raw = client.chat(
            prompt=prompt,
            model=request.model or resolve_default_model(),
            system_prompt="Return only the requested manifest format.",
            config=KoboldGenerationConfig(max_tokens=768),
        )
        raw_output = client.extract_text(raw)
        manifest = parse_logic_manifest(raw_output)
        verification = verify_logic(manifest)
        result = LogicExtractionResult(
            prompt=prompt,
            raw_output=raw_output,
            manifest=manifest,
            verification=verification,
        )
        return result.model_dump()

    @app.post("/api/logic/parse-structured")
    def parse_logic_structured(request: LogicParseRequest) -> dict:
        client = resolve_client()
        prompt = build_linear_schema_prompt(request.analysis_text)
        raw = client.chat(
            prompt=prompt,
            model=request.model or resolve_default_model(),
            system_prompt="Return only the requested structured schema format.",
            config=KoboldGenerationConfig(max_tokens=768),
        )
        raw_output = client.extract_text(raw)
        schema = parse_linear_logic_schema(raw_output)
        manifest = linear_schema_to_manifest(schema)
        verification = verify_logic(manifest)
        puzzle_schema: dict[str, Any] | None = None
        sieve_state: list[dict[str, list[str]]] | None = None
        stage_counts: str | None = None
        try:
            bundle = build_schema_backends_from_linear(schema)
            puzzle_schema = bundle.puzzle_schema.to_dict()
            try:
                solved_sieve = bundle.sieve.run_until_fixpoint()
                sieve_state = [
                    {
                        category: sorted(values)
                        for category, values in house.items()
                    }
                    for house in solved_sieve
                ]
                stage_counts = bundle.permutation.render_stage_counts(sieve_state=solved_sieve)
            except RuntimeError:
                sieve_state = None
                stage_counts = bundle.permutation.render_stage_counts()
        except ValueError:
            puzzle_schema = None
            sieve_state = None
            stage_counts = None
        result = LinearSchemaExtractionResult(
            prompt=prompt,
            raw_output=raw_output,
            linear_schema=schema,
            puzzle_schema=puzzle_schema,
            sieve_state=sieve_state,
            stage_counts=stage_counts,
            manifest=manifest,
            verification=verification,
        )
        return result.model_dump()

    @app.post("/api/logic/example")
    def parse_logic_example(model: str | None = None) -> dict:
        example = load_first_thoughts_example(Path(root) / "examples" / "thoughts example.txt")
        payload = LogicParseRequest(analysis_text=prepare_reasoning_excerpt(example.reasoning_text), model=model)
        result = parse_logic(payload)
        result["source_text"] = example.source_text
        result["reasoning_text"] = example.reasoning_text
        return result

    @app.post("/api/logic/verify")
    def verify_logic_schema(request: LogicVerifyRequest) -> dict:
        """Parse raw logic text and verify — supports both manifest and linear schema formats."""
        raw_text = request.raw_schema
        is_atomic_rule_format = "ATOMIC_RULES:" in raw_text.upper()
        is_manifest_format = bool(
            "AXIOMS:" in raw_text.upper()
            or "HYPOTHESES:" in raw_text.upper()
        )

        schema = None
        atomic_rules: AtomicRuleSet | None = None
        puzzle_schema: dict[str, Any] | None = None
        sieve_state: list[dict[str, list[str]]] | None = None
        stage_counts: str | None = None
        format_kind = "atomic_rules" if is_atomic_rule_format else ("manifest" if is_manifest_format else "linear_schema")

        if is_atomic_rule_format:
            atomic_rules = parse_atomic_rule_set(raw_text)
            entities = sorted(
                {
                    item
                    for rule in atomic_rules.rules
                    for item in re.findall(r"pos\('([^']+)'\)", rule)
                }
            )
            # All atomic rules become axioms — verified together, no branches
            manifest = LogicManifest(
                entities=entities,
                axioms=atomic_rules.rules,
                hypotheses={},
            )
        elif is_manifest_format:
            manifest = parse_logic_manifest(raw_text)
        else:
            schema = parse_linear_logic_schema(raw_text)
            manifest = linear_schema_to_manifest(schema)
            try:
                bundle = build_schema_backends_from_linear(schema)
                puzzle_schema = bundle.puzzle_schema.to_dict()
                try:
                    solved_sieve = bundle.sieve.run_until_fixpoint()
                    sieve_state = [
                        {
                            category: sorted(values)
                            for category, values in house.items()
                        }
                        for house in solved_sieve
                    ]
                    stage_counts = bundle.permutation.render_stage_counts(sieve_state=solved_sieve)
                except RuntimeError:
                    sieve_state = None
                    stage_counts = bundle.permutation.render_stage_counts()
            except ValueError:
                pass

        verification = verify_logic(manifest)
        return {
            "format_kind": format_kind,
            "atomic_rules": atomic_rules.model_dump() if atomic_rules else None,
            "linear_schema": schema.model_dump() if schema else None,
            "manifest": manifest.model_dump(),
            "verification": verification.model_dump(),
            "puzzle_schema": puzzle_schema,
            "sieve_state": sieve_state,
            "stage_counts": stage_counts,
        }

    @app.get("/api/logic/example/raw")
    def get_logic_example_raw() -> dict:
        example = load_first_thoughts_example(Path(root) / "examples" / "thoughts example.txt")
        return {
            "source_text": example.source_text,
            "reasoning_text": example.reasoning_text,
            "reasoning_excerpt": prepare_reasoning_excerpt(example.reasoning_text),
        }

    @app.post("/atoms/evaluate")
    def evaluate_single_atom(request: AtomEvaluateRequest) -> dict:
        return run_atom_evaluation(request)

    @app.post("/atoms/evaluate-batch")
    def evaluate_batch_atoms(request: AtomBatchEvaluateRequest) -> dict:
        for item in request.atoms:
            atom_runtime.register(
                ReactiveAtom(
                    atom_id=item.atom_id or item.expression,
                    expression=item.expression,
                    variables=tuple(item.variables),
                    source_claim_id=item.source_claim_id,
                )
            )
        results = atom_runtime.evaluate_many(
            [item.atom_id or item.expression for item in request.atoms],
            request.context,
        )
        return {"results": [result.__dict__ for result in results]}

    @app.post("/hypotheses/evaluate-connected")
    def evaluate_connected_hypotheses(request: HypothesisEvaluateRequest) -> dict:
        try:
            return run_connected_hypothesis_evaluation(request)
        except ValueError as exc:
            raise HTTPException(400, str(exc)) from exc

    return app


def _claim_stub(item: HypothesisEvaluateItem):
    from .assertions import AtomicClaim

    return AtomicClaim(
        claim_id=item.hypothesis_id,
        title=item.title,
        status=ClaimStatus(item.status),
        consequences=list(item.consequences),
    )


def _reaction_to_dict(reaction) -> dict:
    return {
        "root_hypothesis_id": reaction.root_hypothesis_id,
        "checked_hypothesis_ids": list(reaction.checked_hypothesis_ids),
        "affected_hypothesis_ids": list(reaction.affected_hypothesis_ids),
        "affected_cells": list(reaction.affected_cells),
        "consequences": list(reaction.consequences),
        "results": [
            {
                "hypothesis_id": result.hypothesis_id,
                "title": result.title,
                "passed": result.passed,
                "affected_cells": list(result.affected_cells),
                "related_hypothesis_ids": list(result.related_hypothesis_ids),
                "consequences": list(result.consequences),
                "atom_results": [
                    {
                        "atom_id": atom.atom_id,
                        "passed": atom.passed,
                        "variables": list(atom.variables),
                        "source_claim_id": atom.source_claim_id,
                        "error": atom.error,
                    }
                    for atom in result.atom_results
                ],
            }
            for result in reaction.results
        ],
    }


def _compose_chat_prompt(request: ChatRequest, history: list[dict[str, str]] | None = None) -> str:
    sections: list[str] = []
    if request.nickname:
        sections.append(f"User nickname: {request.nickname}")
    if request.user_context:
        sections.append(f"User context:\n{request.user_context.strip()}")
    prior = history or []
    if prior:
        transcript_lines = ["Conversation so far:"]
        for item in prior:
            role = "User" if item.get("role") == "user" else "Assistant"
            transcript_lines.append(f"{role}: {item.get('content', '').strip()}")
        sections.append("\n".join(line for line in transcript_lines if line.strip()))
        sections.append(f"User: {request.message}")
        sections.append("Assistant:")
    else:
        sections.append(request.message)
    return "\n\n".join(section for section in sections if section.strip())


def _summarize_image_response(raw: dict[str, Any]) -> dict[str, Any]:
    return {
        "image_count": len(raw.get("images") or []),
        "parameters": raw.get("parameters") or {},
        "info": raw.get("info"),
    }


def _chat_page_html() -> str:
    return _CHAT_PAGE_HTML


_CHAT_PAGE_HTML = """
<!doctype html>
<html lang="ru">
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1" />
  <title>Kobold Sandbox Chat</title>
  <style>
    :root {
      --bg: #0a1326;
      --bg-2: #101d39;
      --panel: #162443;
      --panel-2: #1e315b;
      --ink: #eef4ff;
      --muted: #92a4c6;
      --line: #2a3c68;
      --accent: #5ca7ff;
      --accent-2: #2f4f88;
      --good: #7ee787;
      --code: #0d1730;
    }
    * { box-sizing: border-box; }
    body {
      margin: 0;
      font-family: "Helvetica Neue", Helvetica, Arial, sans-serif;
      color: var(--ink);
      background:
        radial-gradient(circle at top left, rgba(92, 167, 255, 0.18), transparent 24%),
        radial-gradient(circle at bottom right, rgba(44, 96, 180, 0.22), transparent 28%),
        linear-gradient(180deg, #08101f 0%, #0a1326 100%);
    }
    .shell {
      max-width: 1440px;
      margin: 0 auto;
      padding: 18px;
      display: grid;
      gap: 14px;
    }
    .app-grid {
      display: grid;
      grid-template-columns: 280px minmax(0, 1fr);
      gap: 14px;
    }
    .panel {
      background: var(--panel);
      border: 1px solid var(--line);
      border-radius: 12px;
      padding: 14px;
      box-shadow: 0 10px 28px rgba(0, 0, 0, 0.26);
    }
    h1, h2, h3 { margin: 0 0 12px; }
    .hero {
      display: flex;
      align-items: center;
      justify-content: space-between;
      gap: 16px;
    }
    .hero-copy {
      display: grid;
      gap: 6px;
    }
    .tabs, .actions {
      display: flex;
      gap: 10px;
      flex-wrap: wrap;
      margin-top: 12px;
    }
    .grid {
      display: grid;
      grid-template-columns: minmax(0, 1.55fr) minmax(320px, 0.75fr);
      gap: 16px;
    }
    .subgrid {
      display: grid;
      grid-template-columns: 1fr 1fr;
      gap: 16px;
    }
    .image-grid {
      display: grid;
      grid-template-columns: 1fr 1fr;
      gap: 16px;
    }
    .tab-panel {
      display: none;
    }
    .tab-panel.active {
      display: block;
    }
    textarea, input, select {
      width: 100%;
      padding: 12px;
      border: 1px solid var(--line);
      border-radius: 8px;
      background: rgba(5, 10, 22, 0.56);
      color: var(--ink);
      font: inherit;
      margin-top: 6px;
      margin-bottom: 12px;
    }
    textarea { min-height: 120px; resize: vertical; }
    #message { min-height: 120px; }
    button {
      border: 0;
      border-radius: 8px;
      padding: 10px 14px;
      background: var(--accent);
      color: #071224;
      cursor: pointer;
      font: inherit;
      font-weight: 700;
    }
    button.secondary { background: var(--accent-2); }
    button.secondary, button.tab-button { color: var(--ink); }
    button.tab-button.active { background: var(--accent); color: #071224; }
    pre {
      white-space: pre-wrap;
      word-break: break-word;
      margin: 0;
      font-family: Consolas, monospace;
      font-size: 13px;
    }
    code {
      font-family: Consolas, monospace;
    }
    .log {
      display: grid;
      gap: 12px;
      max-height: 70vh;
      overflow: auto;
    }
    .entry {
      border: 1px solid var(--line);
      border-radius: 10px;
      padding: 12px;
      background: rgba(8, 15, 30, 0.56);
    }
    .image-preview {
      width: 100%;
      border: 1px solid var(--line);
      border-radius: 10px;
      background: #091120;
      min-height: 320px;
      object-fit: contain;
    }
    .chat-shell {
      display: grid;
      grid-template-rows: auto 1fr auto;
      min-height: 78vh;
    }
    .chat-toolbar {
      display: grid;
      grid-template-columns: 1fr 1fr;
      gap: 12px;
      align-items: start;
    }
    .chat-transcript {
      display: grid;
      gap: 12px;
      padding: 8px 0;
      overflow: auto;
      min-height: 48vh;
      max-height: 60vh;
    }
    .bubble {
      border: 1px solid var(--line);
      border-radius: 12px;
      padding: 12px;
      background: rgba(8, 14, 28, 0.72);
    }
    .bubble.user {
      background: rgba(35, 66, 119, 0.55);
      border-color: #365791;
    }
    .bubble-head {
      display: flex;
      justify-content: space-between;
      gap: 12px;
      color: var(--muted);
      font-size: 12px;
      margin-bottom: 8px;
    }
    .bubble-body {
      display: grid;
      gap: 10px;
    }
    .bubble-body p {
      margin: 0;
      line-height: 1.55;
    }
    .code-card {
      border: 1px solid var(--line);
      border-radius: 10px;
      overflow: hidden;
      background: var(--code);
    }
    .code-head {
      display: flex;
      align-items: center;
      justify-content: space-between;
      gap: 8px;
      padding: 8px 10px;
      background: rgba(255,255,255,0.04);
      border-bottom: 1px solid var(--line);
      color: var(--muted);
      font-size: 12px;
    }
    .code-head button {
      padding: 6px 10px;
      font-size: 12px;
    }
    .code-card pre {
      margin: 0;
      padding: 12px;
      white-space: pre-wrap;
      overflow-x: auto;
      background: transparent;
    }
    .composer {
      display: grid;
      gap: 10px;
      margin-top: 10px;
      padding-top: 10px;
      border-top: 1px solid var(--line);
    }
    .composer-actions {
      display: flex;
      justify-content: space-between;
      gap: 10px;
      flex-wrap: wrap;
      align-items: center;
    }
    .right-stack {
      display: grid;
      gap: 14px;
    }
    .kv {
      display: grid;
      gap: 6px;
    }
    .summary {
      display: grid;
      gap: 6px;
      color: var(--muted);
      font-size: 13px;
    }
    .session-list {
      display: grid;
      gap: 8px;
    }
    .session-item {
      border: 1px solid var(--line);
      border-radius: 10px;
      padding: 10px;
      background: rgba(8, 14, 28, 0.72);
      cursor: pointer;
    }
    .session-item.active {
      border-color: var(--accent);
      background: rgba(92, 167, 255, 0.12);
    }
    .session-title {
      font-weight: 700;
      margin-bottom: 4px;
    }
    .hidden {
      display: none !important;
    }
    .modal {
      position: fixed;
      inset: 0;
      display: none;
      align-items: center;
      justify-content: center;
      padding: 24px;
      background: rgba(2, 6, 14, 0.78);
      z-index: 40;
    }
    .modal.active {
      display: flex;
    }
    .modal-card {
      width: min(980px, 100%);
      max-height: 92vh;
      overflow: auto;
      background: var(--panel);
      border: 1px solid var(--line);
      border-radius: 12px;
      padding: 14px;
      display: grid;
      gap: 12px;
    }
    .modal-top {
      display: flex;
      justify-content: space-between;
      gap: 12px;
      align-items: center;
    }
    .badge {
      display: inline-flex;
      align-items: center;
      gap: 8px;
      padding: 6px 10px;
      border-radius: 999px;
      background: rgba(92, 167, 255, 0.14);
      color: var(--accent);
      font-size: 12px;
    }
    .muted { color: var(--muted); }
    @media (max-width: 900px) {
      .app-grid { grid-template-columns: 1fr; }
      .grid, .subgrid, .image-grid { grid-template-columns: 1fr; }
      .chat-toolbar { grid-template-columns: 1fr; }
    }
  </style>
</head>
<body>
  <div class="shell">
    <div class="panel">
      <div class="hero">
        <div class="hero-copy">
          <h1>Kobold Sandbox</h1>
          <div class="muted">Lite-style shell for chat, imagegen and logic tools.</div>
        </div>
        <div class="badge">Local Kobold-compatible frontend</div>
      </div>
      <div class="tabs">
        <button class="secondary tab-button active" data-tab="chatTab">Chat</button>
        <button class="secondary tab-button" data-tab="imageTab">Image</button>
        <button class="secondary tab-button" data-tab="logicTab">Logic</button>
        <button class="secondary tab-button" data-tab="logTab">Log</button>
      </div>
    </div>

    <div id="chatTab" class="tab-panel active">
      <div class="app-grid">
        <div class="panel">
          <h3>Chats</h3>
          <div class="actions">
            <button id="newSession">New Chat</button>
          </div>
          <div id="sessionList" class="session-list"></div>
        </div>
        <div class="grid">
        <div class="panel chat-shell">
          <div class="chat-toolbar">
            <div>
              <h2>Conversation</h2>
              <div class="summary">
                <div>Рендерит chat log в виде переписки.</div>
                <div>На fenced code-block есть кнопка `Image Gen`.</div>
              </div>
            </div>
            <div class="actions" style="justify-content:flex-end">
              <button class="secondary" id="presetAiry">Preset: Airy</button>
              <button class="secondary" id="presetAnalyst">Preset: Analyst</button>
              <button class="secondary" id="clearPrompts">Clear</button>
              <button class="secondary" id="resetChat">New Chat</button>
              <button class="secondary" id="refreshLog">Refresh log</button>
            </div>
          </div>
          <div id="chatTranscript" class="chat-transcript"></div>
          <div class="composer">
            <label>Message</label>
            <textarea id="message">\u041f\u0440\u0438\u0432\u0435\u0442. \u041a\u0440\u0430\u0442\u043a\u043e \u043f\u0440\u0435\u0434\u0441\u0442\u0430\u0432\u044c\u0441\u044f.</textarea>
            <div class="composer-actions">
              <div class="actions" style="margin-top:0">
                <button id="sendChat">Send</button>
                <button class="secondary" id="useMessageAsImagePrompt">Use as image prompt</button>
              </div>
              <div class="muted">`Shift+Enter` for newline</div>
            </div>
          </div>
        </div>
        <div class="right-stack">
          <div class="panel">
            <h3>Session</h3>
            <label>Nickname</label>
            <input id="nickname" placeholder="Airy" value="Airy" />
            <label>User context</label>
            <textarea id="userContext">\u041f\u043e\u043b\u044c\u0437\u043e\u0432\u0430\u0442\u0435\u043b\u044c \u0437\u043e\u0432\u0435\u0442 \u0430\u0441\u0441\u0438\u0441\u0442\u0435\u043d\u0442\u043a\u0443 Airy, \u0436\u0435\u043d\u0441\u043a\u043e\u0433\u043e \u0440\u043e\u0434\u0430. \u041b\u044e\u0431\u0438\u0442 \u043a\u0440\u0430\u0442\u043a\u043e\u0441\u0442\u044c.</textarea>
            <label>System prompt</label>
            <textarea id="systemPrompt">Be concise. Use a calm, direct tone.</textarea>
            <label>Model override</label>
            <input id="model" placeholder="optional model id" />
          </div>
        <div class="panel">
          <h3>Last Result</h3>
          <pre id="result">No requests yet.</pre>
          <pre id="clientError" class="hidden" style="margin-top:10px;color:#ffb4b4"></pre>
        </div>
      </div>
      </div>
      </div>
    </div>

    <div id="imageTab" class="tab-panel">
      <div class="panel">
        <h2>Image Generation</h2>
        <div class="image-grid">
          <div>
            <label>Image prompt</label>
            <textarea id="imagePrompt">portrait of a small brass automaton in warm studio light</textarea>
            <label>Negative prompt</label>
            <textarea id="imageNegative">blurry, distorted, extra limbs, low quality</textarea>
            <div class="subgrid">
              <div>
                <label>Width</label>
                <input id="imageWidth" type="number" value="768" min="64" step="64" />
              </div>
              <div>
                <label>Height</label>
                <input id="imageHeight" type="number" value="768" min="64" step="64" />
              </div>
              <div>
                <label>Steps</label>
                <input id="imageSteps" type="number" value="20" min="1" max="100" />
              </div>
              <div>
                <label>CFG</label>
                <input id="imageCfg" type="number" value="7" min="1" max="30" step="0.5" />
              </div>
            </div>
            <label>Sampler</label>
            <input id="imageSampler" placeholder="Euler" />
            <div class="actions">
              <button id="generateImage">Generate image</button>
              <button class="secondary" id="loadSamplers">Load samplers</button>
            </div>
          </div>
          <div>
            <img id="imagePreview" class="image-preview" alt="Generated image preview" />
            <pre id="imageResult" style="margin-top:12px">No images yet.</pre>
          </div>
        </div>
      </div>
    </div>

    <div id="logicTab" class="tab-panel">
      <div class="subgrid">
        <div class="panel">
          <h2>Logic Tools</h2>
          <div class="actions">
            <button class="secondary" id="runExample">Run thoughts example</button>
            <button class="secondary" id="runStructured">Structured parse</button>
            <button class="secondary" id="loadExampleMessage">Load example to message</button>
          </div>
          <div class="muted" style="margin-bottom:12px">Linear schema in the spirit of typed Einstein rules.</div>
          <textarea id="linearSchema">ENTITIES: [Elisey, Diana, Ilya, Sofya, Lera, Anna, Maksim]
RULES:
- before(Diana, Ilya)
- before(Ilya, $author)
- immediate_after(Lera, Sofya)
- one_of(Elisey, [0, 6])
BRANCHES:
Sofia:
- author(Sofya)
- at(Elisey, 0)</textarea>
          <div class="actions">
            <button class="secondary" id="convertStructured">Convert to manifest</button>
            <button class="secondary" id="useSchemaAsMessage">Use schema in message</button>
            <button class="secondary" id="loadExampleSchema">Load example to schema</button>
            <button class="secondary" id="copyManifestToMessage">Copy manifest to message</button>
          </div>
        </div>
        <div class="panel">
          <h2>Schema Result</h2>
          <pre id="schemaResult">No schema requests yet.</pre>
        </div>
      </div>
    </div>

    <div id="logTab" class="tab-panel">
      <div class="panel">
        <h2>API Log</h2>
        <div id="log" class="log"></div>
      </div>
    </div>
  </div>
  <div id="imageModal" class="modal">
    <div class="modal-card">
      <div class="modal-top">
        <div>
          <h3>Generate image from code block</h3>
          <div class="muted">Можешь поправить prompt перед запуском.</div>
        </div>
        <button class="secondary" id="closeImageModal">Close</button>
      </div>
      <label>Prompt</label>
      <textarea id="modalImagePrompt"></textarea>
      <div class="actions">
        <button id="modalGenerateImage">Generate</button>
        <button class="secondary" id="modalUseNegativeDefault">Reset negative prompt</button>
      </div>
      <img id="modalImagePreview" class="image-preview" alt="Popup generated image preview" />
      <pre id="modalImageResult">No image generated yet.</pre>
    </div>
  </div>
  <script>

    var resultEl = document.getElementById('result');
    var logEl = document.getElementById('log');
    var schemaResultEl = document.getElementById('schemaResult');
    var imageResultEl = document.getElementById('imageResult');
    var imagePreviewEl = document.getElementById('imagePreview');
    var chatTranscriptEl = document.getElementById('chatTranscript');
    var sessionListEl = document.getElementById('sessionList');
    var clientErrorEl = document.getElementById('clientError');
    var imageModalEl = document.getElementById('imageModal');
    var modalImagePromptEl = document.getElementById('modalImagePrompt');
    var modalImagePreviewEl = document.getElementById('modalImagePreview');
    var modalImageResultEl = document.getElementById('modalImageResult');
    var currentSessionId = 'default';

    function byId(id) {
      return document.getElementById(id);
    }

    function showClientError(error) {
      var text = (error && error.message) ? (error.name + ': ' + error.message) : String(error || 'Unknown error');
      if (clientErrorEl) {
        clientErrorEl.textContent = text;
        clientErrorEl.className = '';
      }
      if (window.console && console.error) {
        console.error(error);
      }
    }

    function clearClientError() {
      if (clientErrorEl) {
        clientErrorEl.textContent = '';
        clientErrorEl.className = 'hidden';
      }
    }

    function requestJson(method, url, body, onSuccess) {
      clearClientError();
      var xhr = new XMLHttpRequest();
      xhr.open(method, url, true);
      xhr.setRequestHeader('Content-Type', 'application/json');
      xhr.onreadystatechange = function () {
        if (xhr.readyState !== 4) {
          return;
        }
        if (xhr.status < 200 || xhr.status >= 300) {
          showClientError(new Error('HTTP ' + xhr.status + ' for ' + url));
          return;
        }
        try {
          onSuccess(xhr.responseText ? JSON.parse(xhr.responseText) : {});
        } catch (error) {
          showClientError(error);
        }
      };
      xhr.send(body ? JSON.stringify(body) : null);
    }

    function escapeHtml(text) {
      return String(text || '')
        .replace(/&/g, '&amp;')
        .replace(/</g, '&lt;')
        .replace(/>/g, '&gt;');
    }

    function showTab(tabId) {
      var panels = document.querySelectorAll('.tab-panel');
      var buttons = document.querySelectorAll('.tab-button');
      var i;
      for (i = 0; i < panels.length; i += 1) {
        panels[i].className = panels[i].className.replace(/\\s*active\\b/g, '');
        if (panels[i].id === tabId) {
          panels[i].className += ' active';
        }
      }
      for (i = 0; i < buttons.length; i += 1) {
        buttons[i].className = buttons[i].className.replace(/\\s*active\\b/g, '');
        if (buttons[i].getAttribute('data-tab') === tabId) {
          buttons[i].className += ' active';
        }
      }
    }

    function renderMessageContent(text) {
      var container = document.createElement('div');
      container.className = 'bubble-body';
      var source = String(text || '');
      var regex = /```([\\w+-]*)\\n?([\\s\\S]*?)```/g;
      var lastIndex = 0;
      var match;
      while ((match = regex.exec(source)) !== null) {
        appendProse(container, source.slice(lastIndex, match.index));
        appendCode(container, match[1], match[2]);
        lastIndex = regex.lastIndex;
      }
      appendProse(container, source.slice(lastIndex));
      if (!container.firstChild) {
        appendProse(container, source);
      }
      return container;
    }

    function appendProse(container, text) {
      var trimmed = String(text || '');
      if (!trimmed.replace(/\\s+/g, '')) {
        return;
      }
      var blocks = trimmed.split(/\\n{2,}/);
      var i;
      for (i = 0; i < blocks.length; i += 1) {
        if (!blocks[i].replace(/\\s+/g, '')) {
          continue;
        }
        var p = document.createElement('p');
        p.textContent = blocks[i].replace(/^\\s+|\\s+$/g, '');
        container.appendChild(p);
      }
    }

    function appendCode(container, lang, code) {
      var card = document.createElement('div');
      card.className = 'code-card';
      var head = document.createElement('div');
      head.className = 'code-head';
      var label = document.createElement('span');
      label.textContent = lang || 'code';
      var btn = document.createElement('button');
      btn.className = 'secondary code-imagegen-button';
      btn.setAttribute('type', 'button');
      btn.setAttribute('data-prompt', String(code || '').replace(/^\\s+|\\s+$/g, ''));
      btn.textContent = 'Image Gen';
      var pre = document.createElement('pre');
      var codeEl = document.createElement('code');
      codeEl.textContent = String(code || '').replace(/^\\s+|\\s+$/g, '');
      pre.appendChild(codeEl);
      head.appendChild(label);
      head.appendChild(btn);
      card.appendChild(head);
      card.appendChild(pre);
      container.appendChild(card);
    }

    function renderTranscript(entries) {
      chatTranscriptEl.innerHTML = '';
      var hasChats = false;
      var i;
      for (i = 0; i < entries.length; i += 1) {
        if (entries[i].kind !== 'chat') {
          continue;
        }
        hasChats = true;
        renderBubble((entries[i].request && entries[i].request.nickname) || 'User', 'prompt', (entries[i].request && entries[i].request.message) || '', 'user');
        renderBubble('Assistant', 'response', entries[i].response_text || '', 'assistant');
      }
      if (!hasChats) {
        var empty = document.createElement('div');
        empty.className = 'muted';
        empty.textContent = 'Conversation is empty.';
        chatTranscriptEl.appendChild(empty);
      }
      chatTranscriptEl.scrollTop = chatTranscriptEl.scrollHeight;
    }

    function renderBubble(title, meta, content, kind) {
      var bubble = document.createElement('div');
      bubble.className = kind === 'user' ? 'bubble user' : 'bubble';
      var head = document.createElement('div');
      head.className = 'bubble-head';
      head.innerHTML = '<strong>' + escapeHtml(title) + '</strong><span>' + escapeHtml(meta) + '</span>';
      bubble.appendChild(head);
      bubble.appendChild(renderMessageContent(content));
      chatTranscriptEl.appendChild(bubble);
    }

    function renderSessions(items) {
      sessionListEl.innerHTML = '';
      var i;
      for (i = 0; i < items.length; i += 1) {
        var item = items[i];
        var node = document.createElement('div');
        node.className = 'session-item' + (item.id === currentSessionId ? ' active' : '');
        node.setAttribute('data-session-id', item.id);
        node.innerHTML = '<div class="session-title">' + escapeHtml(item.title || item.id) + '</div><div class="muted">' + (item.message_count || 0) + ' messages</div>';
        sessionListEl.appendChild(node);
      }
    }

    function refreshSessions() {
      requestJson('GET', '/api/chat/sessions', null, function (payload) {
        renderSessions(payload.sessions || []);
      });
    }

    function refreshLog() {
      requestJson('GET', '/api/chat/log?session_id=' + encodeURIComponent(currentSessionId), null, function (payload) {
        var entries = payload.entries || [];
        var i;
        logEl.innerHTML = '';
        renderTranscript(entries);
        for (i = entries.length - 1; i >= 0; i -= 1) {
          var entry = entries[i];
          var node = document.createElement('div');
          node.className = 'entry';
          var promptText = entry.composed_prompt || ((entry.request && entry.request.prompt) || '');
          node.innerHTML = '<div><strong>' + escapeHtml(entry.kind || 'chat') + '</strong></div>' +
            '<div style="margin-top:8px"><strong>Request</strong></div>' +
            '<pre>' + escapeHtml(JSON.stringify(entry.request, null, 2)) + '</pre>' +
            '<div style="margin-top:8px"><strong>Prompt</strong></div>' +
            '<pre>' + escapeHtml(promptText) + '</pre>' +
            '<div style="margin-top:8px"><strong>Response</strong></div>' +
            '<pre>' + escapeHtml(entry.response_text || '') + '</pre>';
          if (entry.preview_image) {
            var img = document.createElement('img');
            img.src = 'data:image/png;base64,' + entry.preview_image;
            img.alt = 'preview';
            img.style.marginTop = '8px';
            img.style.maxWidth = '100%';
            img.style.border = '1px solid #d8cdbf';
            img.style.borderRadius = '12px';
            node.appendChild(img);
          }
          logEl.appendChild(node);
        }
        if (!entries.length) {
          logEl.innerHTML = '<div class="muted">Log is empty.</div>';
        }
        refreshSessions();
      });
    }

    function sendChat() {
      requestJson('POST', '/api/chat', {
        session_id: currentSessionId,
        nickname: byId('nickname').value || null,
        user_context: byId('userContext').value || null,
        system_prompt: byId('systemPrompt').value || null,
        message: byId('message').value,
        model: byId('model').value || null
      }, function (payload) {
        resultEl.textContent = payload.response_text || JSON.stringify(payload, null, 2);
        byId('message').value = '';
        showTab('chatTab');
        refreshLog();
      });
    }

    function resetChat() {
      requestJson('POST', '/api/chat/reset?session_id=' + encodeURIComponent(currentSessionId), null, function () {
        resultEl.textContent = 'No requests yet.';
        chatTranscriptEl.innerHTML = '<div class="muted">Conversation is empty.</div>';
        logEl.innerHTML = '<div class="muted">Log is empty.</div>';
        refreshSessions();
      });
    }

    function generateImage(target) {
      requestJson('POST', '/api/imagegen', {
        session_id: currentSessionId,
        prompt: target === 'modal' ? modalImagePromptEl.value : byId('imagePrompt').value,
        negative_prompt: byId('imageNegative').value || null,
        width: Number(byId('imageWidth').value || 768),
        height: Number(byId('imageHeight').value || 768),
        steps: Number(byId('imageSteps').value || 20),
        cfg_scale: Number(byId('imageCfg').value || 7),
        sampler_name: byId('imageSampler').value || null
      }, function (payload) {
        var image = payload.preview_image;
        if (target === 'modal') {
          modalImageResultEl.textContent = JSON.stringify(payload, null, 2);
          modalImagePreviewEl.src = image ? 'data:image/png;base64,' + image : '';
        } else {
          imageResultEl.textContent = JSON.stringify(payload, null, 2);
          imagePreviewEl.src = image ? 'data:image/png;base64,' + image : '';
          showTab('imageTab');
        }
        refreshLog();
      });
    }

    function loadSamplers() {
      requestJson('GET', '/api/imagegen/samplers', null, function (payload) {
        imageResultEl.textContent = JSON.stringify(payload, null, 2);
        if (payload.samplers && payload.samplers.length && !byId('imageSampler').value) {
          byId('imageSampler').value = payload.samplers[0];
        }
      });
    }

    function runExample() {
      var model = byId('model').value || '';
      var suffix = model ? '?model=' + encodeURIComponent(model) : '';
      requestJson('POST', '/api/logic/example' + suffix, null, function (payload) {
        resultEl.textContent = JSON.stringify(payload, null, 2);
        showTab('logicTab');
      });
    }

    function loadExampleRaw(callback) {
      requestJson('GET', '/api/logic/example/raw', null, callback);
    }

    function runStructured() {
      requestJson('POST', '/api/logic/parse-structured', {
        analysis_text: byId('message').value,
        model: byId('model').value || null
      }, function (payload) {
        schemaResultEl.textContent = JSON.stringify(payload, null, 2);
        showTab('logicTab');
      });
    }

    function convertStructured() {
      requestJson('POST', '/api/logic/parse-structured', {
        analysis_text: byId('linearSchema').value,
        model: byId('model').value || null
      }, function (payload) {
        schemaResultEl.textContent = JSON.stringify(payload, null, 2);
        showTab('logicTab');
      });
    }

    function loadExampleToMessage() {
      loadExampleRaw(function (payload) {
        byId('message').value = payload.reasoning_excerpt || payload.reasoning_text || payload.source_text;
        showTab('chatTab');
      });
    }

    function loadExampleToSchema() {
      loadExampleRaw(function (payload) {
        byId('linearSchema').value = payload.reasoning_excerpt || payload.reasoning_text;
        showTab('logicTab');
      });
    }

    function useSchemaAsMessage() {
      byId('message').value = byId('linearSchema').value;
      showTab('chatTab');
    }

    function copyManifestToMessage() {
      var text = schemaResultEl.textContent || resultEl.textContent || '';
      if (text && text !== 'No schema requests yet.' && text !== 'No requests yet.') {
        byId('message').value = text;
      }
      showTab('chatTab');
    }

    function useMessageAsImagePrompt() {
      byId('imagePrompt').value = byId('message').value;
      showTab('imageTab');
    }

    function openImageModal(promptText) {
      modalImagePromptEl.value = promptText || byId('message').value || '';
      modalImagePreviewEl.src = '';
      modalImageResultEl.textContent = 'No image generated yet.';
      imageModalEl.className = imageModalEl.className.replace(/\\s*active\\b/g, '') + ' active';
    }

    function closeImageModal() {
      imageModalEl.className = imageModalEl.className.replace(/\\s*active\\b/g, '');
    }

    function setAiryPreset() {
      byId('nickname').value = 'Airy';
      byId('userContext').value = '\u041f\u043e\u043b\u044c\u0437\u043e\u0432\u0430\u0442\u0435\u043b\u044c \u0437\u043e\u0432\u0435\u0442 \u0430\u0441\u0441\u0438\u0441\u0442\u0435\u043d\u0442\u043a\u0443 Airy, \u0436\u0435\u043d\u0441\u043a\u043e\u0433\u043e \u0440\u043e\u0434\u0430. \u041b\u044e\u0431\u0438\u0442 \u043a\u0440\u0430\u0442\u043a\u043e\u0441\u0442\u044c.';
      byId('systemPrompt').value = 'Be concise. Use a calm, direct tone.';
    }

    function setAnalystPreset() {
      byId('nickname').value = 'Analyst';
      byId('userContext').value = '\u041d\u0443\u0436\u043d\u044b \u0444\u043e\u0440\u043c\u0430\u043b\u044c\u043d\u044b\u0435 \u043e\u0433\u0440\u0430\u043d\u0438\u0447\u0435\u043d\u0438\u044f \u0438 \u043c\u0438\u043d\u0438\u043c\u0443\u043c \u0441\u043b\u043e\u0432.';
      byId('systemPrompt').value = 'Focus on constraints, explicit formulas, and clean structure.';
    }

    function clearPrompts() {
      byId('nickname').value = '';
      byId('userContext').value = '';
      byId('systemPrompt').value = '';
    }

    function createSession() {
      requestJson('POST', '/api/chat/sessions', { title: '' }, function (payload) {
        currentSessionId = payload.session.id;
        resultEl.textContent = 'No requests yet.';
        refreshLog();
        showTab('chatTab');
      });
    }

    function switchSession(sessionId) {
      currentSessionId = sessionId;
      resultEl.textContent = 'No requests yet.';
      refreshLog();
      showTab('chatTab');
    }

    function bindEvents() {
      var tabButtons = document.querySelectorAll('.tab-button');
      var i;
      for (i = 0; i < tabButtons.length; i += 1) {
        tabButtons[i].onclick = function () { showTab(this.getAttribute('data-tab')); };
      }
      byId('sendChat').onclick = sendChat;
      byId('runExample').onclick = runExample;
      byId('runStructured').onclick = runStructured;
      byId('refreshLog').onclick = refreshLog;
      byId('presetAiry').onclick = setAiryPreset;
      byId('presetAnalyst').onclick = setAnalystPreset;
      byId('clearPrompts').onclick = clearPrompts;
      byId('resetChat').onclick = resetChat;
      byId('newSession').onclick = createSession;
      byId('convertStructured').onclick = convertStructured;
      byId('useSchemaAsMessage').onclick = useSchemaAsMessage;
      byId('loadExampleMessage').onclick = loadExampleToMessage;
      byId('loadExampleSchema').onclick = loadExampleToSchema;
      byId('copyManifestToMessage').onclick = copyManifestToMessage;
      byId('generateImage').onclick = function () { generateImage('panel'); };
      byId('loadSamplers').onclick = loadSamplers;
      byId('useMessageAsImagePrompt').onclick = useMessageAsImagePrompt;
      byId('closeImageModal').onclick = closeImageModal;
      byId('modalGenerateImage').onclick = function () { generateImage('modal'); };
      byId('modalUseNegativeDefault').onclick = function () {
        byId('imageNegative').value = 'blurry, distorted, extra limbs, low quality';
      };
      byId('message').onkeydown = function (event) {
        event = event || window.event;
        if (event.keyCode === 13 && !event.shiftKey) {
          if (event.preventDefault) { event.preventDefault(); }
          sendChat();
          return false;
        }
      };
      document.onclick = function (event) {
        event = event || window.event;
        var target = event.target || event.srcElement;
        while (target) {
          if (target.className && String(target.className).indexOf('code-imagegen-button') >= 0) {
            openImageModal(target.getAttribute('data-prompt') || '');
            return;
          }
          if (target.className && String(target.className).indexOf('session-item') >= 0) {
            switchSession(target.getAttribute('data-session-id'));
            return;
          }
          if (target === imageModalEl) {
            closeImageModal();
            return;
          }
          target = target.parentNode;
        }
      };
      window.onerror = function (msg) {
        showClientError(msg);
      };
    }

    bindEvents();
    refreshLog();

  </script>
</body>
</html>
"""


def _kobold_available(base_url: str) -> bool:
    try:
        with httpx.Client(timeout=2.0, trust_env=False) as client:
            response = client.get(f"{base_url.rstrip('/')}/v1/models")
            if response.is_success:
                return True
            response = client.get(f"{base_url.rstrip('/')}/api/v1/model")
            return response.is_success
    except httpx.HTTPError:
        return False
