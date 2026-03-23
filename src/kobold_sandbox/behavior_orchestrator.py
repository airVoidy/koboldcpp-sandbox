from __future__ import annotations

from collections import Counter
from datetime import datetime, timezone
from enum import Enum
import json
from pathlib import Path
from typing import Any

from pydantic import BaseModel, Field


class PromptKind(str, Enum):
    SYSTEM = "system"
    CONTEXT = "context"
    THINK = "think"
    ANSWER = "answer"


class PromptBlock(BaseModel):
    kind: PromptKind
    content: str

    def render(self) -> str:
        return self.content.strip()


class SystemPrompt(PromptBlock):
    kind: PromptKind = PromptKind.SYSTEM


class ContextPrompt(PromptBlock):
    kind: PromptKind = PromptKind.CONTEXT


class ThinkPrompt(PromptBlock):
    kind: PromptKind = PromptKind.THINK


class AnswerPrompt(PromptBlock):
    kind: PromptKind = PromptKind.ANSWER


class InstructionBundle(BaseModel):
    bundle_id: str
    author_agent: str
    target_agent: str
    strictness: str = "strict"
    blocks: list[PromptBlock] = Field(default_factory=list)

    def render(self) -> str:
        lines: list[str] = []
        for block in self.blocks:
            lines.append(f"[{block.kind.value}]")
            lines.append(block.render())
        return "\n".join(lines).strip()


class AgentProfile(BaseModel):
    agent_name: str
    model_class: str
    scopes: tuple[str, ...] = ()
    description: str = ""


class BindingRule(BaseModel):
    entity_kind: str
    action: str
    allowed_agents: tuple[str, ...]
    priority: int = 0


class AgentBindingRegistry(BaseModel):
    profiles: dict[str, AgentProfile] = Field(default_factory=dict)
    rules: list[BindingRule] = Field(default_factory=list)

    def register_profile(self, profile: AgentProfile) -> None:
        self.profiles[profile.agent_name] = profile

    def register_rule(self, rule: BindingRule) -> None:
        self.rules.append(rule)

    def resolve_agents(self, entity_kind: str, action: str) -> list[AgentProfile]:
        matches = [
            rule
            for rule in self.rules
            if rule.entity_kind == entity_kind and rule.action == action
        ]
        matches.sort(key=lambda item: item.priority, reverse=True)
        ordered_names: list[str] = []
        for rule in matches:
            for agent_name in rule.allowed_agents:
                if agent_name not in ordered_names and agent_name in self.profiles:
                    ordered_names.append(agent_name)
        return [self.profiles[name] for name in ordered_names]


class ClaimLifecycle(str, Enum):
    PENDING = "pending"
    CHECK = "check"
    PASS = "pass"
    FAIL = "fail"
    BLOCKED = "blocked"


class ClaimScope(str, Enum):
    NODE = "node"
    TREE = "tree"


class BehaviorClaim(BaseModel):
    claim_id: str
    owner_node_id: str | None = None
    scope: ClaimScope = ClaimScope.NODE
    evaluator: str
    watched_paths: tuple[str, ...] = ()
    status: ClaimLifecycle = ClaimLifecycle.PENDING
    details: str = ""
    producer_agents: tuple[str, ...] = ()
    pass_agents: tuple[str, ...] = ()
    fail_agents: tuple[str, ...] = ()
    meta: dict[str, Any] = Field(default_factory=dict)


class ElementExecutionResult(BaseModel):
    outcome: str = "next"
    value: Any = None
    updated_paths: tuple[str, ...] = ()


class BehaviorElement(BaseModel):
    element_id: str
    handler: str
    transitions: dict[str, str] = Field(default_factory=dict)
    description: str = ""
    meta: dict[str, Any] = Field(default_factory=dict)


class BehaviorNode(BaseModel):
    format_version: str = "behavior-node/v1"
    revision: int = 0
    updated_at: str = Field(default_factory=lambda: utc_http_now())
    node_id: str
    kind: str
    entry_element: str
    elements: list[BehaviorElement] = Field(default_factory=list)
    data: dict[str, Any] = Field(default_factory=dict)
    meta: dict[str, Any] = Field(default_factory=dict)
    return_key: str | None = None
    claims: list[BehaviorClaim] = Field(default_factory=list)
    current_element_id: str | None = None
    execution_lock: bool = False
    python_refs: dict[str, str] = Field(default_factory=dict)

    def element(self, element_id: str) -> BehaviorElement:
        return next(item for item in self.elements if item.element_id == element_id)

    def to_serialized_dict(self) -> dict[str, Any]:
        payload = self.model_dump(mode="json")
        payload_meta = dict(payload.get("meta", {}))
        payload_meta.pop("serialized_node", None)
        payload_meta.pop("_revision_history", None)
        payload["meta"] = payload_meta
        return payload

    def to_serialized_json(self) -> str:
        return json.dumps(self.to_serialized_dict(), ensure_ascii=False, indent=2)

    def refresh_from_serialized(self, payload: dict[str, Any] | str, *, lock_element_id: str | None = None) -> None:
        incoming = self._coerce_payload(payload)
        refreshed = BehaviorNode.model_validate(incoming)
        locked_id = lock_element_id or (self.current_element_id if self.execution_lock else None)
        if locked_id:
            locked_element = None
            try:
                locked_element = self.element(locked_id)
            except StopIteration:
                locked_element = None
            self._copy_from(refreshed, skip_element_id=locked_id, locked_element=locked_element)
            return
        self._copy_from(refreshed)

    def _copy_from(
        self,
        refreshed: "BehaviorNode",
        *,
        skip_element_id: str | None = None,
        locked_element: BehaviorElement | None = None,
    ) -> None:
        self.format_version = refreshed.format_version
        self.kind = refreshed.kind
        self.entry_element = refreshed.entry_element
        self.data = dict(refreshed.data)
        preserved_serialized = self.meta.get("serialized_node")
        preserved_history = self.meta.get("_revision_history")
        self.meta = dict(refreshed.meta)
        if preserved_serialized is not None and "serialized_node" not in self.meta:
            self.meta["serialized_node"] = preserved_serialized
        if preserved_history is not None and "_revision_history" not in self.meta:
            self.meta["_revision_history"] = preserved_history
        self.return_key = refreshed.return_key
        self.claims = list(refreshed.claims)
        self.python_refs = dict(refreshed.python_refs)
        self.revision = refreshed.revision
        self.updated_at = refreshed.updated_at
        self.current_element_id = refreshed.current_element_id if not self.execution_lock else self.current_element_id
        if skip_element_id is None:
            self.elements = list(refreshed.elements)
            self.execution_lock = refreshed.execution_lock if not self.execution_lock else self.execution_lock
            return
        merged: list[BehaviorElement] = []
        kept_locked = False
        for item in refreshed.elements:
            if item.element_id == skip_element_id and locked_element is not None:
                merged.append(locked_element)
                kept_locked = True
            else:
                merged.append(item)
        if locked_element is not None and not kept_locked:
            merged.append(locked_element)
        self.elements = merged

    @staticmethod
    def _coerce_payload(payload: dict[str, Any] | str) -> dict[str, Any]:
        if isinstance(payload, str):
            return json.loads(payload)
        return payload


