from __future__ import annotations

from dataclasses import dataclass, field

from .entity_slots import EntityRef, SlotCell, SlotRef


@dataclass(frozen=True)
class PossibleArgumentRow:
    slot_ref: SlotRef
    possible_entities: tuple[EntityRef, ...]
    excluded_entities: tuple[EntityRef, ...] = ()


@dataclass(frozen=True)
class PossibleArgumentMatrix:
    rule_id: str
    trigger: EntityRef
    rows: tuple[PossibleArgumentRow, ...]


@dataclass(frozen=True)
class DomainRuleLambda:
    rule_id: str
    container_type: str
    relation_kind: str
    left_type_ref: str
    right_type_ref: str
    left_entity: EntityRef
    right_entity: EntityRef
    distance: int = 0
    metadata: dict[str, object] = field(default_factory=dict)


@dataclass(frozen=True)
class CellBinding:
    binding_id: str
    rule_id: str
    slot_ref: SlotRef


@dataclass
class RuleRegistry:
    rules: dict[str, DomainRuleLambda] = field(default_factory=dict)

    def register(self, rule: DomainRuleLambda) -> None:
        self.rules[rule.rule_id] = rule

    def get(self, rule_id: str) -> DomainRuleLambda:
        return self.rules[rule_id]


@dataclass(frozen=True)
class RuleStage:
    stage_id: str
    stage_kind: str
    rule_ids: tuple[str, ...]


def bind_rule_to_slot(
    registry: RuleRegistry,
    slot: SlotCell,
    rule: DomainRuleLambda,
) -> CellBinding:
    registry.register(rule)
    if rule.rule_id not in slot.rule_ids:
        slot.rule_ids.append(rule.rule_id)
    return CellBinding(
        binding_id=f"{rule.rule_id}::{slot.ref.slot_id}",
        rule_id=rule.rule_id,
        slot_ref=slot.ref,
    )


def apply_same_container_rule(
    rule: DomainRuleLambda,
    trigger: EntityRef,
    slots: dict[SlotRef, SlotCell],
) -> PossibleArgumentMatrix:
    if trigger not in {rule.left_entity, rule.right_entity}:
        return PossibleArgumentMatrix(rule_id=rule.rule_id, trigger=trigger, rows=())
    counterpart = rule.right_entity if trigger == rule.left_entity else rule.left_entity
    rows = tuple(
        PossibleArgumentRow(
            slot_ref=slot_ref,
            possible_entities=tuple(
                entity
                for entity in sorted(
                    slot.candidate_entities | slot.accepted_entities,
                    key=lambda item: (item.entity_type, item.entity_id),
                )
                if entity == counterpart
            ),
        )
        for slot_ref, slot in slots.items()
        if slot_ref.slot_type == rule.container_type
    )
    return PossibleArgumentMatrix(rule_id=rule.rule_id, trigger=trigger, rows=rows)


def _sorted_house_slot_refs(slots: dict[SlotRef, SlotCell], container_type: str) -> tuple[SlotRef, ...]:
    return tuple(
        sorted(
            (slot_ref for slot_ref in slots if slot_ref.slot_type == container_type),
            key=lambda item: int(item.slot_id.split("-", 1)[1]),
        )
    )


def apply_positional_rule(
    rule: DomainRuleLambda,
    trigger: EntityRef,
    slots: dict[SlotRef, SlotCell],
) -> PossibleArgumentMatrix:
    if trigger not in {rule.left_entity, rule.right_entity}:
        return PossibleArgumentMatrix(rule_id=rule.rule_id, trigger=trigger, rows=())
    slot_refs = _sorted_house_slot_refs(slots, rule.container_type)
    trigger_on_left = trigger == rule.left_entity
    counterpart = rule.right_entity if trigger_on_left else rule.left_entity
    rows: list[PossibleArgumentRow] = []
    for index, slot_ref in enumerate(slot_refs):
        target_indices: list[int] = []
        if rule.relation_kind == "adjacent_pair":
            target_indices = [candidate for candidate in (index - 1, index + 1) if 0 <= candidate < len(slot_refs)]
        elif rule.relation_kind == "offset_pair":
            offset = -rule.distance if trigger_on_left else rule.distance
            candidate = index + offset
            if 0 <= candidate < len(slot_refs):
                target_indices = [candidate]
        possible_refs = {slot_refs[target_index] for target_index in target_indices}
        excluded_refs = {slot_ref for slot_ref in slot_refs if slot_ref not in possible_refs}
        rows.append(
            PossibleArgumentRow(
                slot_ref=slot_ref,
                possible_entities=(counterpart,) if possible_refs else (),
                excluded_entities=(counterpart,) if excluded_refs else (),
            )
        )
    return PossibleArgumentMatrix(rule_id=rule.rule_id, trigger=trigger, rows=tuple(rows))


def apply_atomic_rule(
    rule: DomainRuleLambda,
    trigger: EntityRef,
    slots: dict[SlotRef, SlotCell],
) -> PossibleArgumentMatrix:
    if rule.relation_kind == "same_house_pair":
        return apply_same_container_rule(rule, trigger, slots)
    if rule.relation_kind in {"adjacent_pair", "offset_pair"}:
        return apply_positional_rule(rule, trigger, slots)
    return PossibleArgumentMatrix(rule_id=rule.rule_id, trigger=trigger, rows=())
