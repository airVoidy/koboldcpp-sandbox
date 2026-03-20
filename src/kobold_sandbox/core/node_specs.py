from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any

from .checklist import HypothesisEntry

if TYPE_CHECKING:
    from .state_graph import StateSnapshot


@dataclass(frozen=True)
class SameHousePair:
    left_ns: str
    left_value: str
    right_ns: str
    right_value: str
    universe_keys: tuple[str, ...]
    left_label: str | None = None
    right_label: str | None = None
    left_cell_prefix: str | None = None
    right_cell_prefix: str | None = None
    statement: str = ""


@dataclass(frozen=True)
class AdjacentPair:
    left_ns: str
    left_value: str
    right_ns: str
    right_value: str
    left_label: str | None = None
    right_label: str | None = None
    left_cell_prefix: str | None = None
    right_cell_prefix: str | None = None
    statement: str = ""


@dataclass(frozen=True)
class OffsetPair:
    left_ns: str
    left_value: str
    right_ns: str
    right_value: str
    distance: int = 1
    left_label: str | None = None
    right_label: str | None = None
    left_cell_prefix: str | None = None
    right_cell_prefix: str | None = None
    statement: str = ""


@dataclass(frozen=True)
class HypothesisLink:
    kind: str
    target_spec_id: str
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class NodeSpec:
    node_id: str
    kind: str
    entrypoint: str
    payload: object
    priority: int = 100
    depends_on: tuple[str, ...] = ()
    links: tuple[HypothesisLink, ...] = ()
    tags: tuple[str, ...] = ()


@dataclass(frozen=True)
class NodeInstance:
    instance_id: str
    spec_id: str
    state_id: str
    bindings: dict[str, Any] = field(default_factory=dict)


