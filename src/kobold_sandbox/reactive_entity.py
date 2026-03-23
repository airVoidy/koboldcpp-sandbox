"""Reactive Entity-Based Behavior Tree Runtime — Core Data Model.

Entity-based system with reactive events (listener.endpoint + listened.event)
and runtime lambda stacking. Same DSL ($x, @x, @@x), new runtime.

Key concepts:
- ReactiveEntity: lightweight object with observable properties
- EventBus: pub/sub within a task, fnmatch-based listener matching
- PipelineLayer: transparent lambda stack layer (before/after/override inner)
- Extractor: question-based field extraction from generated text
- Constraint: cross-entity rule with check + repair

Execution flow (N entities, pipeline invariant to N):
  For each entity (sequential):
    1. Generate text (creative LLM call with constraints from previous entities)
    2. text.changed → triggers extractors (short LLM calls)
    3. Extracted values → constraint lists grow (@@used_hair, @@used_eyes, ...)
    4. Next entity gets growing "BANNED" list in prompt
"""
from __future__ import annotations

import fnmatch
import json
from collections import OrderedDict
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Callable


# ---------------------------------------------------------------------------
# Enums
# ---------------------------------------------------------------------------

class EntityStatus(str, Enum):
    PENDING = "pending"
    GENERATING = "generating"
    EXTRACTING = "extracting"
    DONE = "done"
    FAILED = "failed"


# ---------------------------------------------------------------------------
# Events
# ---------------------------------------------------------------------------

@dataclass
class PropertyChangeEvent:
    entity_id: str
    property_name: str
    old_value: Any
    new_value: Any

    @property
    def event_key(self) -> str:
        return f"{self.entity_id}.{self.property_name}.changed"


# ---------------------------------------------------------------------------
# Listener
# ---------------------------------------------------------------------------

@dataclass
class Listener:
    """Subscription: listener.endpoint + listened.event."""
    listener_id: str
    event_pattern: str          # fnmatch glob: "*.text.changed", "desc-1.hair_color.changed"
    endpoint: list[dict] | Callable  # DSL ops or Python callable
    priority: int = 0           # higher = runs first, negative = runs last
    cross_entity: bool = False  # if True, endpoint sees all entities via @@entities
    enabled: bool = True


# ---------------------------------------------------------------------------
# EventBus
# ---------------------------------------------------------------------------

DispatchFn = Callable[[Listener, PropertyChangeEvent], dict]


class EventBus:
    """Pub/sub within a ReactiveTask. Listeners match events by fnmatch glob."""

    def __init__(self, max_depth: int = 10) -> None:
        self._listeners: list[Listener] = []
        self._propagation_depth: int = 0
        self._max_depth: int = max_depth
        self.event_log: list[dict] = []

    def subscribe(self, listener: Listener) -> None:
        self._listeners.append(listener)
        self._listeners.sort(key=lambda l: l.priority, reverse=True)

    def unsubscribe(self, listener_id: str) -> None:
        self._listeners = [l for l in self._listeners if l.listener_id != listener_id]

    def listeners_for(self, event_key: str) -> list[Listener]:
        return [
            l for l in self._listeners
            if l.enabled and fnmatch.fnmatch(event_key, l.event_pattern)
        ]

    def emit(self, event: PropertyChangeEvent, dispatch_fn: DispatchFn) -> list[dict]:
        """Emit event, call matching listeners via dispatch_fn.
        Returns list of listener execution results.
        """
        if self._propagation_depth >= self._max_depth:
            entry = {
                "event": event.event_key,
                "status": "cascade_limit",
                "depth": self._propagation_depth,
            }
            self.event_log.append(entry)
            return [entry]

        self._propagation_depth += 1
        results: list[dict] = []
        try:
            for listener in self._listeners:
                if not listener.enabled:
                    continue
                if not fnmatch.fnmatch(event.event_key, listener.event_pattern):
                    continue
                result = dispatch_fn(listener, event)
                results.append(result)
                self.event_log.append({
                    "event": event.event_key,
                    "listener": listener.listener_id,
                    "result": result.get("status", "unknown"),
                    "depth": self._propagation_depth,
                })
        finally:
            self._propagation_depth -= 1
        return results


