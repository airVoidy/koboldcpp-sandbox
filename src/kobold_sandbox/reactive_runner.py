"""Reactive Entity Runner — execution engine for ReactiveTask.

Reuses existing DSL interpreter (_run_do, _read_ref, _write_ref, etc.)
via EntityDslContext adapter that makes ReactiveEntity look like a DslContext.

Key execution flow:
    For each entity (sequential, order matters):
        1. Build effective pipeline (base + accumulated constraint layers)
        2. Flatten lambda stack → list of DSL ops
        3. _run_do(ctx, ops) → sync_back (triggers events)
        4. Events → extractors → constraint lists grow
        5. Next entity sees updated constraints
"""
from __future__ import annotations

import logging
import re
import threading
from typing import Any, TYPE_CHECKING

from .reactive_entity import (
    Constraint,
    DialogEntry,
    EntityStatus,
    Extractor,
    Listener,
    PipelineLayer,
    PropertyChangeEvent,
    ReactiveEntity,
    ReactiveTask,
    VerifyConfig,
)

if TYPE_CHECKING:
    from .behavior_orchestrator import BehaviorOrchestrator

from .dsl_interpreter import (
    BUILTIN_FNS,
    DslContext,
    DslHalt,
    _eval_test,
    _run_do,
    _read_ref,
    _render_template,
    _write_ref,
)
from .behavior_orchestrator import (
    BehaviorElement,
    BehaviorNode,
    BehaviorTree,
    LLMBackend,
    _strip_think,
)

log = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Entity-aware helper functions (not in dsl_interpreter — kept separate)
# ---------------------------------------------------------------------------

def collect_field_from_entities(global_meta: dict, field: str) -> list:
    """Gather a field from all entities in @@entities dict."""
    entities = global_meta.get("entities", {})
    return [edata.get(field) for edata in entities.values() if isinstance(edata, dict)]


def unique_check_entities(global_meta: dict, field: str) -> bool:
    """Check if a field is unique across all entities."""
    values = collect_field_from_entities(global_meta, field)
    non_empty = [v for v in values if v]
    return len(non_empty) == len(set(str(v) for v in non_empty))


# ---------------------------------------------------------------------------
# Pipeline flattening
# ---------------------------------------------------------------------------

def flatten_pipeline(layers: list[PipelineLayer]) -> list[dict]:
    """Resolve wraps chain into a flat list of DSL ops.

    Execution order: before₁ + before₂ + ... + core_ops + ... + after₂ + after₁
    If a layer has override_ops, it replaces the inner ops entirely.
    """
    if not layers:
        return []

    # Build layer index
    by_id: dict[str, PipelineLayer] = {l.layer_id: l for l in layers}

    # Find outermost layer (not wrapped by anyone)
    wrapped_ids = {l.wraps for l in layers if l.wraps}
    outer_ids = [l.layer_id for l in layers if l.layer_id not in wrapped_ids]

    if not outer_ids:
        # No clear outer — just concatenate all ops
        result: list[dict] = []
        for layer in layers:
            result.extend(layer.ops)
        return result

    # Resolve from outermost inward
    def _resolve(layer_id: str, depth: int = 0) -> list[dict]:
        if depth > 20:
            return []  # safety: prevent infinite wraps loops
        layer = by_id.get(layer_id)
        if layer is None:
            return []

        # Get inner ops
        if layer.wraps and layer.wraps in by_id:
            if layer.override_ops is not None:
                inner = layer.override_ops
            else:
                inner = _resolve(layer.wraps, depth + 1)
        else:
            inner = list(layer.ops)

        return list(layer.before_ops) + inner + list(layer.after_ops)

    # Flatten from each outer layer
    result = []
    for outer_id in outer_ids:
        result.extend(_resolve(outer_id))
    return result


# ---------------------------------------------------------------------------
# EntityDslContext — adapter
# ---------------------------------------------------------------------------

