from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True)
class EntityRef:
    entity_type: str
    entity_id: str


@dataclass(frozen=True)
class EntityValue:
    ref: EntityRef
    labels: tuple[str, ...] = ()


@dataclass(frozen=True)
class SlotRef:
    slot_type: str
    slot_id: str


@dataclass
class SlotCell:
    ref: SlotRef
    accepted_entities: set[EntityRef] = field(default_factory=set)
    candidate_entities: set[EntityRef] = field(default_factory=set)
    z_exclusions: dict[str, set[EntityRef]] = field(default_factory=dict)
    rule_ids: list[str] = field(default_factory=list)


def attach_entity_to_slot(
    slot: SlotCell,
    entity: EntityRef,
    *,
    accepted: bool = False,
) -> None:
    if accepted:
        slot.accepted_entities.add(entity)
    else:
        slot.candidate_entities.add(entity)


def attach_rule_to_slot(slot: SlotCell, rule_id: str) -> None:
    if rule_id not in slot.rule_ids:
        slot.rule_ids.append(rule_id)


def exclude_entity_from_slot(slot: SlotCell, z_key: str, entity: EntityRef) -> None:
    slot.z_exclusions.setdefault(z_key, set()).add(entity)