# ---------------------------------------------------------------------------
# ReactiveProperty
# ---------------------------------------------------------------------------

class ReactiveProperty:
    """Observable property that emits events on change."""

    __slots__ = ("name", "value", "dirty", "_entity")

    def __init__(self, name: str, value: Any = None, entity: ReactiveEntity | None = None) -> None:
        self.name = name
        self.value = value
        self.dirty = False
        self._entity = entity

    def set(self, new_value: Any) -> None:
        old = self.value
        self.value = new_value
        self.dirty = True
        if self._entity is not None and old != new_value:
            self._entity._emit(self.name, old, new_value)

    def __repr__(self) -> str:
        return f"ReactiveProperty({self.name!r}, {self.value!r})"


# ---------------------------------------------------------------------------
# ReactiveEntity
# ---------------------------------------------------------------------------

class DialogEntry:
    """One turn in the instruction ↔ verifier dialog."""

    __slots__ = ("role", "content", "status", "round_index")

    def __init__(self, role: str, content: str, status: str = "pending", round_index: int = 0) -> None:
        self.role = role            # "instruction" | "verifier"
        self.content = content
        self.status = status        # "pending" | "pass" | "fail" | "error"
        self.round_index = round_index

    def to_dict(self) -> dict[str, Any]:
        return {
            "role": self.role,
            "content": self.content,
            "status": self.status,
            "round_index": self.round_index,
        }


class ReactiveEntity:
    """Lightweight entity with observable properties. NOT a behavior tree node."""

    def __init__(
        self,
        entity_id: str,
        properties: dict[str, Any],
        event_bus: EventBus,
    ) -> None:
        self.entity_id = entity_id
        self.status = EntityStatus.PENDING
        self.properties: dict[str, ReactiveProperty] = {}
        self.event_bus = event_bus
        self.variables: dict[str, Any] = {}  # $namespace (ephemeral per pipeline run)
        self.dialog: list[DialogEntry] = []  # instruction ↔ verifier conversation
        self._dispatch_fn: DispatchFn | None = None

        for name, value in properties.items():
            prop = ReactiveProperty(name, value, entity=self)
            self.properties[name] = prop

    def get(self, name: str) -> Any:
        prop = self.properties.get(name)
        return prop.value if prop else None

    def set(self, name: str, value: Any) -> None:
        if name not in self.properties:
            self.properties[name] = ReactiveProperty(name, entity=self)
        self.properties[name].set(value)

    def get_all(self) -> dict[str, Any]:
        return {k: v.value for k, v in self.properties.items()}

    def _emit(self, prop_name: str, old: Any, new: Any) -> None:
        if self._dispatch_fn is None:
            return
        event = PropertyChangeEvent(
            entity_id=self.entity_id,
            property_name=prop_name,
            old_value=old,
            new_value=new,
        )
        self.event_bus.emit(event, self._dispatch_fn)

    def to_dict(self) -> dict[str, Any]:
        return {
            "entity_id": self.entity_id,
            "status": self.status.value,
            "properties": {k: v.value for k, v in self.properties.items()},
            "dialog": [d.to_dict() for d in self.dialog],
        }


# ---------------------------------------------------------------------------
# PipelineLayer — transparent lambda stack
# ---------------------------------------------------------------------------

@dataclass
class PipelineLayer:
    """One layer in the lambda stack. Wraps an inner layer transparently.

    Execution order when flattened:
        before_ops → inner_ops (or override_ops) → after_ops
    """
    layer_id: str
    ops: list[dict] = field(default_factory=list)          # core ops (if no wraps)
    wraps: str | None = None                                # inner layer_id
    before_ops: list[dict] = field(default_factory=list)    # before inner
    after_ops: list[dict] = field(default_factory=list)     # after inner
    override_ops: list[dict] | None = None                  # replaces inner entirely
    tags: list[str] = field(default_factory=list)           # for addressing

    def to_dict(self) -> dict[str, Any]:
        d: dict[str, Any] = {"layer_id": self.layer_id}
        if self.ops:
            d["ops"] = self.ops
        if self.wraps:
            d["wraps"] = self.wraps
        if self.before_ops:
            d["before_ops"] = self.before_ops
        if self.after_ops:
            d["after_ops"] = self.after_ops
        if self.override_ops is not None:
            d["override_ops"] = self.override_ops
        if self.tags:
            d["tags"] = self.tags
        return d

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> PipelineLayer:
        return cls(
            layer_id=data["layer_id"],
            ops=data.get("ops", []),
            wraps=data.get("wraps"),
            before_ops=data.get("before_ops", []),
            after_ops=data.get("after_ops", []),
            override_ops=data.get("override_ops"),
            tags=data.get("tags", []),
        )


