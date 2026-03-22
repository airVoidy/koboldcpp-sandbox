"""Tests for the Behavior Tree DSL interpreter v2.

Namespace: $x=local, @x=node.data, @@x=global_meta
Commands: set, save, copy, render, call, claims, if, for_each, append, outcome, return
"""
from __future__ import annotations

from kobold_sandbox.behavior_orchestrator import (
    BehaviorClaim,
    BehaviorElement,
    BehaviorNode,
    BehaviorOrchestrator,
    BehaviorTree,
    ClaimLifecycle,
    ClaimScope,
    LLMBackend,
)
from kobold_sandbox.dsl_interpreter import DslContext, _eval_test, _run_do, handle_dsl


def _make_tree(
    node_data: dict | None = None,
    elements: list[dict] | None = None,
    global_meta: dict | None = None,
    claims: list | None = None,
) -> tuple[BehaviorTree, BehaviorNode, BehaviorOrchestrator]:
    el_list = []
    for e in (elements or [{"element_id": "main", "handler": "__dsl__"}]):
        el_list.append(BehaviorElement(**e))

    node = BehaviorNode(
        node_id="test-node",
        kind="test",
        entry_element=el_list[0].element_id,
        elements=el_list,
        data=node_data or {},
        claims=claims or [],
    )
    tree = BehaviorTree(
        tree_id="test-tree",
        root_node_id="test-node",
        nodes={"test-node": node},
        global_meta=global_meta or {},
    )
    orch = BehaviorOrchestrator(llm=LLMBackend())
    from kobold_sandbox.dsl_interpreter import handle_dsl
    orch.register_handler("__dsl__", handle_dsl)
    return tree, node, orch


def _ctx(
    node_data: dict | None = None,
    global_meta: dict | None = None,
) -> DslContext:
    tree, node, orch = _make_tree(node_data=node_data, global_meta=global_meta)
    return DslContext(tree=tree, node=node, element=node.elements[0], orchestrator=orch)


# ── set ──

def test_set_local() -> None:
    ctx = _ctx()
    _run_do(ctx, [{"set": {"$x": 42}}])
    assert ctx.variables["x"] == 42


def test_set_node_data() -> None:
    ctx = _ctx()
    _run_do(ctx, [{"set": {"@status": "pending"}}])
    assert ctx.node.data["status"] == "pending"


def test_set_global() -> None:
    ctx = _ctx()
    _run_do(ctx, [{"set": {"@@mode": "strict"}}])
    assert ctx.tree.global_meta["mode"] == "strict"


def test_set_with_ref() -> None:
    ctx = _ctx(node_data={"name": "Airy"})
    _run_do(ctx, [{"set": {"$greeting": "@name"}}])
    assert ctx.variables["greeting"] == "Airy"


def test_set_inc() -> None:
    ctx = _ctx(node_data={"count": 3})
    _run_do(ctx, [{"set": {"@count": {"inc": "@count"}}}])
    assert ctx.node.data["count"] == 4


# ── save ──

def test_save_local_to_data() -> None:
    ctx = _ctx()
    ctx.variables["tmp"] = [1, 2, 3]
    _run_do(ctx, [{"save": {"@result": "$tmp"}}])
    assert ctx.node.data["result"] == [1, 2, 3]


# ── copy ──

def test_copy() -> None:
    ctx = _ctx(node_data={"src": "hello"})
    _run_do(ctx, [{"copy": {"from": "@src", "to": "@dst"}}])
    assert ctx.node.data["dst"] == "hello"


# ── render ──

def test_render_template() -> None:
    ctx = _ctx(node_data={"style": "gothic", "hair_color": "black"})
    _run_do(ctx, [{"render": {"to": "$prompt", "template": "Style: {$@style}. Hair: {$@hair_color}."}}])
    assert ctx.variables["prompt"] == "Style: gothic. Hair: black."


