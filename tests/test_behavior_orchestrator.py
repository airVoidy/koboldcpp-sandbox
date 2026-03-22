import pytest

from kobold_sandbox import (
    AnswerPrompt,
    BehaviorElement,
    ClaimLifecycle,
    ContextPrompt,
    InstructionBundle,
    SystemPrompt,
    ThinkPrompt,
    build_character_description_reference_tree,
    create_reference_behavior_orchestrator,
)
from kobold_sandbox.behavior_orchestrator import plan_and_build_tree


def _sentence_count(text: str) -> int:
    return len([item for item in text.replace("!", ".").replace("?", ".").split(".") if item.strip()])


def test_instruction_bundle_renders_typed_prompt_blocks() -> None:
    bundle = InstructionBundle(
        bundle_id="demo",
        author_agent="qwen_27b_planner",
        target_agent="small_context_worker",
        blocks=[
            SystemPrompt(content="You write strict task instructions."),
            ContextPrompt(content="Need one local generation step."),
            ThinkPrompt(content="Check the output against constraints."),
            AnswerPrompt(content="Return plain text only."),
        ],
    )

    rendered = bundle.render()

    assert "[system]" in rendered
    assert "[context]" in rendered
    assert "[think]" in rendered
    assert "[answer]" in rendered
    assert rendered.rstrip().endswith("Return plain text only.")


def test_reference_tree_resolves_agents_by_scope_and_action() -> None:
    tree = build_character_description_reference_tree()

    local_check_agents = tree.bindings.resolve_agents("description_item.local_check", "check")
    global_check_agents = tree.bindings.resolve_agents("description_root.global_check", "audit")

    assert [item.agent_name for item in local_check_agents] == ["small_context_worker", "qwen_27b_planner"]
    assert [item.agent_name for item in global_check_agents] == ["qwen_27b_planner"]


def test_reference_tree_roundtrips_through_json_serialization() -> None:
    tree = build_character_description_reference_tree()
    orchestrator = create_reference_behavior_orchestrator()

    payload = orchestrator.export_tree_json(tree)
    clone = build_character_description_reference_tree()
    orchestrator.update_tree_from_json(clone, payload)

    assert clone.tree_id == tree.tree_id
    assert clone.python_refs["tree_factory"].endswith("build_character_description_reference_tree")
    assert clone.node("description-01").python_refs["handler.draft"].endswith("_handle_llm_generate")
    assert clone.node("root").meta["instruction_bundles"][0]["bundle_id"] == "root-plan"


def test_reference_character_description_tree_runs_end_to_end() -> None:
    tree = build_character_description_reference_tree()
    orchestrator = create_reference_behavior_orchestrator()

    outputs = orchestrator.run_tree(tree)

    assert len(outputs) == 10
    assert all(5 <= _sentence_count(text) <= 10 for text in outputs)

    child_nodes = [tree.node(child_id) for child_id in tree.node("root").data["child_ids"]]
    hair_colors = [str(node.data["hair_color"]) for node in child_nodes]
    styles = [str(node.data["style"]) for node in child_nodes]

    assert len(set(hair_colors)) == 10
    assert len(set(styles)) == 10
    assert any(int(node.data["repair_count"]) > 0 for node in child_nodes)
    assert all(node.data["audit_status"] == "pass" for node in child_nodes)
    assert all(claim.status == ClaimLifecycle.PASS for claim in tree.global_claims)
    assert all(claim.status == ClaimLifecycle.PASS for node in child_nodes for claim in node.claims)

    for node in child_nodes:
        text = str(node.data["final_text"]).lower()
        assert str(node.data["hair_color"]).lower() in text
        assert str(node.data["style"]).lower() in text


def test_single_description_node_routes_through_repair_when_local_checks_fail() -> None:
    tree = build_character_description_reference_tree()
    orchestrator = create_reference_behavior_orchestrator()

    record = orchestrator.run_node(tree, "description-01")
    node = tree.node("description-01")

    assert record.executed_elements == ["draft", "local_check", "repair", "compress", "audit"]
    assert node.data["repair_count"] == 1
    assert all(claim.status == ClaimLifecycle.PASS for claim in node.claims)
    assert 5 <= _sentence_count(str(node.data["final_text"])) <= 10