# ---------------------------------------------------------------------------
# Extractor — question-based field extraction
# ---------------------------------------------------------------------------

@dataclass
class Extractor:
    """Extracts a structured field from generated text via short LLM call."""
    field: str                          # target property: "hair_color"
    question: str                       # prompt: "Какой цвет волос в тексте? Одно слово."
    constraint_list: str | None = None  # global_meta key to append to: "used_hair"
    parse_mode: str = "word"            # "word" | "line" | "enum"
    enum_values: list[str] | None = None
    agent_name: str | None = None       # override agent for extraction
    max_tokens: int = 30
    no_think: bool = True

    def to_dict(self) -> dict[str, Any]:
        d: dict[str, Any] = {
            "field": self.field,
            "question": self.question,
            "parse_mode": self.parse_mode,
            "max_tokens": self.max_tokens,
            "no_think": self.no_think,
        }
        if self.constraint_list:
            d["constraint_list"] = self.constraint_list
        if self.enum_values:
            d["enum_values"] = self.enum_values
        if self.agent_name:
            d["agent_name"] = self.agent_name
        return d

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> Extractor:
        return cls(
            field=data["field"],
            question=data["question"],
            constraint_list=data.get("constraint_list"),
            parse_mode=data.get("parse_mode", "word"),
            enum_values=data.get("enum_values"),
            agent_name=data.get("agent_name"),
            max_tokens=data.get("max_tokens", 30),
            no_think=data.get("no_think", True),
        )


# ---------------------------------------------------------------------------
# VerifyConfig — instruction ↔ verifier dialog settings
# ---------------------------------------------------------------------------