class BehaviorTree(BaseModel):
    format_version: str = "behavior-tree/v1"
    revision: int = 0
    updated_at: str = Field(default_factory=lambda: utc_http_now())
    tree_id: str
    root_node_id: str
    nodes: dict[str, BehaviorNode] = Field(default_factory=dict)
    global_meta: dict[str, Any] = Field(default_factory=dict)
    global_claims: list[BehaviorClaim] = Field(default_factory=list)
    bindings: AgentBindingRegistry = Field(default_factory=AgentBindingRegistry)
    python_refs: dict[str, str] = Field(default_factory=dict)

    def node(self, node_id: str) -> BehaviorNode:
        return self.nodes[node_id]

    @classmethod
    def from_serialized_dict(cls, payload: dict[str, Any]) -> "BehaviorTree":
        return cls.model_validate(payload)

    def to_serialized_dict(self) -> dict[str, Any]:
        payload = self.model_dump(mode="json")
        payload_meta = dict(payload.get("global_meta", {}))
        payload_meta.pop("serialized_tree", None)
        payload_meta.pop("_revision_history", None)
        payload["global_meta"] = payload_meta
        return payload

    def to_serialized_json(self) -> str:
        return json.dumps(self.to_serialized_dict(), ensure_ascii=False, indent=2)

    def refresh_from_serialized(self, payload: dict[str, Any] | str) -> None:
        incoming = self._coerce_payload(payload)
        refreshed = BehaviorTree.model_validate(incoming)
        self.format_version = refreshed.format_version
        self.revision = refreshed.revision
        self.updated_at = refreshed.updated_at
        self.root_node_id = refreshed.root_node_id
        preserved_serialized = self.global_meta.get("serialized_tree")
        preserved_history = self.global_meta.get("_revision_history")
        self.global_meta = dict(refreshed.global_meta)
        if preserved_serialized is not None and "serialized_tree" not in self.global_meta:
            self.global_meta["serialized_tree"] = preserved_serialized
        if preserved_history is not None and "_revision_history" not in self.global_meta:
            self.global_meta["_revision_history"] = preserved_history
        self.global_claims = list(refreshed.global_claims)
        self.bindings = refreshed.bindings
        self.python_refs = dict(refreshed.python_refs)
        for node_id, refreshed_node in refreshed.nodes.items():
            if node_id in self.nodes:
                self.nodes[node_id].refresh_from_serialized(
                    refreshed_node.to_serialized_dict(),
                    lock_element_id=self.nodes[node_id].current_element_id if self.nodes[node_id].execution_lock else None,
                )
            else:
                self.nodes[node_id] = refreshed_node
        stale = [node_id for node_id in self.nodes if node_id not in refreshed.nodes]
        for node_id in stale:
            if self.nodes[node_id].execution_lock:
                continue
            del self.nodes[node_id]

    @staticmethod
    def _coerce_payload(payload: dict[str, Any] | str) -> dict[str, Any]:
        if isinstance(payload, str):
            return json.loads(payload)
        return payload


class NodeRunRecord(BaseModel):
    node_id: str
    executed_elements: list[str] = Field(default_factory=list)
    outcome: str = "done"
    return_value: Any = None


class ClaimEvaluation(BaseModel):
    status: ClaimLifecycle
    details: str = ""


def utc_http_now() -> str:
    return datetime.now(timezone.utc).strftime("%a, %d %b %Y %H:%M:%S GMT")


class LLMBackend:
    """Registry of LLM clients keyed by agent name."""

    def __init__(self) -> None:
        self._clients: dict[str, Any] = {}  # agent_name -> KoboldClient

    def register(self, agent_name: str, client: Any) -> None:
        self._clients[agent_name] = client

    def get(self, agent_name: str) -> Any:
        return self._clients.get(agent_name)

    def call(
        self,
        agent_name: str,
        prompt: str,
        system_prompt: str | None = None,
        *,
        temperature: float = 0.6,
        max_tokens: int = 2048,
        no_think: bool = True,
        max_continue: int = 20,
    ) -> str:
        client = self._clients.get(agent_name)
        if client is None:
            raise ValueError(f"No LLM client registered for agent '{agent_name}'")

        import httpx
        import re as _re

        # Build messages — same approach as multi_agent_chat.html
        messages: list[dict] = []
        if system_prompt:
            messages.append({"role": "system", "content": system_prompt})
        messages.append({"role": "user", "content": prompt})

        # No-think: add assistant prefill + continue_assistant_turn
        # This is the correct way — prefill as assistant message, not appended to user
        if no_think:
            messages.append({"role": "assistant", "content": "<think>\n\n</think>\n\n"})

        payload: dict = {
            "messages": messages,
            "temperature": temperature,
            "max_tokens": max_tokens,
            "stream": False,
        }
        if no_think:
            payload["continue_assistant_turn"] = True

        base_url = client.base_url.rstrip("/")
        http = httpx.Client(timeout=client.timeout, trust_env=False)

        try:
            resp = http.post(f"{base_url}/v1/chat/completions", json=payload)
            resp.raise_for_status()
            raw = resp.json()

            chunk = raw.get("choices", [{}])[0].get("message", {}).get("content", "")
            finish = raw.get("choices", [{}])[0].get("finish_reason", "stop")

            # With no_think + continue_assistant_turn, KoboldCpp returns ONLY new tokens
            # (not the prefill), so chunk IS the result directly
            raw_result = chunk

            # For continue: full_assistant = prefill + all chunks so far
            if no_think:
                full_assistant = "<think>\n\n</think>\n\n" + raw_result
            else:
                full_assistant = raw_result

            # Continue loop until EoT (finish_reason != "length") or max_continue.
            # Even if </think> appeared, keep going — model hasn't sent EoT yet,
            # answer text is still being generated.
            for i in range(max_continue):
                if str(finish).strip().lower() not in {"length", "max_tokens"}:
                    break

                # Send same base messages + full assistant content for KV cache match
                cont_messages = list(messages[:-1]) if no_think else list(messages)
                cont_messages.append({"role": "assistant", "content": full_assistant})

                continue_payload = {
                    "messages": cont_messages,
                    "continue_assistant_turn": True,
                    "cache_prompt": False,
                    "temperature": temperature,
                    "max_tokens": max_tokens,
                    "stream": False,
                }
                try:
                    resp = http.post(f"{base_url}/v1/chat/completions", json=continue_payload)
                    resp.raise_for_status()
                except (httpx.RemoteProtocolError, httpx.ConnectError, httpx.ReadError) as exc:
                    # Connection reset — retry once with fresh client
                    http.close()
                    http = httpx.Client(timeout=client.timeout, trust_env=False)
                    try:
                        resp = http.post(f"{base_url}/v1/chat/completions", json=continue_payload)
                        resp.raise_for_status()
                    except Exception:
                        break  # Give up, return partial result
                except httpx.HTTPStatusError:
                    break  # Server error, return partial result
                cont_raw = resp.json()
                new_chunk = cont_raw.get("choices", [{}])[0].get("message", {}).get("content", "")
                raw_result += new_chunk
                full_assistant += new_chunk
                finish = cont_raw.get("choices", [{}])[0].get("finish_reason", "stop")

            # Strip think blocks from final result
            result = _re.sub(r"<think\b[^>]*>.*?</think>\s*", "", raw_result, flags=_re.DOTALL | _re.IGNORECASE).strip()
            if "<think>" in result:
                # Unclosed think — take everything after </think> if present, or discard think
                if "</think>" in raw_result:
                    result = raw_result[raw_result.rindex("</think>") + len("</think>"):].strip()
                else:
                    result = _re.sub(r"<think>[\s\S]*", "", result).strip()
        finally:
            http.close()

        return result