def test_render_with_global() -> None:
    ctx = _ctx(global_meta={"language": "ru"})
    _run_do(ctx, [{"render": {"to": "$msg", "template": "Lang: {$@@language}"}}])
    assert ctx.variables["msg"] == "Lang: ru"


def test_render_with_local_var() -> None:
    ctx = _ctx()
    _run_do(ctx, [
        {"set": {"$name": "test"}},
        {"render": {"to": "$out", "template": "Hello {$$name}!"}},
    ])
    assert ctx.variables["out"] == "Hello test!"


# ── call builtins ──

def test_call_len() -> None:
    ctx = _ctx()
    ctx.variables["items"] = [1, 2, 3]
    _run_do(ctx, [{"call": {"fn": "len", "args": {"value": "$items"}, "to": "$n"}}])
    assert ctx.variables["n"] == 3


def test_call_truncate_sentences() -> None:
    ctx = _ctx(node_data={"text": "One. Two. Three. Four. Five. Six.", "range": [2, 3]})
    _run_do(ctx, [{"call": {"fn": "truncate_sentences", "args": {"text": "@text", "range": "@range"}, "to": "$result"}}])
    # Should truncate to max 3
    assert ctx.variables["result"].count(".") <= 4  # 3 sentences + possible trailing


def test_call_unique() -> None:
    ctx = _ctx()
    ctx.variables["colors"] = ["red", "blue", "red", "green"]
    _run_do(ctx, [{"call": {"fn": "unique", "args": {"value": "$colors"}, "to": "$uniq"}}])
    assert ctx.variables["uniq"] == ["red", "blue", "green"]


def test_call_node_field() -> None:
    tree, node, orch = _make_tree(node_data={})
    other = BehaviorNode(
        node_id="other", kind="test", entry_element="x",
        elements=[BehaviorElement(element_id="x", handler="__dsl__")],
        data={"result": "from_other"},
    )
    tree.nodes["other"] = other
    ctx = DslContext(tree=tree, node=node, element=node.elements[0], orchestrator=orch)
    _run_do(ctx, [{"call": {"fn": "node_field", "args": {"node_id": "other", "field": "result"}, "to": "$val"}}])
    assert ctx.variables["val"] == "from_other"


# ── outcome & return ──

def test_outcome() -> None:
    ctx = _ctx()
    _run_do(ctx, [{"outcome": "pass"}])
    assert ctx.outcome == "pass"


def test_return() -> None:
    ctx = _ctx(node_data={"final": "done"})
    _run_do(ctx, [{"return": "@final"}])
    assert ctx.value == "done"


# ── if ──

def test_if_empty_true() -> None:
    ctx = _ctx()
    ctx.variables["failures"] = []
    _run_do(ctx, [{"if": {
        "test": {"empty": "$failures"},
        "then": [{"outcome": "pass"}],
        "else": [{"outcome": "fail"}],
    }}])
    assert ctx.outcome == "pass"


def test_if_empty_false() -> None:
    ctx = _ctx()
    ctx.variables["failures"] = ["bad"]
    _run_do(ctx, [{"if": {
        "test": {"empty": "$failures"},
        "then": [{"outcome": "pass"}],
        "else": [{"outcome": "fail"}],
    }}])
    assert ctx.outcome == "fail"


def test_if_contains() -> None:
    ctx = _ctx(node_data={"text": "She has black hair", "color": "black"})
    _run_do(ctx, [{"if": {
        "test": {"contains": ["@text", "@color"]},
        "then": [{"outcome": "pass"}],
        "else": [{"outcome": "fail"}],
    }}])
    assert ctx.outcome == "pass"


def test_if_in_range() -> None:
    ctx = _ctx()
    ctx.variables["count"] = 7
    _run_do(ctx, [{"if": {
        "test": {"in_range": ["$count", [5, 10]]},
        "then": [{"outcome": "pass"}],
        "else": [{"outcome": "fail"}],
    }}])
    assert ctx.outcome == "pass"