@dataclass
class VerifyConfig:
    """Configuration for the instruction ↔ verifier dialog loop.

    Each entity goes through a dialog:
      [instruction LLM] generates/refines the prompt
      [verifier LLM] evaluates: PASS or FAIL + feedback
      ... repeat until PASS or max_rounds
    """
    instruction_agent: str = "small_context_worker"     # LLM that generates/refines
    verifier_agent: str = "small_context_worker"        # LLM that evaluates
    instruction_system: str = ""                        # system prompt for instruction LLM
    verifier_system: str = ""                           # system prompt for verifier LLM
    verifier_prompt_template: str = (
        "Оцени описание. Если хорошее — ответь PASS.\n"
        "Если нужно улучшить — ответь FAIL и опиши что исправить.\n\n"
        "Описание:\n{text}"
    )
    refine_prompt_template: str = (
        "Предыдущее описание получило замечания от верификатора:\n{feedback}\n\n"
        "Предыдущее описание:\n{text}\n\n"
        "Перепиши, исправив замечания. Начинай сразу с текста."
    )
    max_rounds: int = 5
    pass_keyword: str = "PASS"

    def to_dict(self) -> dict[str, Any]:
        return {
            "instruction_agent": self.instruction_agent,
            "verifier_agent": self.verifier_agent,
            "instruction_system": self.instruction_system,
            "verifier_system": self.verifier_system,
            "verifier_prompt_template": self.verifier_prompt_template,
            "refine_prompt_template": self.refine_prompt_template,
            "max_rounds": self.max_rounds,
            "pass_keyword": self.pass_keyword,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> VerifyConfig:
        return cls(**{k: v for k, v in data.items() if k in cls.__dataclass_fields__})


# ---------------------------------------------------------------------------
# Constraint — cross-entity rule
# ---------------------------------------------------------------------------

@dataclass
class Constraint:
    """Cross-entity rule with check + optional repair."""
    constraint_id: str
    watches: list[str]                      # event patterns: ["*.hair_color.changed"]
    check: dict                             # DSL test expression
    repair: list[dict] | None = None        # DSL ops for auto-repair
    max_repair_attempts: int = 3

    def to_dict(self) -> dict[str, Any]:
        d: dict[str, Any] = {
            "constraint_id": self.constraint_id,
            "watches": self.watches,
            "check": self.check,
            "max_repair_attempts": self.max_repair_attempts,
        }
        if self.repair:
            d["repair"] = self.repair
        return d

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> Constraint:
        return cls(
            constraint_id=data["constraint_id"],
            watches=data["watches"],
            check=data["check"],
            repair=data.get("repair"),
            max_repair_attempts=data.get("max_repair_attempts", 3),
        )


# ---------------------------------------------------------------------------
# ReactiveTask — container
# ---------------------------------------------------------------------------

class ReactiveTask:
    """Container for an entity-based reactive task.

    Pipeline is invariant to N — same flow for 4 or 100 entities.
    Constraint lists grow with each entity, ensuring uniqueness by construction.
    """

    def __init__(
        self,
        task_id: str,
        global_meta: dict[str, Any] | None = None,
    ) -> None:
        self.task_id = task_id
        self.event_bus = EventBus()
        self.global_meta: dict[str, Any] = global_meta or {}
        self.entities: OrderedDict[str, ReactiveEntity] = OrderedDict()
        self.pipeline: list[PipelineLayer] = []
        self.extractors: list[Extractor] = []
        self.constraints: list[Constraint] = []
        self.verify_config: VerifyConfig | None = None  # instruction ↔ verifier dialog
        self.revision: int = 0

    def add_entity(self, entity_id: str, properties: dict[str, Any]) -> ReactiveEntity:
        entity = ReactiveEntity(entity_id, properties, self.event_bus)
        self.entities[entity_id] = entity
        return entity

    def add_layer(self, layer: PipelineLayer) -> None:
        self.pipeline.append(layer)

    def add_extractor(self, extractor: Extractor) -> None:
        self.extractors.append(extractor)

    def add_constraint(self, constraint: Constraint) -> None:
        self.constraints.append(constraint)

    def add_listener(self, listener: Listener) -> None:
        self.event_bus.subscribe(listener)

    def get_layer(self, layer_id: str) -> PipelineLayer | None:
        return next((l for l in self.pipeline if l.layer_id == layer_id), None)

    def to_dict(self) -> dict[str, Any]:
        d: dict[str, Any] = {
            "task_id": self.task_id,
            "global_meta": self.global_meta,
            "entities": {eid: e.to_dict() for eid, e in self.entities.items()},
            "pipeline": [l.to_dict() for l in self.pipeline],
            "extractors": [x.to_dict() for x in self.extractors],
            "constraints": [c.to_dict() for c in self.constraints],
            "revision": self.revision,
            "event_log": self.event_bus.event_log[-100:],
        }
        if self.verify_config:
            d["verify_config"] = self.verify_config.to_dict()
        return d

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> ReactiveTask:
        task = cls(
            task_id=data["task_id"],
            global_meta=data.get("global_meta", {}),
        )

        # Entities
        for eid, edata in data.get("entities", {}).items():
            props = edata.get("properties", edata) if isinstance(edata, dict) else {}
            task.add_entity(eid, props)

        # Pipeline layers
        for ldata in data.get("pipeline", []):
            task.add_layer(PipelineLayer.from_dict(ldata))

        # Extractors
        for xdata in data.get("extractors", []):
            task.add_extractor(Extractor.from_dict(xdata))

        # Constraints
        for cdata in data.get("constraints", []):
            task.add_constraint(Constraint.from_dict(cdata))

        # Verify config
        if "verify_config" in data:
            task.verify_config = VerifyConfig.from_dict(data["verify_config"])

        # Listeners (raw, not auto-generated from constraints)
        for ldata in data.get("listeners", []):
            task.add_listener(Listener(
                listener_id=ldata.get("id", ldata.get("event", "")),
                event_pattern=ldata["event"],
                endpoint=ldata["endpoint"],
                priority=ldata.get("priority", 0),
                cross_entity=ldata.get("cross_entity", False),
            ))

        return task