class EntityDslContext:
    """Adapts ReactiveEntity + ReactiveTask to DslContext for the DSL interpreter.

    Maps:
        @x → entity.properties (via BehaviorNode.data shim)
        @@x → task.global_meta (via BehaviorTree.global_meta shim)
        $x → DslContext.variables (ephemeral)
    """

    def __init__(
        self,
        entity: ReactiveEntity,
        task: ReactiveTask,
        orchestrator: BehaviorOrchestrator,
    ) -> None:
        self.entity = entity
        self.task = task
        self.orchestrator = orchestrator

        # Build shim objects so existing _read_ref/_write_ref work
        self._node = BehaviorNode(
            node_id=entity.entity_id,
            kind="reactive_entity",
            entry_element="__virtual__",
            data=entity.get_all(),
        )
        self._tree = BehaviorTree(
            tree_id=task.task_id,
            root_node_id=entity.entity_id,
            nodes={entity.entity_id: self._node},
            global_meta=dict(task.global_meta),
        )
        self._element = BehaviorElement(
            element_id="__virtual__",
            handler="__dsl__",
        )

    def to_dsl_context(self) -> DslContext:
        return DslContext(
            tree=self._tree,
            node=self._node,
            element=self._element,
            orchestrator=self.orchestrator,
        )

    def sync_back(self) -> list[str]:
        """Write changes from DslContext back to entity properties.
        Returns list of changed property names.
        """
        changed: list[str] = []
        for key, value in self._node.data.items():
            old = self.entity.get(key)
            if old != value:
                self.entity.set(key, value)
                changed.append(key)

        # Sync global_meta changes back to task
        for key, value in self._tree.global_meta.items():
            if key not in self.task.global_meta or self.task.global_meta[key] != value:
                self.task.global_meta[key] = value

        return changed

    def inject_entities_into_global(self) -> None:
        """Make all entities visible as @@entities for cross-entity ops."""
        self._tree.global_meta["entities"] = {
            eid: e.get_all() for eid, e in self.task.entities.items()
        }
        self._tree.global_meta["entity_ids"] = list(self.task.entities.keys())


# ---------------------------------------------------------------------------
# ReactiveRunner
# ---------------------------------------------------------------------------