class BehaviorOrchestrator:
    def __init__(self, llm: LLMBackend | None = None) -> None:
        self._handlers: dict[str, Any] = {}
        self._claim_evaluators: dict[str, Any] = {}
        self.llm = llm or LLMBackend()

    def register_handler(self, name: str, fn: Any) -> None:
        self._handlers[name] = fn

    def register_claim_evaluator(self, name: str, fn: Any) -> None:
        self._claim_evaluators[name] = fn

    def evaluate_claims(self, tree: BehaviorTree, node_id: str | None = None) -> None:
        if node_id is not None:
            node = tree.node(node_id)
            for claim in node.claims:
                self._apply_claim(tree, claim)
        for claim in tree.global_claims:
            self._apply_claim(tree, claim)

    def run_node(self, tree: BehaviorTree, node_id: str) -> NodeRunRecord:
        node = tree.node(node_id)
        record = NodeRunRecord(node_id=node_id)
        current_id = node.entry_element

        while current_id:
            result: ElementExecutionResult | None = None
            element: BehaviorElement | None = None
            next_id: str | None = None
            self.refresh_node_from_meta(tree, node.node_id, lock_element_id=current_id)
            try:
                element = node.element(current_id)
                node.current_element_id = current_id
                node.execution_lock = True
                record.executed_elements.append(element.element_id)
                node.meta["last_executed_elements"] = list(record.executed_elements)
                result = self._handlers[element.handler](tree, node, element, self)
                if not isinstance(result, ElementExecutionResult):
                    result = ElementExecutionResult.model_validate(result)
                if result.updated_paths:
                    node.meta["last_updated_paths"] = list(result.updated_paths)
                    self.evaluate_claims(tree, node_id=node.node_id)
                node.meta["last_transition"] = {"from": element.element_id, "outcome": result.outcome}
                self.persist_node_to_meta(tree, node.node_id)
                next_id = element.transitions.get(result.outcome)
                if next_id is None:
                    next_id = self._default_next(node, element.element_id)
            except Exception as exc:
                node.meta["last_error"] = str(exc)
                self.persist_node_to_meta(tree, node.node_id)
                raise
            finally:
                node.execution_lock = False
                node.current_element_id = None
                self.persist_node_to_meta(tree, node.node_id)
                self.refresh_node_from_meta(tree, node.node_id)
            current_id = next_id
            record.outcome = result.outcome
            if result.value is not None:
                record.return_value = result.value

        if record.return_value is None and node.return_key:
            record.return_value = node.data.get(node.return_key)
        self.persist_node_to_meta(tree, node.node_id)
        self.persist_tree_to_meta(tree)
        return record

    def run_tree(self, tree: BehaviorTree) -> Any:
        return self.run_node(tree, tree.root_node_id).return_value

    def assemble_instruction(self, bundle: InstructionBundle) -> str:
        return bundle.render()

    def export_tree_json(self, tree: BehaviorTree) -> str:
        return tree.to_serialized_json()

    def export_node_json(self, tree: BehaviorTree, node_id: str) -> str:
        return tree.node(node_id).to_serialized_json()

    def update_tree_from_json(self, tree: BehaviorTree, payload: dict[str, Any] | str) -> None:
        tree.refresh_from_serialized(payload)

    def update_node_from_json(self, tree: BehaviorTree, node_id: str, payload: dict[str, Any] | str) -> None:
        tree.node(node_id).refresh_from_serialized(payload)

    def refresh_node_from_meta(self, tree: BehaviorTree, node_id: str, lock_element_id: str | None = None) -> None:
        node = tree.node(node_id)
        serialized = node.meta.get("serialized_node")
        if serialized:
            node.refresh_from_serialized(serialized, lock_element_id=lock_element_id)

    def persist_node_to_meta(self, tree: BehaviorTree, node_id: str) -> None:
        node = tree.node(node_id)
        node.revision += 1
        node.updated_at = utc_http_now()
        node.meta["serialized_node"] = node.to_serialized_dict()
        history = dict(node.meta.get("_revision_history", {}))
        history[str(node.revision)] = node.to_serialized_dict()
        if len(history) > 20:
            for key in sorted(history.keys(), key=int)[:-20]:
                history.pop(key, None)
        node.meta["_revision_history"] = history
        # Bump tree revision so polling detects changes mid-run
        tree.revision += 1
        tree.updated_at = node.updated_at

    def persist_tree_to_meta(self, tree: BehaviorTree) -> None:
        tree.revision += 1
        tree.updated_at = utc_http_now()
        tree.global_meta["serialized_tree"] = tree.to_serialized_dict()
        history = dict(tree.global_meta.get("_revision_history", {}))
        history[str(tree.revision)] = tree.to_serialized_dict()
        if len(history) > 20:
            for key in sorted(history.keys(), key=int)[:-20]:
                history.pop(key, None)
        tree.global_meta["_revision_history"] = history

    def _apply_claim(self, tree: BehaviorTree, claim: BehaviorClaim) -> None:
        evaluation = self._claim_evaluators[claim.evaluator](tree, claim, self)
        if not isinstance(evaluation, ClaimEvaluation):
            evaluation = ClaimEvaluation.model_validate(evaluation)
        claim.status = evaluation.status
        claim.details = evaluation.details

    @staticmethod
    def _default_next(node: BehaviorNode, element_id: str) -> str | None:
        ids = [item.element_id for item in node.elements]
        index = ids.index(element_id)
        if index + 1 >= len(ids):
            return None
        return ids[index + 1]


def reference_behavior_tree_template_path() -> Path:
    return Path(__file__).resolve().parents[2] / "examples" / "behavior_case" / "character_description_reference_tree.json"


def load_reference_behavior_tree_template(path: str | Path | None = None) -> dict[str, Any]:
    target = Path(path) if path is not None else reference_behavior_tree_template_path()
    return json.loads(target.read_text(encoding="utf-8"))


def build_reference_agent_bindings() -> AgentBindingRegistry:
    payload = load_reference_behavior_tree_template()
    return AgentBindingRegistry.model_validate(payload["bindings"])