class TickPlanner:
    def __init__(self, *, max_branch_candidates: int = 2):
        self.max_branch_candidates = max_branch_candidates

    def materialize(self, spec: NodeSpec, snapshot: "StateSnapshot") -> list[NodeInstance]:
        payload = spec.payload
        if isinstance(payload, SameHousePair):
            candidates = self._resolve_same_house_candidates(payload, snapshot)
            if not candidates:
                return []
            return [
                NodeInstance(
                    instance_id=f"{spec.node_id}-{candidate['house']}",
                    spec_id=spec.node_id,
                    state_id=snapshot.state_id,
                    bindings=candidate,
                )
                for candidate in candidates
            ]
        if isinstance(payload, AdjacentPair):
            candidates = self._resolve_adjacent_candidates(payload, snapshot)
            if not candidates:
                return []
            return [
                NodeInstance(
                    instance_id=(spec.node_id if candidate.get("materialization_kind") != "domain_branch" else f"{spec.node_id}-{candidate['branch_id']}"),
                    spec_id=spec.node_id,
                    state_id=snapshot.state_id,
                    bindings=candidate,
                )
                for candidate in candidates
            ]
        if isinstance(payload, OffsetPair):
            candidates = self._resolve_offset_candidates(payload, snapshot)
            if not candidates:
                return []
            return [
                NodeInstance(
                    instance_id=(spec.node_id if candidate.get("materialization_kind") != "domain_branch" else f"{spec.node_id}-{candidate['branch_id']}"),
                    spec_id=spec.node_id,
                    state_id=snapshot.state_id,
                    bindings=candidate,
                )
                for candidate in candidates
            ]
        return []

    def _resolve_same_house_candidates(self, payload: SameHousePair, snapshot: "StateSnapshot") -> list[dict[str, Any]]:
        left_values = snapshot.values.get(payload.left_ns, {})
        right_values = snapshot.values.get(payload.right_ns, {})
        anchored_candidates: list[str] = []
        for house in payload.universe_keys:
            left_match = left_values.get(house) == payload.left_value
            right_match = right_values.get(house) == payload.right_value
            if left_match and right_match:
                return [{"house": house, "materialization_kind": "anchored"}]
            if left_match or right_match:
                anchored_candidates.append(house)
        if len(anchored_candidates) == 1:
            return [{"house": anchored_candidates[0], "materialization_kind": "anchored"}]

        from .state_graph import compute_candidate_domains

        left_domains = compute_candidate_domains(
            snapshot.values,
            payload.left_ns,
            universe_keys=payload.universe_keys,
            value_universe=(payload.left_value,),
        )
        right_domains = compute_candidate_domains(
            snapshot.values,
            payload.right_ns,
            universe_keys=payload.universe_keys,
            value_universe=(payload.right_value,),
        )
        shared_candidates = [
            house
            for house in payload.universe_keys
            if payload.left_value in left_domains["by_house"].get(house, ())
            and payload.right_value in right_domains["by_house"].get(house, ())
        ]
        if len(shared_candidates) == 1:
            return [{"house": shared_candidates[0], "materialization_kind": "anchored"}]
        if 1 < len(shared_candidates) <= self.max_branch_candidates:
            return [
                {"house": house, "materialization_kind": "domain_branch"}
                for house in shared_candidates
            ]
        return []

    def _resolve_adjacent_candidates(self, payload: AdjacentPair, snapshot: "StateSnapshot") -> list[dict[str, Any]]:
        left_candidates = self._candidate_positions(snapshot, payload.left_ns, payload.left_value)
        right_candidates = self._candidate_positions(snapshot, payload.right_ns, payload.right_value)
        left_values = snapshot.values.get(payload.left_ns, {})
        right_values = snapshot.values.get(payload.right_ns, {})
        left_known = left_values.get(payload.left_value)
        right_known = right_values.get(payload.right_value)
        if left_known is not None and right_known is not None:
            return [{"materialization_kind": "anchored"}]
        if left_known is not None:
            candidates = self._adjacent_candidates(int(left_known), right_values, payload.right_value)
            if len(candidates) == 1:
                return [{
                    "materialization_kind": "anchored",
                    "anchor_side": "left",
                    "candidate_position": candidates[0],
                }]
            if 1 < len(candidates) <= self.max_branch_candidates:
                return [
                    {
                        "materialization_kind": "domain_branch",
                        "anchor_side": "left",
                        "candidate_position": candidate,
                        "branch_id": f"{payload.right_value}-{candidate}",
                    }
                    for candidate in candidates
                ]
            return []
        if right_known is not None:
            candidates = self._adjacent_candidates(int(right_known), left_values, payload.left_value)
            if len(candidates) == 1:
                return [{
                    "materialization_kind": "anchored",
                    "anchor_side": "right",
                    "candidate_position": candidates[0],
                }]
            if 1 < len(candidates) <= self.max_branch_candidates:
                return [
                    {
                        "materialization_kind": "domain_branch",
                        "anchor_side": "right",
                        "candidate_position": candidate,
                        "branch_id": f"{payload.left_value}-{candidate}",
                    }
                    for candidate in candidates
                ]
            return []
        valid_pairs = [
            (left_position, right_position)
            for left_position in left_candidates
            for right_position in right_candidates
            if abs(left_position - right_position) == 1
        ]
        if len(valid_pairs) == 1:
            left_position, right_position = valid_pairs[0]
            return [{
                "materialization_kind": "domain_branch",
                "left_position": left_position,
                "right_position": right_position,
                "branch_id": f"{payload.left_value}-{left_position}_{payload.right_value}-{right_position}",
            }]
        if 1 < len(valid_pairs) <= self.max_branch_candidates:
            return [
                {
                    "materialization_kind": "domain_branch",
                    "left_position": left_position,
                    "right_position": right_position,
                    "branch_id": f"{payload.left_value}-{left_position}_{payload.right_value}-{right_position}",
                }
                for left_position, right_position in valid_pairs
            ]
        return []

    def _resolve_offset_candidates(self, payload: OffsetPair, snapshot: "StateSnapshot") -> list[dict[str, Any]]:
        left_candidates = self._candidate_positions(snapshot, payload.left_ns, payload.left_value)
        right_candidates = self._candidate_positions(snapshot, payload.right_ns, payload.right_value)
        left_values = snapshot.values.get(payload.left_ns, {})
        right_values = snapshot.values.get(payload.right_ns, {})
        left_known = left_values.get(payload.left_value)
        right_known = right_values.get(payload.right_value)
        if left_known is not None and right_known is not None:
            return [{"materialization_kind": "anchored"}]
        if left_known is not None:
            candidate = int(left_known) - payload.distance
            if self._position_available(candidate, right_values, payload.right_value):
                return [{
                    "materialization_kind": "anchored",
                    "anchor_side": "left",
                    "candidate_position": candidate,
                }]
            return []
        if right_known is not None:
            candidate = int(right_known) + payload.distance
            if self._position_available(candidate, left_values, payload.left_value):
                return [{
                    "materialization_kind": "anchored",
                    "anchor_side": "right",
                    "candidate_position": candidate,
                }]
            return []
        valid_pairs = [
            (right_position, left_position)
            for right_position in right_candidates
            for left_position in left_candidates
            if left_position == right_position + payload.distance
        ]
        if len(valid_pairs) == 1:
            right_position, left_position = valid_pairs[0]
            return [{
                "materialization_kind": "domain_branch",
                "left_position": left_position,
                "right_position": right_position,
                "branch_id": f"{payload.right_value}-{right_position}_{payload.left_value}-{left_position}",
            }]
        if 1 < len(valid_pairs) <= self.max_branch_candidates:
            return [
                {
                    "materialization_kind": "domain_branch",
                    "left_position": left_position,
                    "right_position": right_position,
                    "branch_id": f"{payload.right_value}-{right_position}_{payload.left_value}-{left_position}",
                }
                for right_position, left_position in valid_pairs
            ]
        return []

    def _candidate_positions(self, snapshot: "StateSnapshot", namespace: str, target_value: str) -> list[int]:
        from .state_graph import compute_candidate_domains

        namespace_values = snapshot.values.get(namespace, {})
        if isinstance(namespace_values, dict) and target_value in namespace_values:
            return [int(namespace_values[target_value])]
        if namespace.endswith("_house"):
            by_house_namespace = f"{namespace[:-6]}_by_house"
            domains = compute_candidate_domains(
                snapshot.values,
                by_house_namespace,
                universe_keys=tuple(f"house-{index}" for index in range(1, 6)),
                value_universe=(target_value,),
            )
            return [
                int(house.split("-", 1)[1])
                for house in domains["by_value"].get(target_value, ())
            ]
        return []

    def _adjacent_candidates(self, anchor: int, namespace_values: dict[str, Any], target_value: str) -> list[int]:
        occupied = {int(value) for key, value in namespace_values.items() if key != target_value}
        return [
            candidate
            for candidate in (anchor - 1, anchor + 1)
            if self._position_available(candidate, namespace_values, target_value, occupied=occupied)
        ]

    def _position_available(
        self,
        candidate: int,
        namespace_values: dict[str, Any],
        target_value: str,
        *,
        occupied: set[int] | None = None,
    ) -> bool:
        if candidate < 1 or candidate > 5:
            return False
        occupied_positions = occupied if occupied is not None else {
            int(value) for key, value in namespace_values.items() if key != target_value
        }
        return candidate not in occupied_positions


