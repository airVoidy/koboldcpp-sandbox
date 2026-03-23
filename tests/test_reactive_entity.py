"""Tests for the reactive entity-based behavior tree runtime."""
from __future__ import annotations

import pytest
from unittest.mock import MagicMock, patch

from kobold_sandbox.reactive_entity import (
    Constraint,
    DialogEntry,
    EntityStatus,
    EventBus,
    Extractor,
    Listener,
    PipelineLayer,
    PropertyChangeEvent,
    ReactiveEntity,
    ReactiveTask,
    VerifyConfig,
)
from kobold_sandbox.reactive_runner import (
    EntityDslContext,
    ReactiveRunner,
    collect_field_from_entities,
    flatten_pipeline,
    unique_check_entities,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_task(**kwargs) -> ReactiveTask:
    """Create a minimal ReactiveTask for testing."""
    return ReactiveTask(task_id=kwargs.get("task_id", "test-task"), global_meta=kwargs.get("global_meta", {}))


def _make_mock_orchestrator(call_results: list[str] | None = None):
    """Create a mock BehaviorOrchestrator with a mock LLM backend."""
    from kobold_sandbox.behavior_orchestrator import BehaviorOrchestrator, LLMBackend

    llm = MagicMock(spec=LLMBackend)
    # Mock .get() to return truthy (agent exists)
    llm.get.return_value = True
    # Mock .call() to return from call_results sequentially
    results = list(call_results or ["mocked response"])
    call_count = {"n": 0}

    def _mock_call(*args, **kw):
        idx = min(call_count["n"], len(results) - 1)
        call_count["n"] += 1
        return results[idx]

    llm.call.side_effect = _mock_call

    orch = BehaviorOrchestrator(llm=llm)
    # Register __dsl__ handler
    from kobold_sandbox.dsl_interpreter import handle_dsl
    orch.register_handler("__dsl__", handle_dsl)
    return orch


# ---------------------------------------------------------------------------
# Core: ReactiveProperty + Events
# ---------------------------------------------------------------------------

class TestPropertyChangeEvent:
    def test_event_key(self):
        event = PropertyChangeEvent("desc-1", "text", "old", "new")
        assert event.event_key == "desc-1.text.changed"


class TestEventBus:
    def test_subscribe_and_emit(self):
        bus = EventBus()
        received = []
        listener = Listener(
            listener_id="test",
            event_pattern="*.text.changed",
            endpoint=lambda e, t: None,
        )
        bus.subscribe(listener)

        def dispatch(l, e):
            received.append(e.event_key)
            return {"status": "ok"}

        event = PropertyChangeEvent("desc-1", "text", None, "hello")
        bus.emit(event, dispatch)
        assert received == ["desc-1.text.changed"]

    def test_glob_matching(self):
        bus = EventBus()
        matched = []

        # Specific pattern
        bus.subscribe(Listener("specific", "desc-1.text.changed", endpoint=[]))
        # Wildcard pattern
        bus.subscribe(Listener("wildcard", "*.text.changed", endpoint=[]))
        # Non-matching
        bus.subscribe(Listener("other", "*.hair_color.changed", endpoint=[]))

        def dispatch(l, e):
            matched.append(l.listener_id)
            return {"status": "ok"}

        event = PropertyChangeEvent("desc-1", "text", None, "hello")
        bus.emit(event, dispatch)
        assert "specific" in matched
        assert "wildcard" in matched
        assert "other" not in matched

    def test_cascade_depth_limit(self):
        bus = EventBus(max_depth=3)
        depth_reached = {"max": 0}

        def dispatch(l, e):
            depth_reached["max"] = max(depth_reached["max"], bus._propagation_depth)
            # Trigger another event (cascade)
            inner_event = PropertyChangeEvent("desc-1", "text", "a", "b")
            bus.emit(inner_event, dispatch)
            return {"status": "ok"}

        bus.subscribe(Listener("cascade", "*.text.changed", endpoint=[]))
        event = PropertyChangeEvent("desc-1", "text", None, "hello")
        bus.emit(event, dispatch)

        assert depth_reached["max"] <= 3

    def test_listener_priority_order(self):
        bus = EventBus()
        order = []

        bus.subscribe(Listener("low", "*.text.changed", endpoint=[], priority=-1))
        bus.subscribe(Listener("high", "*.text.changed", endpoint=[], priority=10))
        bus.subscribe(Listener("mid", "*.text.changed", endpoint=[], priority=5))

        def dispatch(l, e):
            order.append(l.listener_id)
            return {"status": "ok"}

        bus.emit(PropertyChangeEvent("x", "text", None, "v"), dispatch)
        assert order == ["high", "mid", "low"]


class TestReactiveEntity:
    def test_get_set(self):
        bus = EventBus()
        entity = ReactiveEntity("e1", {"name": "Alice"}, bus)
        assert entity.get("name") == "Alice"
        entity.set("name", "Bob")
        assert entity.get("name") == "Bob"

    def test_set_emits_event(self):
        bus = EventBus()
        entity = ReactiveEntity("e1", {"text": "old"}, bus)
        events = []

        def dispatch(l, e):
            events.append(e)
            return {"status": "ok"}

        entity._dispatch_fn = dispatch
        bus.subscribe(Listener("test", "*.text.changed", endpoint=[]))

        entity.set("text", "new")
        assert len(events) == 1
        assert events[0].old_value == "old"
        assert events[0].new_value == "new"

    def test_no_event_on_same_value(self):
        bus = EventBus()
        entity = ReactiveEntity("e1", {"text": "same"}, bus)
        events = []

        def dispatch(l, e):
            events.append(e)
            return {"status": "ok"}

        entity._dispatch_fn = dispatch
        bus.subscribe(Listener("test", "*.text.changed", endpoint=[]))

        entity.set("text", "same")  # same value
        assert len(events) == 0

    def test_to_dict(self):
        bus = EventBus()
        entity = ReactiveEntity("e1", {"text": "hello", "style": "gothic"}, bus)
        d = entity.to_dict()
        assert d["entity_id"] == "e1"
        assert d["properties"]["text"] == "hello"
        assert d["dialog"] == []


# ---------------------------------------------------------------------------
# PipelineLayer + flatten
# ---------------------------------------------------------------------------

class TestPipelineLayer:
    def test_simple_ops(self):
        layers = [PipelineLayer(layer_id="gen", ops=[{"set": {"@text": "hello"}}])]
        flat = flatten_pipeline(layers)
        assert len(flat) == 1
        assert flat[0] == {"set": {"@text": "hello"}}

    def test_wraps_before_after(self):
        layers = [
            PipelineLayer(layer_id="inner", ops=[{"set": {"@text": "core"}}]),
            PipelineLayer(
                layer_id="outer",
                wraps="inner",
                before_ops=[{"set": {"$prep": True}}],
                after_ops=[{"set": {"$done": True}}],
            ),
        ]
        flat = flatten_pipeline(layers)
        assert len(flat) == 3
        assert flat[0] == {"set": {"$prep": True}}
        assert flat[1] == {"set": {"@text": "core"}}
        assert flat[2] == {"set": {"$done": True}}

    def test_override_replaces_inner(self):
        layers = [
            PipelineLayer(layer_id="inner", ops=[{"set": {"@text": "original"}}]),
            PipelineLayer(
                layer_id="outer",
                wraps="inner",
                override_ops=[{"set": {"@text": "replaced"}}],
            ),
        ]
        flat = flatten_pipeline(layers)
        assert len(flat) == 1
        assert flat[0] == {"set": {"@text": "replaced"}}

    def test_three_layer_stack(self):
        layers = [
            PipelineLayer(layer_id="core", ops=[{"set": {"@x": "core"}}]),
            PipelineLayer(layer_id="mid", wraps="core", before_ops=[{"set": {"$mid_b": 1}}], after_ops=[{"set": {"$mid_a": 1}}]),
            PipelineLayer(layer_id="outer", wraps="mid", before_ops=[{"set": {"$out_b": 1}}], after_ops=[{"set": {"$out_a": 1}}]),
        ]
        flat = flatten_pipeline(layers)
        # outer_before + mid_before + core + mid_after + outer_after
        assert len(flat) == 5
        assert flat[0] == {"set": {"$out_b": 1}}
        assert flat[1] == {"set": {"$mid_b": 1}}
        assert flat[2] == {"set": {"@x": "core"}}
        assert flat[3] == {"set": {"$mid_a": 1}}
        assert flat[4] == {"set": {"$out_a": 1}}

    def test_roundtrip(self):
        layer = PipelineLayer(
            layer_id="test",
            ops=[{"set": {"@x": 1}}],
            wraps="inner",
            before_ops=[{"log": "before"}],
            tags=["generate"],
        )
        d = layer.to_dict()
        restored = PipelineLayer.from_dict(d)
        assert restored.layer_id == "test"
        assert restored.wraps == "inner"
        assert restored.before_ops == [{"log": "before"}]


# ---------------------------------------------------------------------------
# EntityDslContext
# ---------------------------------------------------------------------------

class TestEntityDslContext:
    def test_dsl_reads_entity_properties(self):
        task = _make_task(global_meta={"language": "ru"})
        entity = task.add_entity("e1", {"style": "gothic", "text": ""})
        orch = _make_mock_orchestrator()

        adapter = EntityDslContext(entity, task, orch)
        ctx = adapter.to_dsl_context()

        # @style should read from entity properties
        from kobold_sandbox.dsl_interpreter import _read_ref
        assert _read_ref(ctx, "@style") == "gothic"
        # @@language should read from global_meta
        assert _read_ref(ctx, "@@language") == "ru"

    def test_sync_back_writes_to_entity(self):
        task = _make_task()
        entity = task.add_entity("e1", {"text": ""})
        orch = _make_mock_orchestrator()

        adapter = EntityDslContext(entity, task, orch)
        ctx = adapter.to_dsl_context()

        # Write via DslContext
        from kobold_sandbox.dsl_interpreter import _write_ref
        _write_ref(ctx, "@text", "hello world")

        changed = adapter.sync_back()
        assert "text" in changed
        assert entity.get("text") == "hello world"


# ---------------------------------------------------------------------------
# ReactiveTask serialization
# ---------------------------------------------------------------------------

class TestReactiveTask:
    def test_from_dict_round_trip(self):
        spec = {
            "task_id": "demo",
            "global_meta": {"sentence_range": [5, 10]},
            "entities": {
                "desc-1": {"properties": {"style": "gothic", "hair_color": "black"}},
                "desc-2": {"properties": {"style": "cyber", "hair_color": "white"}},
            },
            "pipeline": [
                {"layer_id": "gen", "ops": [{"set": {"@text": "stub"}}]},
            ],
            "extractors": [
                {"field": "hair_color", "question": "What hair color?", "constraint_list": "used_hair"},
            ],
            "constraints": [
                {"constraint_id": "unique_hair", "watches": ["*.hair_color.changed"], "check": {"not_empty": "@@used_hair"}},
            ],
            "verify_config": {"max_rounds": 3, "pass_keyword": "PASS"},
        }
        task = ReactiveTask.from_dict(spec)
        assert task.task_id == "demo"
        assert len(task.entities) == 2
        assert len(task.pipeline) == 1
        assert len(task.extractors) == 1
        assert len(task.constraints) == 1
        assert task.verify_config is not None
        assert task.verify_config.max_rounds == 3

        # Round trip
        d = task.to_dict()
        assert d["task_id"] == "demo"
        assert len(d["entities"]) == 2

    def test_add_entity(self):
        task = _make_task()
        entity = task.add_entity("e1", {"x": 1})
        assert "e1" in task.entities
        assert entity.get("x") == 1


# ---------------------------------------------------------------------------
# ReactiveRunner (with mocked LLM)
# ---------------------------------------------------------------------------

class TestReactiveRunner:
    def test_simple_pipeline_execution(self):
        """Test that pipeline ops execute and write to entity."""
        task = _make_task()
        task.add_entity("e1", {"text": ""})
        task.add_layer(PipelineLayer(
            layer_id="gen",
            ops=[{"set": {"@text": "generated text"}}],
        ))

        orch = _make_mock_orchestrator()
        runner = ReactiveRunner(orch)
        result = runner.run_task(task)

        assert result["entities"]["e1"]["properties"]["text"] == "generated text"
        assert result["entities"]["e1"]["status"] == "done"

    def test_sequential_constraint_accumulation(self):
        """Test that constraint lists grow with each entity."""
        task = _make_task(global_meta={"used_colors": []})
        task.add_entity("e1", {"color": "red"})
        task.add_entity("e2", {"color": "blue"})

        # Pipeline sets @text, then we'll check constraint accumulation
        task.add_layer(PipelineLayer(
            layer_id="gen",
            ops=[{"set": {"@text": "stub text"}}],
        ))

        # Extractor that reads color and appends to used_colors
        task.add_extractor(Extractor(
            field="color_extracted",
            question="What color?",
            constraint_list="used_colors",
            parse_mode="word",
        ))

        # Mock LLM: return the entity's color value
        orch = _make_mock_orchestrator(["red", "blue"])
        runner = ReactiveRunner(orch)
        result = runner.run_task(task)

        # After both entities, used_colors should have both
        assert "red" in task.global_meta.get("used_colors", [])
        assert "blue" in task.global_meta.get("used_colors", [])

    def test_entity_order_preserved(self):
        """Entities execute in order."""
        task = _make_task()
        order = []

        task.add_entity("a", {"text": ""})
        task.add_entity("b", {"text": ""})
        task.add_entity("c", {"text": ""})

        task.add_layer(PipelineLayer(layer_id="gen", ops=[{"set": {"@text": "x"}}]))

        orch = _make_mock_orchestrator()
        runner = ReactiveRunner(orch)

        def on_start(eid):
            order.append(eid)

        runner.run_task(task, on_entity_start=on_start)
        assert order == ["a", "b", "c"]

    def test_verify_dialog_pass_immediately(self):
        """If verifier says PASS on first round, dialog has 1 entry."""
        task = _make_task()
        task.add_entity("e1", {"text": ""})
        task.add_layer(PipelineLayer(layer_id="gen", ops=[{"set": {"@text": "good text"}}]))
        task.verify_config = VerifyConfig(max_rounds=3)

        # LLM returns PASS
        orch = _make_mock_orchestrator(["PASS - отличное описание"])
        runner = ReactiveRunner(orch)
        runner.run_task(task)

        entity = task.entities["e1"]
        assert entity.get("validated") is True
        assert len(entity.dialog) == 1
        assert entity.dialog[0].role == "verifier"
        assert entity.dialog[0].status == "pass"

    def test_verify_dialog_refine_then_pass(self):
        """Verifier fails first, instruction refines, verifier passes."""
        task = _make_task()
        task.add_entity("e1", {"text": ""})
        task.add_layer(PipelineLayer(layer_id="gen", ops=[{"set": {"@text": "initial text"}}]))
        task.verify_config = VerifyConfig(max_rounds=5)

        # LLM calls: 1) verifier FAIL, 2) instruction refine, 3) verifier PASS
        orch = _make_mock_orchestrator([
            "FAIL: нет описания позы",        # verifier round 0
            "Демонша сидит на троне...",       # instruction refine
            "PASS",                            # verifier round 1
        ])
        runner = ReactiveRunner(orch)
        runner.run_task(task)

        entity = task.entities["e1"]
        assert entity.get("validated") is True
        assert len(entity.dialog) == 3  # fail + refine + pass
        assert entity.dialog[0].status == "fail"
        assert entity.dialog[1].role == "instruction"
        assert entity.dialog[2].status == "pass"

    def test_pipeline_layers_accumulate_for_later_entities(self):
        """Entity 0 gets base pipeline, entity 1+ gets constraint wrapper."""
        task = _make_task(global_meta={"used_hair": ["black"]})
        task.add_entity("e1", {"text": ""})
        task.add_entity("e2", {"text": ""})
        task.add_layer(PipelineLayer(layer_id="gen", ops=[{"set": {"@text": "base"}}]))
        task.add_extractor(Extractor(field="hair", question="?", constraint_list="used_hair"))

        orch = _make_mock_orchestrator(["white", "white"])  # extraction results
        runner = ReactiveRunner(orch)

        # Check that _build_effective_layers adds constraint layer for entity 1
        e2 = task.entities["e2"]
        layers = runner._build_effective_layers(task, e2, 1)
        assert len(layers) == 2  # base + constraint wrapper
        assert layers[1].layer_id == "_constraints_1"


# ---------------------------------------------------------------------------
# Entity-aware helpers (in reactive_runner, not dsl_interpreter)
# ---------------------------------------------------------------------------

class TestEntityHelpers:
    def test_collect_field(self):
        global_meta = {
            "entities": {
                "e1": {"hair": "black"},
                "e2": {"hair": "white"},
                "e3": {"hair": "blue"},
            }
        }
        result = collect_field_from_entities(global_meta, "hair")
        assert result == ["black", "white", "blue"]

    def test_unique_check_pass(self):
        global_meta = {
            "entities": {"e1": {"hair": "black"}, "e2": {"hair": "white"}}
        }
        assert unique_check_entities(global_meta, "hair") is True

    def test_unique_check_fail(self):
        global_meta = {
            "entities": {"e1": {"hair": "black"}, "e2": {"hair": "black"}}
        }
        assert unique_check_entities(global_meta, "hair") is False


# ---------------------------------------------------------------------------
# Dialog entry
# ---------------------------------------------------------------------------

class TestDialogEntry:
    def test_to_dict(self):
        entry = DialogEntry("verifier", "PASS", "pass", 0)
        d = entry.to_dict()
        assert d == {"role": "verifier", "content": "PASS", "status": "pass", "round_index": 0}