def test_if_all() -> None:
    ctx = _ctx(node_data={"text": "Black hair and blue eyes", "hair": "black"})
    _run_do(ctx, [{"if": {
        "test": {"all": [
            {"not_empty": "@text"},
            {"contains": ["@text", "@hair"]},
        ]},
        "then": [{"outcome": "pass"}],
    }}])
    assert ctx.outcome == "pass"


def test_if_not() -> None:
    ctx = _ctx(node_data={"x": 5})
    _run_do(ctx, [{"if": {
        "test": {"not": {"eq": ["@x", 10]}},
        "then": [{"set": {"$ok": True}}],
    }}])
    assert ctx.variables["ok"] is True


# ── for_each ──

def test_for_each() -> None:
    ctx = _ctx(node_data={"items": ["a", "b", "c"]})
    ctx.variables["collected"] = []
    _run_do(ctx, [{"for_each": {
        "in": "@items",
        "as": "$item",
        "do": [{"append": {"to": "$collected", "value": "$item"}}],
    }}])
    assert ctx.variables["collected"] == ["a", "b", "c"]


# ── append ──

def test_append() -> None:
    ctx = _ctx()
    ctx.variables["list"] = ["a"]
    _run_do(ctx, [{"append": {"to": "$list", "value": "b"}}])
    assert ctx.variables["list"] == ["a", "b"]


# ── collect ──

def test_collect_from_nodes() -> None:
    tree, node, orch = _make_tree(node_data={"child_ids": ["c1", "c2"]})
    for cid, val in [("c1", "text1"), ("c2", "text2")]:
        tree.nodes[cid] = BehaviorNode(
            node_id=cid, kind="test", entry_element="x",
            elements=[BehaviorElement(element_id="x", handler="__dsl__")],
            data={"final_text": val},
        )
    ctx = DslContext(tree=tree, node=node, element=node.elements[0], orchestrator=orch)
    _run_do(ctx, [{"collect": {"from_nodes": "@child_ids", "field": "final_text", "to": "$outputs"}}])
    assert ctx.variables["outputs"] == ["text1", "text2"]


# ── claims ──

def test_claims_shortcut() -> None:
    tree, node, orch = _make_tree(
        node_data={"draft_text": "short"},
        claims=[BehaviorClaim(
            claim_id="test-range",
            owner_node_id="test-node",
            scope=ClaimScope.NODE,
            evaluator="text_sentence_range",
            meta={"range_field": "sentence_range", "text_fields": ["draft_text"]},
        )],
        global_meta={"sentence_range": [5, 10]},
    )
    orch.register_claim_evaluator("text_sentence_range", _dummy_sentence_range_evaluator)
    ctx = DslContext(tree=tree, node=node, element=node.elements[0], orchestrator=orch)
    _run_do(ctx, [{"claims": "$fails"}])
    assert isinstance(ctx.variables["fails"], list)


def _dummy_sentence_range_evaluator(tree, claim, orch):
    from kobold_sandbox.behavior_orchestrator import ClaimEvaluation, ClaimLifecycle
    return ClaimEvaluation(status=ClaimLifecycle.FAIL, details="too short")


# ── coalesce ──

def test_coalesce() -> None:
    ctx = _ctx(node_data={"final_text": "", "draft_text": "fallback"})
    _run_do(ctx, [{"set": {"$text": {"coalesce": ["@final_text", "@draft_text"]}}}])
    assert ctx.variables["text"] == "fallback"


# ── DSL claim evaluation ──

def test_dsl_claim_eval() -> None:
    from kobold_sandbox.dsl_interpreter import eval_dsl_claim
    tree, node, orch = _make_tree(node_data={"draft_text": "She has black hair", "hair_color": "black"})
    claim = BehaviorClaim(
        claim_id="hair-check",
        owner_node_id="test-node",
        scope=ClaimScope.NODE,
        evaluator="__dsl__",
        meta={
            "dsl": {
                "test": {"contains": [{"coalesce": ["@final_text", "@draft_text"]}, "@hair_color"]},
                "pass": "hair color present",
                "fail": "hair color missing",
                "pending_if": {"empty": {"coalesce": ["@final_text", "@draft_text"]}},
            }
        },
    )
    status, details = eval_dsl_claim(tree, claim, orch)
    assert status == ClaimLifecycle.PASS
    assert details == "hair color present"