def create_reference_behavior_orchestrator(
    *,
    worker_url: str | None = None,
    planner_url: str | None = None,
) -> BehaviorOrchestrator:
    llm = LLMBackend()
    if worker_url:
        from .kobold_client import KoboldClient

        llm.register("small_context_worker", KoboldClient(worker_url, timeout=180.0))
    if planner_url:
        from .kobold_client import KoboldClient

        llm.register("qwen_27b_planner", KoboldClient(planner_url, timeout=180.0))

    orchestrator = BehaviorOrchestrator(llm=llm)
    from .dsl_interpreter import handle_dsl
    orchestrator.register_handler("__dsl__", handle_dsl)
    orchestrator.register_handler("root_plan", _handle_root_plan)
    orchestrator.register_handler("run_children", _handle_run_children)
    orchestrator.register_handler("global_check", _handle_global_check)
    orchestrator.register_handler("repair_global_conflicts", _handle_repair_global_conflicts)
    orchestrator.register_handler("collect_outputs", _handle_collect_outputs)
    orchestrator.register_handler("llm_generate", _handle_llm_generate)
    orchestrator.register_handler("evaluate_claims", _handle_evaluate_claims)
    orchestrator.register_handler("llm_repair", _handle_llm_repair)
    orchestrator.register_handler("truncate_sentences", _handle_truncate_sentences)
    orchestrator.register_handler("finalize_from_claims", _handle_finalize_from_claims)
    orchestrator.register_handler("generate_description", _handle_generate_description)
    orchestrator.register_handler("local_check", _handle_local_check)
    orchestrator.register_handler("repair_local", _handle_repair_local)
    orchestrator.register_handler("compress_description", _handle_compress_description)
    orchestrator.register_handler("audit_description", _handle_audit_description)
    orchestrator.register_claim_evaluator("text_sentence_range", _eval_text_sentence_range)
    orchestrator.register_claim_evaluator("text_has_expected_value", _eval_text_has_expected_value)
    orchestrator.register_claim_evaluator("unique_child_field", _eval_unique_child_field)
    orchestrator.register_claim_evaluator("sentence_range", _eval_sentence_range)
    orchestrator.register_claim_evaluator("hair_color_present", _eval_hair_color_present)
    orchestrator.register_claim_evaluator("style_present", _eval_style_present)
    orchestrator.register_claim_evaluator("unique_hair_colors", _eval_unique_hair_colors)
    orchestrator.register_claim_evaluator("unique_styles", _eval_unique_styles)
    return orchestrator


# plan_and_build_tree removed — use nl_to_dsl.plan_and_build instead


def plan_and_build_tree(
    task_prompt: str,
    orchestrator: "BehaviorOrchestrator",
    *,
    tree_id: str = "auto",
) -> "BehaviorTree":
    """Delegate to nl_to_dsl.plan_and_build for DSL-based tree generation."""
    from .nl_to_dsl import plan_and_build

    tree_dict = plan_and_build(
        orchestrator.llm,
        task_prompt,
        agent_name="qwen_27b_planner",
    )
    return BehaviorTree.from_serialized_dict(tree_dict)


def _handle_generate_from_prompt(
    _tree: BehaviorTree, node: BehaviorNode, _element: BehaviorElement, orchestrator: BehaviorOrchestrator,
) -> ElementExecutionResult:
    prompt = str(node.data.get("prompt", ""))
    style = str(node.data.get("style", ""))
    key_detail = str(node.data.get("key_detail", ""))
    sr = node.data.get("sentence_range", [5, 10])

    # Read settings from tree global_meta (set by UI)
    tree_sr = _tree.global_meta.get("sentence_range", sr)
    lang = _tree.global_meta.get("language", "ru")
    lang_instruction = "Отвечай на русском." if lang == "ru" else f"Reply in {lang}."

    full_prompt = prompt
    if style:
        full_prompt += f"\nСтиль: {style}."
    if key_detail:
        full_prompt += f"\nОбязательно упомяни: {key_detail}."
    full_prompt += f"\nИспользуй {tree_sr[0]}-{tree_sr[1]} предложений."
    full_prompt += f"\n{lang_instruction} Начинай сразу с текста, без заголовков и предисловий."

    agent_name = _tree.global_meta.get("creative_agent", "small_context_worker")
    gen_temp = _tree.global_meta.get("temperature", 0.6)
    gen_max = _tree.global_meta.get("max_tokens", 2048)
    if orchestrator.llm.get(agent_name):
        try:
            text = orchestrator.llm.call(agent_name, full_prompt, temperature=gen_temp, max_tokens=gen_max)
            node.data["draft_text"] = _strip_think(text).strip()
            node.data["llm_generated"] = True
            node.data["generated_by"] = agent_name
            return ElementExecutionResult(updated_paths=("draft_text",), outcome="pass")
        except Exception as exc:
            node.data["llm_error"] = str(exc)

    # Fallback
    node.data["draft_text"] = f"[Шаблон] {prompt}"
    return ElementExecutionResult(updated_paths=("draft_text",), outcome="pass")


def _handle_repair_from_prompt(
    tree: BehaviorTree, node: BehaviorNode, _element: BehaviorElement, orchestrator: BehaviorOrchestrator,
) -> ElementExecutionResult:
    node.data["repair_count"] = node.data.get("repair_count", 0) + 1
    failures = node.data.get("local_failures", [])
    old_text = str(node.data.get("draft_text", ""))
    prompt = node.data.get("prompt", "")
    key_detail = node.data.get("key_detail", "")

    repair_prompt = (
        f"Предыдущий текст не прошёл проверку.\n"
        f"Проблемы: {', '.join(failures)}.\n"
        f"Задание: {prompt}\n"
    )
    if key_detail:
        repair_prompt += f"Обязательно упомяни: {key_detail}.\n"
    repair_prompt += f"Перепиши, исправив проблемы. Начинай сразу с текста, без предисловий и заголовков. Отвечай на русском.\n\nСтарый текст:\n{old_text}"

    agent_name = tree.global_meta.get("creative_agent", "small_context_worker")
    if orchestrator.llm.get(agent_name):
        try:
            text = orchestrator.llm.call(agent_name, repair_prompt)
            node.data["draft_text"] = _strip_think(text).strip()
            node.data["generated_by"] = agent_name
            orchestrator.evaluate_claims(tree, node_id=node.node_id)
            return ElementExecutionResult(updated_paths=("draft_text", "repair_count"), outcome="pass")
        except Exception:
            pass

    node.data["draft_text"] = f"[Repaired] {prompt}"
    orchestrator.evaluate_claims(tree, node_id=node.node_id)
    return ElementExecutionResult(updated_paths=("draft_text", "repair_count"), outcome="pass")


def _eval_key_detail_present(
    tree: BehaviorTree, claim: BehaviorClaim, _orchestrator: BehaviorOrchestrator,
) -> ClaimEvaluation:
    node = tree.node(claim.owner_node_id or "")
    text = str(node.data.get("final_text") or node.data.get("draft_text") or "").lower()
    key_detail = str(claim.meta.get("key_detail", node.data.get("key_detail", ""))).lower()
    if not key_detail:
        return ClaimEvaluation(status=ClaimLifecycle.PASS, details="no key detail required")
    # Fuzzy: check if any word from key_detail appears
    words = [w for w in key_detail.split() if len(w) > 2]
    if not text:
        return ClaimEvaluation(status=ClaimLifecycle.PENDING, details="no text yet")
    matches = sum(1 for w in words if w in text)
    if matches >= len(words):
        return ClaimEvaluation(status=ClaimLifecycle.PASS, details=f"key detail '{key_detail}' present")
    if matches > 0:
        return ClaimEvaluation(status=ClaimLifecycle.PASS, details=f"partial match ({matches}/{len(words)} words)")
    return ClaimEvaluation(status=ClaimLifecycle.FAIL, details=f"key detail '{key_detail}' missing")