class ReactiveRunner:
    """Executes a ReactiveTask: sequential entities, reactive events, lambda stacking."""

    def __init__(self, orchestrator: BehaviorOrchestrator) -> None:
        self.orchestrator = orchestrator

    def run_task(
        self,
        task: ReactiveTask,
        *,
        on_entity_start: Any = None,
        on_entity_done: Any = None,
    ) -> dict[str, Any]:
        """Execute all entities through the pipeline, sequentially.

        Each entity accumulates constraints for the next one.
        Pipeline is invariant to N.
        """

        # Wire up dispatch function for the event bus
        def dispatch_fn(listener: Listener, event: PropertyChangeEvent) -> dict:
            return self._dispatch_listener(task, listener, event)

        for entity in task.entities.values():
            entity._dispatch_fn = dispatch_fn

        results: dict[str, dict] = {}
        entity_list = list(task.entities.values())

        for i, entity in enumerate(entity_list):
            if on_entity_start:
                on_entity_start(entity.entity_id)

            entity.status = EntityStatus.GENERATING
            entity.variables.clear()

            # Build effective pipeline with accumulated constraints
            effective_layers = self._build_effective_layers(task, entity, i)
            flat_ops = flatten_pipeline(effective_layers)

            # Execute pipeline via DSL interpreter
            adapter = EntityDslContext(entity, task, self.orchestrator)
            adapter.inject_entities_into_global()
            ctx = adapter.to_dsl_context()

            # Inject entity index into local vars
            ctx.variables["_entity_index"] = i
            ctx.variables["_entity_id"] = entity.entity_id
            ctx.variables["_entity_count"] = len(entity_list)

            try:
                _run_do(ctx, flat_ops)
                # Capture think content from DSL variables before sync
                if ctx.variables.get("_last_think"):
                    entity.set("_think", ctx.variables["_last_think"])
                adapter.sync_back()  # triggers events

                # Run instruction ↔ verifier dialog if configured
                if task.verify_config:
                    self._run_verify_dialog(task, entity, task.verify_config)

                entity.status = EntityStatus.EXTRACTING

                # Run extractors (extract structured fields, accumulate constraints)
                self._run_extractors(task, entity)

                entity.status = EntityStatus.DONE
            except DslHalt:
                adapter.sync_back()
                entity.status = EntityStatus.DONE
            except Exception as exc:
                log.error("Entity %s failed: %s", entity.entity_id, exc)
                entity.status = EntityStatus.FAILED
                entity.set("_error", str(exc))

            results[entity.entity_id] = entity.to_dict()

            if on_entity_done:
                on_entity_done(entity.entity_id, entity.status.value)

        # Post-run: evaluate cross-entity constraints
        constraint_results = self._run_constraints(task)

        task.revision += 1
        return {
            "task_id": task.task_id,
            "entities": results,
            "constraint_results": constraint_results,
            "event_log": task.event_bus.event_log[-200:],
            "revision": task.revision,
        }

    # --- Verify dialog (instruction ↔ verifier) ---

    def _run_verify_dialog(
        self,
        task: ReactiveTask,
        entity: ReactiveEntity,
        config: VerifyConfig,
    ) -> None:
        """Run instruction ↔ verifier dialog until PASS or max_rounds.

        Round 0: verifier evaluates initial text
        Round N: instruction LLM refines based on feedback → verifier re-evaluates
        Each round is stored in entity.dialog for inspection.
        """
        text = entity.get("text")
        if not text:
            return

        for round_idx in range(config.max_rounds):
            # --- Verifier turn ---
            verifier_prompt = config.verifier_prompt_template.replace("{text}", str(text))

            # Inject constraint context into verifier prompt
            for extractor in task.extractors:
                if extractor.constraint_list:
                    used = task.global_meta.get(extractor.constraint_list, [])
                    verifier_prompt = verifier_prompt.replace(
                        f"{{{extractor.constraint_list}}}", ", ".join(str(v) for v in used)
                    )

            if not self.orchestrator.llm.get(config.verifier_agent):
                # No verifier agent — skip dialog, mark as pass
                entity.dialog.append(DialogEntry("verifier", "PASS (no agent)", "pass", round_idx))
                entity.set("validated", True)
                return

            try:
                verifier_raw = self.orchestrator.llm.call(
                    config.verifier_agent,
                    verifier_prompt,
                    system_prompt=config.verifier_system or None,
                    temperature=0.2,
                    max_tokens=512,
                    no_think=True,
                )
                verifier_text = _strip_think(verifier_raw).strip()
            except Exception as exc:
                entity.dialog.append(DialogEntry("verifier", f"ERROR: {exc}", "error", round_idx))
                return

            # Check if PASS
            is_pass = config.pass_keyword.upper() in verifier_text.upper()
            status = "pass" if is_pass else "fail"
            entity.dialog.append(DialogEntry("verifier", verifier_text, status, round_idx))

            if is_pass:
                entity.set("validated", True)
                return

            # --- Instruction turn (refine) ---
            if round_idx >= config.max_rounds - 1:
                break  # last round, no more refinement

            refine_prompt = (
                config.refine_prompt_template
                .replace("{feedback}", verifier_text)
                .replace("{text}", str(text))
            )

            if not self.orchestrator.llm.get(config.instruction_agent):
                break

            try:
                refined_raw = self.orchestrator.llm.call(
                    config.instruction_agent,
                    refine_prompt,
                    system_prompt=config.instruction_system or None,
                    temperature=0.6,
                    max_tokens=2048,
                    no_think=True,
                )
                text = _strip_think(refined_raw).strip()
                entity.dialog.append(DialogEntry("instruction", text, "pending", round_idx))

                # Update entity text (triggers events)
                entity.set("text", text)
            except Exception as exc:
                entity.dialog.append(DialogEntry("instruction", f"ERROR: {exc}", "error", round_idx))
                return

        # Exhausted rounds without PASS
        entity.set("validated", False)

    # --- Pipeline construction ---

    def _build_effective_layers(
        self,
        task: ReactiveTask,
        entity: ReactiveEntity,
        entity_index: int,
    ) -> list[PipelineLayer]:
        """Build pipeline layers for this entity.

        Entity 0: base layers only.
        Entity N>0: base layers + constraint wrapper that injects example + banned lists.
        """
        layers = list(task.pipeline)

        if entity_index == 0 or not layers:
            return layers

        # Find the outermost layer to wrap
        wrapped_ids = {l.wraps for l in layers if l.wraps}
        outer_ids = [l.layer_id for l in layers if l.layer_id not in wrapped_ids]
        outermost = outer_ids[0] if outer_ids else layers[-1].layer_id

        # Build constraint layer that wraps the outermost
        constraint_layer = PipelineLayer(
            layer_id=f"_constraints_{entity_index}",
            wraps=outermost,
            before_ops=self._build_constraint_before_ops(task),
            tags=["constraints", "auto"],
        )
        layers.append(constraint_layer)
        return layers

    def _build_constraint_before_ops(self, task: ReactiveTask) -> list[dict]:
        """Build DSL ops that set up constraint variables from global_meta."""
        ops: list[dict] = []

        # Collect all constraint lists from global_meta
        constraint_vars: dict[str, list] = {}
        for extractor in task.extractors:
            if extractor.constraint_list:
                key = extractor.constraint_list
                values = task.global_meta.get(key, [])
                if values:
                    constraint_vars[key] = values

        # Set each constraint list as a local variable for prompt rendering
        for key, values in constraint_vars.items():
            ops.append({"set": {f"${key}": values}})

        # Find first completed entity's text as example
        for entity in task.entities.values():
            if entity.status == EntityStatus.DONE and entity.get("text"):
                ops.append({"set": {"$_example_text": entity.get("text")}})
                break

        return ops

    # --- Event dispatch ---

    def _dispatch_listener(
        self,
        task: ReactiveTask,
        listener: Listener,
        event: PropertyChangeEvent,
    ) -> dict:
        """Execute a listener's endpoint in response to an event."""
        entity = task.entities.get(event.entity_id)
        if not entity:
            return {"status": "error", "message": f"entity {event.entity_id} not found"}

        if isinstance(listener.endpoint, list):
            adapter = EntityDslContext(entity, task, self.orchestrator)
            if listener.cross_entity:
                adapter.inject_entities_into_global()
            ctx = adapter.to_dsl_context()

            # Inject event metadata
            ctx.variables["_event_entity"] = event.entity_id
            ctx.variables["_event_property"] = event.property_name
            ctx.variables["_event_old"] = event.old_value
            ctx.variables["_event_new"] = event.new_value

            try:
                _run_do(ctx, listener.endpoint)
                adapter.sync_back()
                return {"status": "ok", "listener": listener.listener_id}
            except DslHalt:
                adapter.sync_back()
                return {"status": "halted", "listener": listener.listener_id}
            except Exception as exc:
                return {"status": "error", "listener": listener.listener_id, "error": str(exc)}

        elif callable(listener.endpoint):
            try:
                listener.endpoint(event, task)
                return {"status": "ok", "listener": listener.listener_id}
            except Exception as exc:
                return {"status": "error", "listener": listener.listener_id, "error": str(exc)}

        return {"status": "noop"}

    # --- Extractors ---

    def _run_extractors(self, task: ReactiveTask, entity: ReactiveEntity) -> None:
        """Run all extractors on entity's text, populate properties, accumulate constraints."""
        text = entity.get("text")
        if not text:
            return

        for extractor in task.extractors:
            agent_name = (
                extractor.agent_name
                or task.global_meta.get("extract_agent")
                or task.global_meta.get("creative_agent", "small_context_worker")
            )
            if not self.orchestrator.llm.get(agent_name):
                continue

            # Build extraction prompt
            prompt = f"{extractor.question}\n\nТекст:\n{text}"

            try:
                raw = self.orchestrator.llm.call(
                    agent_name,
                    prompt,
                    temperature=0.1,
                    max_tokens=extractor.max_tokens,
                    no_think=extractor.no_think,
                )
                value = self._parse_extraction(raw, extractor)

                # Set property on entity (triggers events)
                entity.set(extractor.field, value)

                # Accumulate into constraint list
                if extractor.constraint_list and value:
                    key = extractor.constraint_list
                    current = task.global_meta.get(key, [])
                    if not isinstance(current, list):
                        current = []
                    if value not in current:
                        current.append(value)
                        task.global_meta[key] = current

            except Exception as exc:
                log.warning("Extractor %s failed for %s: %s", extractor.field, entity.entity_id, exc)

    def _parse_extraction(self, raw: str, extractor: Extractor) -> Any:
        """Parse raw LLM output according to extractor's parse_mode."""
        cleaned = _strip_think(raw).strip()

        if extractor.parse_mode == "word":
            # First word
            words = cleaned.split()
            return words[0] if words else cleaned

        if extractor.parse_mode == "line":
            lines = cleaned.split("\n")
            return lines[0].strip() if lines else cleaned

        if extractor.parse_mode == "enum" and extractor.enum_values:
            upper = cleaned.upper()
            for val in extractor.enum_values:
                if val.upper() in upper:
                    return val
            return cleaned

        return cleaned

    # --- Constraints ---

    def _run_constraints(self, task: ReactiveTask) -> list[dict]:
        """Evaluate all cross-entity constraints. Attempt repair if configured."""
        results: list[dict] = []
        for constraint in task.constraints:
            result = self._evaluate_constraint(task, constraint)
            results.append(result)
        return results

    def _evaluate_constraint(self, task: ReactiveTask, constraint: Constraint) -> dict:
        """Check a constraint across all entities. Returns status dict."""
        # Build synthetic context with access to all entities
        first_entity = next(iter(task.entities.values()), None)
        if not first_entity:
            return {"constraint_id": constraint.constraint_id, "status": "skip", "message": "no entities"}

        adapter = EntityDslContext(first_entity, task, self.orchestrator)
        adapter.inject_entities_into_global()
        ctx = adapter.to_dsl_context()

        passed = _eval_test(ctx, constraint.check)
        if passed:
            return {"constraint_id": constraint.constraint_id, "status": "pass"}

        # Attempt repair
        if constraint.repair:
            for attempt in range(constraint.max_repair_attempts):
                for entity in task.entities.values():
                    repair_adapter = EntityDslContext(entity, task, self.orchestrator)
                    repair_adapter.inject_entities_into_global()
                    repair_ctx = repair_adapter.to_dsl_context()
                    repair_ctx.variables["_constraint_failure"] = constraint.constraint_id
                    repair_ctx.variables["_repair_attempt"] = attempt
                    try:
                        _run_do(repair_ctx, constraint.repair)
                        repair_adapter.sync_back()
                    except (DslHalt, Exception):
                        pass

                # Re-check
                adapter2 = EntityDslContext(first_entity, task, self.orchestrator)
                adapter2.inject_entities_into_global()
                ctx2 = adapter2.to_dsl_context()
                if _eval_test(ctx2, constraint.check):
                    return {
                        "constraint_id": constraint.constraint_id,
                        "status": "repaired",
                        "attempts": attempt + 1,
                    }

        return {"constraint_id": constraint.constraint_id, "status": "fail"}
