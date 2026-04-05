from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Any, Literal

from pydantic import BaseModel, Field


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


# ---------------------------------------------------------------------------
# Universal Node — PNode
# ---------------------------------------------------------------------------

def jpath(data: Any, path: str, default: Any = None) -> Any:
    """Traverse any JSON value by dot-path. Numeric segments = array index."""
    if not path:
        return data
    obj = data
    for part in path.split("."):
        if isinstance(obj, dict):
            obj = obj.get(part)
        elif isinstance(obj, (list, tuple)) and part.isdigit():
            idx = int(part)
            obj = obj[idx] if idx < len(obj) else None
        else:
            return default
        if obj is None:
            return default
    return obj


class PNode(BaseModel):
    """Universal pipeline node. data = any valid JSON."""

    id: str
    parent_id: str | None = None
    data: Any = None
    ts: str = Field(default_factory=utc_now)

    def json_data(self) -> str:
        return json.dumps(self.data, ensure_ascii=False, default=str)

    @classmethod
    def from_json(cls, id: str, json_str: str, **kwargs: Any) -> PNode:
        return cls(id=id, data=json.loads(json_str), **kwargs)

    def get(self, path: str, default: Any = None) -> Any:
        return jpath(self.data, path, default)


class PNodeStore:
    """In-memory store for PNodes."""

    def __init__(self) -> None:
        self._nodes: dict[str, PNode] = {}

    def put(self, node: PNode) -> dict:
        self._nodes[node.id] = node
        return self.to_dict(node)

    def get(self, nid: str) -> PNode | None:
        return self._nodes.get(nid)

    def children(self, parent_id: str) -> list[PNode]:
        return [n for n in self._nodes.values() if n.parent_id == parent_id]

    def query_data(self, path: str, value: Any) -> list[PNode]:
        return [n for n in self._nodes.values() if jpath(n.data, path) == value]

    def remove(self, nid: str) -> bool:
        return self._nodes.pop(nid, None) is not None

    def clear(self) -> None:
        self._nodes.clear()

    def all(self) -> list[PNode]:
        return list(self._nodes.values())

    @staticmethod
    def to_dict(node: PNode) -> dict:
        return {"id": node.id, "parent_id": node.parent_id, "data": node.data, "ts": node.ts}


class Node(BaseModel):
    id: str
    title: str
    branch: str
    parent_id: str | None = None
    summary: str = ""
    kind: str = "generic"
    claim_id: str | None = None
    assumptions: list[str] = Field(default_factory=list)
    consequences: list[str] = Field(default_factory=list)
    created_at: str = Field(default_factory=utc_now)
    updated_at: str = Field(default_factory=utc_now)
    tags: list[str] = Field(default_factory=list)


class SandboxState(BaseModel):
    sandbox_name: str
    kobold_url: str
    default_model: str | None = None
    root_branch: str = "main"
    active_node_id: str
    nodes: dict[str, Node] = Field(default_factory=dict)


class RunResult(BaseModel):
    node_id: str
    prompt: str
    response_text: str
    raw_response: dict[str, Any]
    saved_to: str


class OpenAIChatMessage(BaseModel):
    role: Literal["system", "user", "assistant"]
    content: str


class OpenAIChatCompletionRequest(BaseModel):
    messages: list[OpenAIChatMessage]
    temperature: float = 0.2
    max_tokens: int | None = None
    model: str | None = None


class OpenAIContentPart(BaseModel):
    text: str | None = None
    type: str | None = None


class OpenAIChoiceMessage(BaseModel):
    content: str | list[OpenAIContentPart] | None = None
    role: str | None = None


class OpenAIChoice(BaseModel):
    message: OpenAIChoiceMessage = Field(default_factory=OpenAIChoiceMessage)


class OpenAIChatCompletionResponse(BaseModel):
    choices: list[OpenAIChoice] = Field(default_factory=list)


class OpenAIModelDescriptor(BaseModel):
    id: str
    object: str | None = None
    created: int | None = None
    owned_by: str | None = None
    permission: list[dict[str, Any]] = Field(default_factory=list)
    root: str | None = None


class OpenAIModelsResponse(BaseModel):
    object: str | None = None
    data: list[OpenAIModelDescriptor] = Field(default_factory=list)


class NativeGenerateRequest(BaseModel):
    prompt: str
    temperature: float = 0.2
    max_length: int | None = None
    model: str | None = None


class NativeGenerateResult(BaseModel):
    text: str = ""
    tool_calls: list[dict[str, Any]] = Field(default_factory=list)
    finish_reason: str | None = None
    logprobs: Any = None
    prompt_tokens: int | None = None
    completion_tokens: int | None = None


class NativeGenerateResponse(BaseModel):
    results: list[NativeGenerateResult] = Field(default_factory=list)


class NativeModelResponse(BaseModel):
    result: str | None = None


class ImageGenerationRequest(BaseModel):
    prompt: str
    negative_prompt: str | None = None
    steps: int = 20
    width: int = 512
    height: int = 512
    cfg_scale: float = 7.0
    sampler_name: str | None = None
    batch_size: int = 1


class ImageGenerationResponse(BaseModel):
    images: list[str] = Field(default_factory=list)
    parameters: dict[str, Any] = Field(default_factory=dict)
    info: str | None = None


class ImageSamplerDescriptor(BaseModel):
    name: str
    aliases: list[str] = Field(default_factory=list)
    options: dict[str, Any] = Field(default_factory=dict)