def initialize_behavior_tree_runtime_state(tree: BehaviorTree) -> BehaviorTree:
    for node in tree.nodes.values():
        node.updated_at = utc_http_now()
        node.meta["serialized_node"] = node.to_serialized_dict()
        node.meta["_revision_history"] = {str(node.revision): node.to_serialized_dict()}
    tree.updated_at = utc_http_now()
    tree.global_meta["serialized_tree"] = tree.to_serialized_dict()
    tree.global_meta["_revision_history"] = {str(tree.revision): tree.to_serialized_dict()}
    return tree


def build_character_description_reference_tree(path: str | Path | None = None) -> BehaviorTree:
    payload = load_reference_behavior_tree_template(path)
    tree = BehaviorTree.model_validate(payload)
    return initialize_behavior_tree_runtime_state(tree)


def _handle_root_plan(tree: BehaviorTree, node: BehaviorNode, _element: BehaviorElement, orchestrator: BehaviorOrchestrator) -> ElementExecutionResult:
    bundle = InstructionBundle.model_validate(node.meta["instruction_bundles"][0])
    node.meta["assembled_instruction"] = orchestrator.assemble_instruction(bundle)
    node.data["planned"] = True
    return ElementExecutionResult(updated_paths=("planned",), outcome="pass")


def _handle_run_children(tree: BehaviorTree, node: BehaviorNode, _element: BehaviorElement, orchestrator: BehaviorOrchestrator) -> ElementExecutionResult:
    outputs: list[str] = []
    run_records: dict[str, Any] = {}
    for child_id in node.data["child_ids"]:
        record = orchestrator.run_node(tree, child_id)
        outputs.append(record.return_value)
        run_records[child_id] = record.model_dump()
    node.data["child_runs"] = run_records
    node.data["outputs"] = outputs
    return ElementExecutionResult(updated_paths=("child_runs", "outputs"), outcome="pass")


def _handle_global_check(tree: BehaviorTree, node: BehaviorNode, _element: BehaviorElement, orchestrator: BehaviorOrchestrator) -> ElementExecutionResult:
    orchestrator.evaluate_claims(tree)
    failed = [claim.claim_id for claim in tree.global_claims if claim.status != ClaimLifecycle.PASS]
    node.data["global_failures"] = failed
    return ElementExecutionResult(updated_paths=("global_failures",), outcome="fail" if failed else "pass")


def _handle_repair_global_conflicts(tree: BehaviorTree, node: BehaviorNode, _element: BehaviorElement, orchestrator: BehaviorOrchestrator) -> ElementExecutionResult:
    seen_colors: set[str] = set()
    fallback_colors = list(tree.global_meta.get("fallback_hair_colors", []))
    for child_id in node.data["child_ids"]:
        child = tree.node(child_id)
        color = child.data["hair_color"]
        if color not in seen_colors:
            seen_colors.add(color)
            continue
        for candidate in fallback_colors:
            if candidate not in seen_colors:
                child.data["hair_color"] = candidate
                child.data["repair_count"] += 1
                child.data["draft_text"] = _render_description(
                    index=child.data["index"],
                    style=child.data["style"],
                    hair_color=candidate,
                    sentence_count=6,
                )
                child.data["final_text"] = child.data["draft_text"]
                orchestrator.evaluate_claims(tree, node_id=child_id)
                seen_colors.add(candidate)
                break
    node.data["outputs"] = [tree.node(child_id).data["final_text"] for child_id in node.data["child_ids"]]
    orchestrator.evaluate_claims(tree)
    return ElementExecutionResult(updated_paths=("outputs",), outcome="pass")


def _handle_collect_outputs(tree: BehaviorTree, node: BehaviorNode, _element: BehaviorElement, _orchestrator: BehaviorOrchestrator) -> ElementExecutionResult:
    outputs = [tree.node(child_id).data["final_text"] for child_id in node.data["child_ids"]]
    node.data["outputs"] = outputs
    return ElementExecutionResult(updated_paths=("outputs",), outcome="done", value=outputs)


def _handle_llm_generate(
    tree: BehaviorTree, node: BehaviorNode, element: BehaviorElement, orchestrator: BehaviorOrchestrator,
) -> ElementExecutionResult:
    output_field = str(element.meta.get("output_field", "draft_text"))
    fallback_mode = str(element.meta.get("fallback_mode", "description_template"))
    bundle = _get_bundle(node, bundle_id=element.meta.get("bundle_id"))
    prompt = _render_bundle_prompt(tree, node, bundle, extra_context=element.meta.get("template_context"))
    prompt_template = element.meta.get("prompt_template")
    if prompt_template:
        prompt = _expand_template(str(prompt_template), tree, node, extra=_coerce_extra_context(element.meta.get("template_context")))
    system = bundle.get("system")
    system_template = element.meta.get("system_template")
    if system_template:
        system = _expand_template(str(system_template), tree, node, extra=_coerce_extra_context(element.meta.get("template_context")))

    target_agent = (
        element.meta.get("agent_name")
        or bundle.get("target_agent")
        or tree.global_meta.get("creative_agent", "small_context_worker")
    )
    temperature = float(element.meta.get("temperature", tree.global_meta.get("temperature", 0.6)))
    max_tokens = int(element.meta.get("max_tokens", tree.global_meta.get("max_tokens", 2048)))
    if orchestrator.llm.get(str(target_agent)):
        try:
            text = orchestrator.llm.call(str(target_agent), prompt, system_prompt=system, temperature=temperature, max_tokens=max_tokens)
            node.data[output_field] = _strip_think(text).strip()
            node.data["llm_generated"] = True
            node.data["generated_by"] = target_agent
            return ElementExecutionResult(updated_paths=(output_field,), outcome="pass")
        except Exception as exc:
            node.data["llm_error"] = str(exc)

    if fallback_mode == "prompt_stub":
        fallback_text = str(node.data.get("prompt", prompt)).strip()
    else:
        sentence_count = int(node.data.get("fallback_sentence_count", element.meta.get("fallback_sentence_count", 6)))
        fallback_hair_color = str(node.data.get("fallback_hair_color", node.data.get("hair_color", "")))
        fallback_text = _render_description(
            index=int(node.data.get("index", 0)),
            style=str(node.data.get("style", "")),
            hair_color=fallback_hair_color,
            sentence_count=sentence_count,
        )
    node.data[output_field] = fallback_text
    return ElementExecutionResult(updated_paths=(output_field,), outcome="pass")


def _handle_evaluate_claims(
    tree: BehaviorTree, node: BehaviorNode, element: BehaviorElement, orchestrator: BehaviorOrchestrator,
) -> ElementExecutionResult:
    scope = str(element.meta.get("scope", "node"))
    failure_field = str(element.meta.get("failure_field", "failures"))
    if scope == "tree":
        orchestrator.evaluate_claims(tree)
        claims = tree.global_claims
    else:
        orchestrator.evaluate_claims(tree, node_id=node.node_id)
        claims = node.claims
    failures = [claim.claim_id for claim in claims if claim.status != ClaimLifecycle.PASS]
    node.data[failure_field] = failures
    return ElementExecutionResult(updated_paths=(failure_field,), outcome="fail" if failures else "pass")


