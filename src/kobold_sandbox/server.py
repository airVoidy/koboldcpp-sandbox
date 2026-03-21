from __future__ import annotations

import uuid
import json
import re
from pathlib import Path
from typing import Any

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse
import httpx
from pydantic import BaseModel

from .assertions import ClaimStatus, HypothesisTree
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
from .reactive import AtomRuntime, ReactiveAtom, evaluate_atom
from .orchestrator import export_graph, run_task
from .kobold_client import KoboldClient, KoboldGenerationConfig
from .storage import Sandbox
from .core import build_schema_backends_from_linear, linear_schema_to_puzzle_schema
from .data_store.api import create_datastore_router


class CreateNodeRequest(BaseModel):
    parent_id: str
    title: str
    summary: str = ""
    tags: list[str] = []


class RunRequest(BaseModel):
    task: str
    model: str | None = None
    commit: bool = False


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


def create_app(root: str) -> FastAPI:
    sandbox = Sandbox(Path(root))
    atom_runtime = AtomRuntime()
    hypothesis_runtime = HypothesisRuntime(atom_runtime)
    app = FastAPI(title="Kobold Sandbox")

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