def test_dsl_claim_eval_fail() -> None:
    from kobold_sandbox.dsl_interpreter import eval_dsl_claim
    tree, node, orch = _make_tree(node_data={"draft_text": "She has blue eyes", "hair_color": "black"})
    claim = BehaviorClaim(
        claim_id="hair-check",
        owner_node_id="test-node",
        scope=ClaimScope.NODE,
        evaluator="__dsl__",
        meta={
            "dsl": {
                "test": {"contains": [{"coalesce": ["@final_text", "@draft_text"]}, "@hair_color"]},
                "pass": "ok",
                "fail": "hair color missing",
            }
        },
    )
    status, details = eval_dsl_claim(tree, claim, orch)
    assert status == ClaimLifecycle.FAIL
    assert details == "hair color missing"


def test_dsl_claim_pending() -> None:
    from kobold_sandbox.dsl_interpreter import eval_dsl_claim
    tree, node, orch = _make_tree(node_data={"draft_text": "", "hair_color": "black"})
    claim = BehaviorClaim(
        claim_id="hair-check",
        owner_node_id="test-node",
        scope=ClaimScope.NODE,
        evaluator="__dsl__",
        meta={
            "dsl": {
                "pending_if": {"empty": {"coalesce": ["@final_text", "@draft_text"]}},
                "test": {"contains": ["@draft_text", "@hair_color"]},
                "pass": "ok",
                "fail": "missing",
            }
        },
    )
    status, details = eval_dsl_claim(tree, claim, orch)
    assert status == ClaimLifecycle.PENDING


# ── Integration: full element run ──

def test_local_check_example() -> None:
    """The canonical local_check example from DSL spec."""
    tree, node, orch = _make_tree(
        node_data={"draft_text": "short"},
        elements=[{
            "element_id": "local_check",
            "handler": "__dsl__",
            "transitions": {"pass": "compress", "fail": "repair"},
            "meta": {
                "do": [
                    {"claims": "$local_failures"},
                    {"save": {"@local_failures": "$local_failures"}},
                    {"if": {
                        "test": {"empty": "$local_failures"},
                        "then": [{"outcome": "pass"}],
                        "else": [{"outcome": "fail"}],
                    }},
                ],
            },
        }, {
            "element_id": "repair",
            "handler": "__dsl__",
            "meta": {"do": [
                {"set": {"@repaired": True}},
                {"outcome": "done"},
            ]},
        }, {
            "element_id": "compress",
            "handler": "__dsl__",
            "meta": {"do": [{"outcome": "done"}]},
        }],
    )
    # No claims registered → empty failures → pass
    record = orch.run_node(tree, "test-node")
    assert "local_check" in record.executed_elements
    # With no claims, should go to compress
    assert "compress" in record.executed_elements


def test_repair_example() -> None:
    """Repair flow: inc counter, render prompt, save."""
    tree, node, orch = _make_tree(
        node_data={"repair_count": 0, "style": "gothic", "hair_color": "black", "draft_text": "old", "local_failures": ["too_short"]},
        elements=[{
            "element_id": "repair",
            "handler": "__dsl__",
            "meta": {"do": [
                {"set": {"@repair_count": {"inc": "@repair_count"}}},
                {"render": {"to": "$prompt", "template": "Fix: {$@local_failures}. Style: {$@style}. Old: {$@draft_text}"}},
                {"save": {"@draft_text": "$prompt"}},  # In real case this would be LLM output
                {"outcome": "pass"},
            ]},
        }],
    )
    record = orch.run_node(tree, "test-node")
    assert node.data["repair_count"] == 1
    assert "Fix:" in node.data["draft_text"]
    assert record.outcome == "pass"