def _handle_llm_repair(
    tree: BehaviorTree, node: BehaviorNode, element: BehaviorElement, orchestrator: BehaviorOrchestrator,
) -> ElementExecutionResult:
    target_field = str(element.meta.get("target_field", "draft_text"))
    counter_field = str(element.meta.get("counter_field", "repair_count"))
    failure_field = str(element.meta.get("failure_field", "local_failures"))
    node.data[counter_field] = int(node.data.get(counter_field, 0)) + 1
    failures = node.data.get(failure_field, [])
    old_text = str(node.data.get(target_field, ""))
    bundle = _get_bundle(node, bundle_id=element.meta.get("bundle_id"))
    target_agent = (
        element.meta.get("agent_name")
        or bundle.get("target_agent")
        or tree.global_meta.get("creative_agent", "small_context_worker")
    )
    extra = _coerce_extra_context(element.meta.get("template_context"))
    extra.update({
        "old_text": old_text,
        "failures": failures,
        "failures_text": ", ".join(str(item) for item in failures),
        "target_field": target_field,
    })
    prompt = _build_repair_prompt(tree, node, failures, old_text, bundle, prompt_template=element.meta.get("prompt_template"), extra=extra)
    system_prompt = bundle.get("system")
    system_template = element.meta.get("system_template")
    if system_template:
        system_prompt = _expand_template(str(system_template), tree, node, extra=extra)
    if orchestrator.llm.get(str(target_agent)):
        try:
            text = orchestrator.llm.call(str(target_agent), prompt, system_prompt=system_prompt)
            node.data[target_field] = _strip_think(text).strip()
            node.data["generated_by"] = target_agent
            orchestrator.evaluate_claims(tree, node_id=node.node_id)
            return ElementExecutionResult(updated_paths=(target_field, counter_field), outcome="pass")
        except Exception as exc:
            node.data["llm_error"] = str(exc)
    node.data[target_field] = _render_description(
        index=int(node.data.get("index", 0)),
        style=str(node.data.get("style", "")),
        hair_color=str(node.data.get("hair_color", "")),
        sentence_count=int(element.meta.get("fallback_sentence_count", 6)),
    )
    orchestrator.evaluate_claims(tree, node_id=node.node_id)
    return ElementExecutionResult(updated_paths=(target_field, counter_field), outcome="pass")


def _handle_truncate_sentences(
    tree: BehaviorTree, node: BehaviorNode, element: BehaviorElement, orchestrator: BehaviorOrchestrator,
) -> ElementExecutionResult:
    source_field = str(element.meta.get("source_field", "draft_text"))
    target_field = str(element.meta.get("target_field", "final_text"))
    range_field = str(element.meta.get("range_field", "sentence_range"))
    text = str(node.data.get(source_field, "")).strip()
    sr = node.data.get(range_field) or tree.global_meta.get(range_field) or [5, 10]
    max_sent = int(sr[1])
    sentences = _sentence_split(text)
    if len(sentences) > max_sent:
        sentences = sentences[:max_sent]
    node.data[target_field] = " ".join(f"{sentence}." for sentence in sentences)
    orchestrator.evaluate_claims(tree, node_id=node.node_id)
    return ElementExecutionResult(updated_paths=(target_field,), outcome="pass")


def _handle_finalize_from_claims(
    tree: BehaviorTree, node: BehaviorNode, element: BehaviorElement, orchestrator: BehaviorOrchestrator,
) -> ElementExecutionResult:
    orchestrator.evaluate_claims(tree, node_id=node.node_id)
    status_field = str(element.meta.get("status_field", "audit_status"))
    success_value = element.meta.get("success_value", "pass")
    fail_value = element.meta.get("fail_value", "fail")
    return_field = str(element.meta.get("return_field", node.return_key or ""))
    terminal_outcome = str(element.meta.get("outcome", "done"))
    node.data[status_field] = success_value if all(claim.status == ClaimLifecycle.PASS for claim in node.claims) else fail_value
    return ElementExecutionResult(updated_paths=(status_field,), outcome=terminal_outcome, value=node.data.get(return_field))


def _handle_generate_description(_tree: BehaviorTree, node: BehaviorNode, _element: BehaviorElement, orchestrator: BehaviorOrchestrator) -> ElementExecutionResult:
    index = int(node.data["index"])
    style = str(node.data["style"])
    hair_color = str(node.data["hair_color"])

    # Try LLM first, fallback to template
    agent_name = _tree.global_meta.get("creative_agent", "small_context_worker")
    gen_temp = _tree.global_meta.get("temperature", 0.6)
    gen_max = _tree.global_meta.get("max_tokens", 2048)
    tree_sr = _tree.global_meta.get("sentence_range", [5, 10])
    lang = _tree.global_meta.get("language", "ru")
    lang_instruction = "Отвечай на русском." if lang == "ru" else f"Reply in {lang}."
    if orchestrator.llm.get(agent_name):
        bundle = _get_bundle(node)
        system = bundle.get("system", "Опиши внешность персонажа.")
        prompt = (
            f"Напиши описание внешности персонажа #{index + 1}.\n"
            f"Стиль: {style}.\n"
            f"Обязательно упомяни цвет волос: {hair_color}.\n"
            f"Используй {tree_sr[0]}-{tree_sr[1]} предложений. Только описание внешности, без истории.\n"
            f"{lang_instruction}"
        )
        try:
            text = orchestrator.llm.call(agent_name, prompt, system_prompt=system, temperature=gen_temp, max_tokens=gen_max)
            node.data["draft_text"] = _strip_think(text).strip()
            node.data["llm_generated"] = True
            node.data["generated_by"] = agent_name
            return ElementExecutionResult(updated_paths=("draft_text",), outcome="pass")
        except Exception as exc:
            node.data["llm_error"] = str(exc)

    # Fallback: template
    sentence_count = 6
    if index == 0:
        sentence_count = 4
        hair_color = ""
    elif index == 1:
        hair_color = "black"
    node.data["draft_text"] = _render_description(
        index=index, style=style, hair_color=hair_color, sentence_count=sentence_count,
    )
    return ElementExecutionResult(updated_paths=("draft_text",), outcome="pass")


def _handle_local_check(tree: BehaviorTree, node: BehaviorNode, _element: BehaviorElement, orchestrator: BehaviorOrchestrator) -> ElementExecutionResult:
    orchestrator.evaluate_claims(tree, node_id=node.node_id)
    failures = [claim.claim_id for claim in node.claims if claim.status != ClaimLifecycle.PASS]
    node.data["local_failures"] = failures
    return ElementExecutionResult(updated_paths=("local_failures",), outcome="fail" if failures else "pass")