def test_refresh_node_from_serialized_updates_unlocked_elements_and_preserves_locked_one() -> None:
    tree = build_character_description_reference_tree()
    orchestrator = create_reference_behavior_orchestrator()
    node = tree.node("description-02")

    updated = node.to_serialized_dict()
    updated["data"]["style"] = "baroque neon"
    updated["elements"][1]["handler"] = "local_check_v2"
    updated["elements"][2]["handler"] = "repair_v2"
    node.meta["serialized_node"] = updated
    node.current_element_id = "local_check"
    node.execution_lock = True

    orchestrator.refresh_node_from_meta(tree, node.node_id, lock_element_id="local_check")

    assert node.data["style"] == "baroque neon"
    assert node.element("local_check").handler == "evaluate_claims"
    assert node.element("repair").handler == "repair_v2"

    node.execution_lock = False
    node.current_element_id = None
    orchestrator.refresh_node_from_meta(tree, node.node_id)

    assert node.element("local_check").handler == "local_check_v2"


def test_run_node_releases_lock_when_handler_raises() -> None:
    tree = build_character_description_reference_tree()
    orchestrator = create_reference_behavior_orchestrator()
    node = tree.node("description-02")
    original = node.elements[0]
    node.elements[0] = BehaviorElement(element_id=original.element_id, handler="boom")

    def boom_handler(*_args, **_kwargs):
        raise RuntimeError("boom")

    orchestrator.register_handler("boom", boom_handler)

    try:
        orchestrator.run_node(tree, "description-02")
    except RuntimeError:
        pass
    else:
        raise AssertionError("expected RuntimeError")

    assert node.execution_lock is False
    assert node.current_element_id is None
    assert node.meta["last_error"] == "boom"


def test_llm_backend_uses_registered_client_chat_interface() -> None:
    from kobold_sandbox.behavior_orchestrator import LLMBackend

    seen: dict[str, object] = {}

    class FakeClient:
        def chat(self, prompt, model=None, system_prompt=None, config=None):
            seen["prompt"] = prompt
            seen["system_prompt"] = system_prompt
            seen["temperature"] = config.temperature
            seen["max_tokens"] = config.max_tokens
            return {"choices": [{"message": {"content": "ok"}}]}

        def extract_text(self, raw):
            seen["raw"] = raw
            return raw["choices"][0]["message"]["content"]

    backend = LLMBackend()
    backend.register("worker", FakeClient())

    text = backend.call("worker", "hello", system_prompt="sys", temperature=0.7, max_tokens=123)

    assert text == "ok"
    assert seen["system_prompt"] == "sys"
    assert seen["temperature"] == 0.7
    assert seen["max_tokens"] == 123
    assert "hello" in str(seen["prompt"])


@pytest.mark.live
def test_auto_plan_live() -> None:
    """Live test: planner decomposes task, workers execute. Requires LLM servers."""
    orchestrator = create_reference_behavior_orchestrator(
        worker_url="http://localhost:5001",
        planner_url="http://192.168.1.15:5050",
    )
    tree = plan_and_build_tree(
        "Создать 3 описания внешности персонажа в разных стилях. "
        "Каждое описание 5-8 предложений. Обязательно указать цвет волос и глаз.",
        orchestrator,
    )

    # Planner should create root + 3 items
    assert len(tree.nodes) >= 4, f"Expected >= 4 nodes, got {len(tree.nodes)}"
    assert "root" in tree.nodes

    # Run all
    outputs = orchestrator.run_tree(tree)
    assert len(outputs) >= 3, f"Expected >= 3 outputs, got {len(outputs)}"

    # Check each item passed audit
    for nid, node in tree.nodes.items():
        if nid == "root":
            continue
        assert node.data.get("audit_status") == "pass", f"{nid} audit failed"
        text = node.data.get("final_text", "")
        assert len(text) > 100, f"{nid} text too short: {len(text)} chars"