def node_instance_to_entry(spec: NodeSpec, instance: NodeInstance) -> HypothesisEntry:
    payload = spec.payload
    if isinstance(payload, SameHousePair):
        house = instance.bindings["house"]
        return HypothesisEntry(
            hypothesis_id=instance.instance_id,
            title=f"{spec.node_id} candidate at {house}",
            entrypoint=spec.entrypoint,
            related_cells=(
                f"{payload.left_cell_prefix}:{house}:{payload.left_value}",
                f"{payload.right_cell_prefix}:{house}:{payload.right_value}",
                f"relation-link:{spec.node_id}:{house}",
            ),
            tags=spec.tags,
            metadata={
                "house": house,
                "materialization_kind": instance.bindings.get("materialization_kind", "anchored"),
                "universe_keys": payload.universe_keys,
                "relation_id": spec.node_id,
                "relation_kind": "same_house_pair",
                "left": {
                    "namespace": payload.left_ns,
                    "value": payload.left_value,
                    "label": payload.left_label or payload.left_value,
                    "cell_prefix": payload.left_cell_prefix or payload.left_ns,
                },
                "right": {
                    "namespace": payload.right_ns,
                    "value": payload.right_value,
                    "label": payload.right_label or payload.right_value,
                    "cell_prefix": payload.right_cell_prefix or payload.right_ns,
                },
                "statement": payload.statement,
            },
        )
    if isinstance(payload, AdjacentPair):
        return HypothesisEntry(
            hypothesis_id=instance.instance_id,
            title=f"{spec.node_id} positional candidate",
            entrypoint=spec.entrypoint,
            related_cells=(
                f"{payload.left_cell_prefix}:{payload.left_value}",
                f"{payload.right_cell_prefix}:{payload.right_value}",
                f"relation-link:{spec.node_id}",
            ),
            tags=spec.tags,
            metadata={
                "relation_id": spec.node_id,
                "relation_kind": "adjacent_pair",
                "materialization_kind": instance.bindings.get("materialization_kind", "anchored"),
                "anchor_side": instance.bindings.get("anchor_side"),
                "candidate_position": instance.bindings.get("candidate_position"),
                "left_position": instance.bindings.get("left_position"),
                "right_position": instance.bindings.get("right_position"),
                "distance": 1,
                "left": {
                    "namespace": payload.left_ns,
                    "value": payload.left_value,
                    "label": payload.left_label or payload.left_value,
                    "cell_prefix": payload.left_cell_prefix or payload.left_ns,
                },
                "right": {
                    "namespace": payload.right_ns,
                    "value": payload.right_value,
                    "label": payload.right_label or payload.right_value,
                    "cell_prefix": payload.right_cell_prefix or payload.right_ns,
                },
                "statement": payload.statement,
            },
        )
    if isinstance(payload, OffsetPair):
        return HypothesisEntry(
            hypothesis_id=instance.instance_id,
            title=f"{spec.node_id} positional candidate",
            entrypoint=spec.entrypoint,
            related_cells=(
                f"{payload.left_cell_prefix}:{payload.left_value}",
                f"{payload.right_cell_prefix}:{payload.right_value}",
                f"relation-link:{spec.node_id}",
            ),
            tags=spec.tags,
            metadata={
                "relation_id": spec.node_id,
                "relation_kind": "offset_pair",
                "materialization_kind": instance.bindings.get("materialization_kind", "anchored"),
                "anchor_side": instance.bindings.get("anchor_side"),
                "candidate_position": instance.bindings.get("candidate_position"),
                "left_position": instance.bindings.get("left_position"),
                "right_position": instance.bindings.get("right_position"),
                "distance": payload.distance,
                "left": {
                    "namespace": payload.left_ns,
                    "value": payload.left_value,
                    "label": payload.left_label or payload.left_value,
                    "cell_prefix": payload.left_cell_prefix or payload.left_ns,
                },
                "right": {
                    "namespace": payload.right_ns,
                    "value": payload.right_value,
                    "label": payload.right_label or payload.right_value,
                    "cell_prefix": payload.right_cell_prefix or payload.right_ns,
                },
                "statement": payload.statement,
            },
        )
    raise TypeError(f"Unsupported payload type: {type(payload).__name__}")