def _handle_repair_local(tree: BehaviorTree, node: BehaviorNode, _element: BehaviorElement, orchestrator: BehaviorOrchestrator) -> ElementExecutionResult:
    node.data["repair_count"] += 1
    failures = node.data.get("local_failures", [])
    style = str(node.data["style"])
    hair_color = str(node.data["hair_color"])

    agent_name = tree.global_meta.get("creative_agent", "small_context_worker")
    if orchestrator.llm.get(agent_name):
        old_text = str(node.data.get("draft_text", ""))
        prompt = (
            f"Предыдущее описание не прошло проверку.\n"
            f"Проблемы: {', '.join(failures)}.\n"
            f"Стиль: {style}. Цвет волос: {hair_color}.\n"
            f"Перепиши описание, исправив проблемы. 5-10 предложений. Только внешность.\n"
            f"Отвечай на русском.\n\n"
            f"Старое описание:\n{old_text}"
        )
        try:
            text = orchestrator.llm.call(agent_name, prompt)
            node.data["draft_text"] = _strip_think(text).strip()
            orchestrator.evaluate_claims(tree, node_id=node.node_id)
            return ElementExecutionResult(updated_paths=("draft_text", "repair_count"), outcome="pass")
        except Exception:
            pass

    # Fallback
    node.data["draft_text"] = _render_description(
        index=int(node.data["index"]), style=style, hair_color=hair_color, sentence_count=6,
    )
    orchestrator.evaluate_claims(tree, node_id=node.node_id)
    return ElementExecutionResult(updated_paths=("draft_text", "repair_count"), outcome="pass")


def _handle_compress_description(tree: BehaviorTree, node: BehaviorNode, _element: BehaviorElement, orchestrator: BehaviorOrchestrator) -> ElementExecutionResult:
    text = str(node.data["draft_text"]).strip()
    sr = node.data.get("sentence_range") or tree.global_meta.get("sentence_range") or [5, 10]
    max_sent = int(sr[1])
    sentences = _sentence_split(text)
    if len(sentences) > max_sent:
        sentences = sentences[:max_sent]
    node.data["final_text"] = " ".join(f"{sentence}." for sentence in sentences)
    orchestrator.evaluate_claims(tree, node_id=node.node_id)
    return ElementExecutionResult(updated_paths=("final_text",), outcome="pass")


def _handle_audit_description(tree: BehaviorTree, node: BehaviorNode, _element: BehaviorElement, orchestrator: BehaviorOrchestrator) -> ElementExecutionResult:
    orchestrator.evaluate_claims(tree, node_id=node.node_id)
    node.data["audit_status"] = "pass" if all(claim.status == ClaimLifecycle.PASS for claim in node.claims) else "fail"
    return ElementExecutionResult(updated_paths=("audit_status",), outcome="done", value=node.data.get("final_text", ""))


def _eval_text_sentence_range(tree: BehaviorTree, claim: BehaviorClaim, _orchestrator: BehaviorOrchestrator) -> ClaimEvaluation:
    node = tree.node(claim.owner_node_id or "")
    text_fields = tuple(claim.meta.get("text_fields", ("final_text", "draft_text")))
    text = str(_first_value(node.data, text_fields) or "").strip()
    count = len(_sentence_split(text))
    range_field = str(claim.meta.get("range_field", "sentence_range"))
    sr = node.data.get(range_field) or tree.global_meta.get(range_field) or [5, 10]
    lo, hi = int(sr[0]), int(sr[1])
    if lo <= count <= hi:
        return ClaimEvaluation(status=ClaimLifecycle.PASS, details=f"{count} sentences (target {lo}-{hi})")
    if not text:
        return ClaimEvaluation(status=ClaimLifecycle.PENDING, details="no text yet")
    return ClaimEvaluation(status=ClaimLifecycle.FAIL, details=f"{count} sentences (target {lo}-{hi})")


def _eval_text_has_expected_value(tree: BehaviorTree, claim: BehaviorClaim, _orchestrator: BehaviorOrchestrator) -> ClaimEvaluation:
    node = tree.node(claim.owner_node_id or "")
    text_fields = tuple(claim.meta.get("text_fields", ("final_text", "draft_text")))
    text = str(_first_value(node.data, text_fields) or "").lower()
    expected_field = str(claim.meta.get("expected_field", ""))
    label = str(claim.meta.get("label", expected_field or "value"))
    expected_value = str(claim.meta.get("expected_value", node.data.get(expected_field, ""))).lower()
    if expected_value and expected_value in text:
        return ClaimEvaluation(status=ClaimLifecycle.PASS, details=f"{label} {expected_value} present")
    if not text:
        return ClaimEvaluation(status=ClaimLifecycle.PENDING, details="no text yet")
    return ClaimEvaluation(status=ClaimLifecycle.FAIL, details=f"{label} {expected_value or '-'} missing")


def _eval_unique_child_field(tree: BehaviorTree, claim: BehaviorClaim, _orchestrator: BehaviorOrchestrator) -> ClaimEvaluation:
    root_node_id = str(claim.meta.get("root_node_id", tree.root_node_id))
    child_ids_field = str(claim.meta.get("child_ids_field", "child_ids"))
    child_field = str(claim.meta.get("child_field", ""))
    label = str(claim.meta.get("label", child_field or "values"))
    child_ids = tree.node(root_node_id).data.get(child_ids_field, [])
    values = [str(tree.node(node_id).data.get(child_field, "")).strip() for node_id in child_ids]
    if any(not value for value in values):
        return ClaimEvaluation(status=ClaimLifecycle.PENDING, details=f"missing {label}")
    duplicates = [value for value, count in Counter(values).items() if count > 1]
    if duplicates:
        return ClaimEvaluation(status=ClaimLifecycle.FAIL, details=f"duplicate {label}: {', '.join(sorted(duplicates))}")
    return ClaimEvaluation(status=ClaimLifecycle.PASS, details=f"all {label} unique")


def _eval_sentence_range(tree: BehaviorTree, claim: BehaviorClaim, _orchestrator: BehaviorOrchestrator) -> ClaimEvaluation:
    claim.meta.setdefault("range_field", "sentence_range")
    claim.meta.setdefault("text_fields", ("final_text", "draft_text"))
    return _eval_text_sentence_range(tree, claim, _orchestrator)


def _eval_hair_color_present(tree: BehaviorTree, claim: BehaviorClaim, _orchestrator: BehaviorOrchestrator) -> ClaimEvaluation:
    claim.meta.setdefault("expected_field", "hair_color")
    claim.meta.setdefault("label", "hair color")
    claim.meta.setdefault("text_fields", ("final_text", "draft_text"))
    return _eval_text_has_expected_value(tree, claim, _orchestrator)


def _eval_style_present(tree: BehaviorTree, claim: BehaviorClaim, _orchestrator: BehaviorOrchestrator) -> ClaimEvaluation:
    claim.meta.setdefault("expected_field", "style")
    claim.meta.setdefault("label", "style")
    claim.meta.setdefault("text_fields", ("final_text", "draft_text"))
    return _eval_text_has_expected_value(tree, claim, _orchestrator)


def _eval_unique_hair_colors(tree: BehaviorTree, _claim: BehaviorClaim, _orchestrator: BehaviorOrchestrator) -> ClaimEvaluation:
    _claim.meta.setdefault("child_field", "hair_color")
    _claim.meta.setdefault("label", "hair colors")
    return _eval_unique_child_field(tree, _claim, _orchestrator)


def _eval_unique_styles(tree: BehaviorTree, _claim: BehaviorClaim, _orchestrator: BehaviorOrchestrator) -> ClaimEvaluation:
    _claim.meta.setdefault("child_field", "style")
    _claim.meta.setdefault("label", "styles")
    return _eval_unique_child_field(tree, _claim, _orchestrator)


def _strip_think(text: str) -> str:
    """Remove <think>...</think> blocks and common LLM preamble/postamble from output."""
    import re

    cleaned = re.sub(r"<think>[\s\S]*?</think>\s*", "", text).strip()
    # Handle unclosed <think> block (model didn't emit </think>)
    if "<think>" in cleaned:
        cleaned = re.sub(r"<think>[\s\S]*$", "", cleaned).strip()
    # Handle case where entire text is inside an unclosed think
    if cleaned.startswith("<think>"):
        cleaned = ""

    # Strip markdown bold headers like **Описание внешности:**
    cleaned = re.sub(r"\*\*[^*]{2,60}\*\*:?\s*", "", cleaned).strip()

    # Strip common preamble patterns (Russian and English)
    preamble_patterns = [
        r"^(?:Вот|Ниже|Далее|Here is|Here's)[^\n]{0,120}?:\s*\n*",
        r"^(?:Исправленн|Дополненн|Переписанн|Обновлённ)[^\n]{0,120}?:\s*\n*",
        r"^(?:Описание внешности|Description)[^\n]{0,60}?:\s*\n*",
    ]
    for pattern in preamble_patterns:
        cleaned = re.sub(pattern, "", cleaned, flags=re.IGNORECASE).strip()

    # Strip trailing meta-comments
    cleaned = re.sub(r"\n+(?:Примечание|Надеюсь|Note|Итого|Если нужно)[^\n]*$", "", cleaned, flags=re.IGNORECASE).strip()

    return cleaned


def _get_bundle(node: BehaviorNode, bundle_id: str | None = None) -> dict[str, Any]:
    """Extract instruction bundle blocks as a dict with metadata and kind->content."""
    bundles = node.meta.get("instruction_bundles", [])
    if not bundles:
        return {}
    selected = bundles[0]
    if bundle_id:
        selected = next((bundle for bundle in bundles if bundle.get("bundle_id") == bundle_id), selected)
    payload = {
        "bundle_id": selected.get("bundle_id"),
        "author_agent": selected.get("author_agent"),
        "target_agent": selected.get("target_agent"),
        "strictness": selected.get("strictness"),
    }
    for block in selected.get("blocks", []):
        payload[block["kind"]] = block["content"]
    return payload


def _render_bundle_prompt(
    tree: BehaviorTree,
    node: BehaviorNode,
    bundle: dict[str, Any],
    *,
    extra_context: dict[str, Any] | None = None,
) -> str:
    parts: list[str] = []
    for key in ("context", "think", "answer"):
        content = bundle.get(key)
        if content:
            parts.append(_expand_template(str(content), tree, node, extra=_coerce_extra_context(extra_context)))
    return "\n".join(parts).strip()


def _build_repair_prompt(
    tree: BehaviorTree,
    node: BehaviorNode,
    failures: list[str],
    old_text: str,
    bundle: dict[str, Any],
    *,
    prompt_template: str | None = None,
    extra: dict[str, Any] | None = None,
) -> str:
    extra = _coerce_extra_context(extra)
    extra.setdefault("old_text", old_text)
    extra.setdefault("failures", failures)
    extra.setdefault("failures_text", ", ".join(str(item) for item in failures))
    if prompt_template:
        return _expand_template(prompt_template, tree, node, extra=extra)
    repair_context = bundle.get("context")
    if repair_context:
        return _render_bundle_prompt(tree, node, bundle, extra_context=extra)
    prompt = (
        f"Previous text failed validation.\n"
        f"Failures: {', '.join(failures)}.\n"
        f"Task: {_expand_template(str(node.data.get('prompt', '')), tree, node, extra=extra)}\n"
        f"Rewrite and fix the issues. Start directly with content.\n\n"
        f"Previous text:\n{old_text}"
    )
    return prompt


def _coerce_extra_context(extra: Any) -> dict[str, Any]:
    return dict(extra) if isinstance(extra, dict) else {}


def _template_context(tree: BehaviorTree, node: BehaviorNode, extra: dict[str, Any] | None = None) -> dict[str, Any]:
    values: dict[str, Any] = {
        "node_id": node.node_id,
        "tree_id": tree.tree_id,
        "node.kind": node.kind,
        "node.return_key": node.return_key or "",
        "global.language": tree.global_meta.get("language", "ru"),
        "global.sentence_range": tree.global_meta.get("sentence_range", [5, 10]),
        **{f"data.{key}": value for key, value in node.data.items()},
        **{f"global.{key}": value for key, value in tree.global_meta.items()},
    }
    if extra:
        for key, value in extra.items():
            values[key] = value
            if "." not in key:
                values[f"extra.{key}"] = value
    return values


def _resolve_template_key(context: dict[str, Any], key: str) -> Any:
    if key in context:
        return context[key]
    if "." not in key:
        return context.get(key)
    head, tail = key.split(".", 1)
    current = context.get(head)
    if isinstance(current, dict):
        for part in tail.split("."):
            if not isinstance(current, dict) or part not in current:
                return context.get(key)
            current = current[part]
        return current
    return context.get(key)


def _expand_template(text: str, tree: BehaviorTree, node: BehaviorNode, *, extra: dict[str, Any] | None = None) -> str:
    import re

    context = _template_context(tree, node, extra)
    rendered = text
    for match in re.findall(r"\{\$([^}]+)\}", text):
        value = _resolve_template_key(context, match.strip())
        rendered = rendered.replace("{$" + match + "}", _stringify_template_value(value))
    for match in re.findall(r"\{\{([^}]+)\}\}", text):
        value = _resolve_template_key(context, match.strip())
        rendered = rendered.replace("{{" + match + "}}", _stringify_template_value(value))
    return rendered


def _stringify_template_value(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, list):
        return ", ".join(str(item) for item in value)
    if isinstance(value, dict):
        return json.dumps(value, ensure_ascii=False)
    return str(value)


def _first_value(mapping: dict[str, Any], fields: tuple[str, ...]) -> Any:
    for field in fields:
        value = mapping.get(field)
        if value:
            return value
    return None


def _sentence_split(text: str) -> list[str]:
    parts = [item.strip() for item in text.replace("!", ".").replace("?", ".").split(".")]
    return [item for item in parts if item]


def _render_description(*, index: int, style: str, hair_color: str, sentence_count: int) -> str:
    color_phrase = f"{hair_color} hair" if hair_color else "an unmentioned hair color"
    base = [
        f"In {style}, character {index + 1} appears with {color_phrase} cut into a precise silhouette",
        f"The face is narrow, watchful, and framed by layered strands that shape the brow and jaw",
        f"The skin carries a clear tone that contrasts with the clothing and keeps attention on the features",
        f"The eyes are described with enough detail to make the expression feel deliberate rather than generic",
        f"The posture stays elegant and readable, so the body line supports the visual identity at a glance",
        f"Small surface details like lashes, cheekbones, and the bridge of the nose complete the appearance",
        f"The overall styling stays distinct enough that the figure would not be confused with the other descriptions",
        f"The final look remains focused on outward appearance instead of backstory or action",
    ]
    return " ".join(f"{sentence}." for sentence in base[:sentence_count])
