from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from typing import Any

from .checklist import HypothesisEntry, HypothesisResult
from .hypothesis_runner import run_hypothesis_entry
from .node_specs import NodeSpec, TickPlanner, node_instance_to_entry


def _snapshot_digest(values: dict[str, dict[str, Any]], notes: tuple[str, ...]) -> str:
    payload = json.dumps({"values": values, "notes": notes}, ensure_ascii=False, sort_keys=True)
    return hashlib.sha1(payload.encode("utf-8")).hexdigest()[:12]


@dataclass(frozen=True)
class StateSnapshot:
    state_id: str
    values: dict[str, dict[str, Any]]
    notes: tuple[str, ...] = ()

    @classmethod
    def from_values(cls, values: dict[str, dict[str, Any]], *, notes: tuple[str, ...] = ()) -> "StateSnapshot":
        normalized = {key: dict(inner) for key, inner in values.items()}
        _normalize_bidirectional_assignments(normalized)
        return cls(state_id=f"state-{_snapshot_digest(normalized, notes)}", values=normalized, notes=notes)


@dataclass
class StateNode:
    node_id: str
    snapshot: StateSnapshot
    depth: int
    status: str
    derived_from_edge_id: str | None = None


@dataclass(frozen=True)
class StateEdge:
    edge_id: str
    from_node_id: str
    to_node_id: str
    hypothesis_id: str
    outcome_id: str
    status: str
    consequences: tuple[str, ...] = ()


@dataclass
class StateGraph:
    nodes: dict[str, StateNode]
    edges: dict[str, StateEdge]
    root_node_id: str

    @classmethod
    def from_snapshot(cls, snapshot: StateSnapshot) -> "StateGraph":
        root = StateNode(node_id=snapshot.state_id, snapshot=snapshot, depth=0, status="open")
        return cls(nodes={root.node_id: root}, edges={}, root_node_id=root.node_id)


def _apply_assignment(values: dict[str, dict[str, Any]], namespace: str, key: str, value: Any) -> bool:
    bucket = values.setdefault(namespace, {})
    existing = bucket.get(key)
    if existing is not None and existing != value:
        return False
    changed = existing != value
    bucket[key] = value
    if namespace.endswith("_house") and isinstance(value, int):
        by_house_namespace = f"{namespace[:-6]}_by_house"
        by_house_bucket = values.setdefault(by_house_namespace, {})
        house_key = f"house-{value}"
        existing_by_house = by_house_bucket.get(house_key)
        if existing_by_house is None or existing_by_house == key:
            changed = changed or existing_by_house != key
            by_house_bucket[house_key] = key
    elif namespace.endswith("_by_house") and isinstance(key, str) and key.startswith("house-"):
        try:
            house_index = int(key.split("-", 1)[1])
        except ValueError:
            return changed
        house_namespace = f"{namespace[:-9]}_house"
        house_bucket = values.setdefault(house_namespace, {})
        existing_house = house_bucket.get(value)
        if existing_house is None or existing_house == house_index:
            changed = changed or existing_house != house_index
            house_bucket[value] = house_index
    return changed


def _normalize_bidirectional_assignments(values: dict[str, dict[str, Any]]) -> None:
    for namespace, assignments in list(values.items()):
        if namespace in {"__eliminations__", "__universes__"} or not isinstance(assignments, dict):
            continue
        for key, value in list(assignments.items()):
            _apply_assignment(values, namespace, key, value)


def _collect_house_keys(
    assignments: dict[str, Any],
    eliminations: dict[str, list[str]],
) -> list[str]:
    house_keys = set(assignments)
    house_keys.update(eliminations)
    return sorted(house_keys, key=lambda item: int(item.split("-", 1)[1]) if item.startswith("house-") else item)


def _collect_value_universe(
    assignments: dict[str, Any],
    eliminations: dict[str, list[str]],
) -> list[str]:
    value_universe = {str(value) for value in assignments.values()}
    for removed_values in eliminations.values():
        value_universe.update(str(item) for item in removed_values)
    return sorted(value_universe)


def compute_candidate_domains(
    values: dict[str, dict[str, Any]],
    namespace: str,
    *,
    universe_keys: tuple[str, ...] | None = None,
    value_universe: tuple[str, ...] | None = None,
) -> dict[str, dict[str, tuple[str, ...]]]:
    assignments = values.get(namespace, {})
    eliminations = values.get("__eliminations__", {}).get(namespace, {})
    inverse_assignments = values.get(f"{namespace[:-9]}_house", {}) if namespace.endswith("_by_house") else {}
    if not isinstance(assignments, dict) or not isinstance(eliminations, dict) or not isinstance(inverse_assignments, dict):
        return {"by_house": {}, "by_value": {}}

    house_keys = sorted(
        {
            *_collect_house_keys(assignments, eliminations),
            *(universe_keys or ()),
        }
    )
    universe_store = values.get("__universes__", {})
    declared_universe = universe_store.get(namespace, ()) if isinstance(universe_store, dict) else ()
    value_universe = sorted(
        {
            *[str(value) for value in assignments.values()],
            *[str(value) for value in inverse_assignments.keys()],
            *[str(item) for removed_values in eliminations.values() for item in removed_values],
            *[str(item) for item in declared_universe],
            *[str(item) for item in (value_universe or ())],
        }
    )
    by_house: dict[str, tuple[str, ...]] = {}
    by_value: dict[str, tuple[str, ...]] = {}
    for house in house_keys:
        assigned = assignments.get(house)
        if assigned is not None:
            by_house[house] = (str(assigned),)
            continue
        allowed = tuple(
            value
            for value in value_universe
            if value not in eliminations.get(house, [])
            and inverse_assignments.get(value) in {None, int(house.split("-", 1)[1])}
        )
        by_house[house] = allowed
    for value in value_universe:
        assigned_house = inverse_assignments.get(value)
        if assigned_house is not None:
            by_value[value] = (f"house-{int(assigned_house)}",)
            continue
        allowed_houses = tuple(
            house
            for house, allowed_values in by_house.items()
            if value in allowed_values
        )
        by_value[value] = allowed_houses
    return {"by_house": by_house, "by_value": by_value}


def _propagate_singletons(values: dict[str, dict[str, Any]]) -> None:
    elimination_store = values.get("__eliminations__", {})
    changed = True
    while changed:
        changed = False
        for namespace, assignments in list(values.items()):
            if namespace == "__eliminations__" or not namespace.endswith("_by_house") or not isinstance(assignments, dict):
                continue
            eliminations = elimination_store.get(namespace, {})
            if not isinstance(eliminations, dict):
                continue
            house_keys = _collect_house_keys(assignments, eliminations)
            value_universe = _collect_value_universe(assignments, eliminations)
            if not house_keys or not value_universe:
                continue
            domains = compute_candidate_domains(values, namespace)
            for value, candidate_houses in domains["by_value"].items():
                if len(candidate_houses) == 1:
                    target_house = candidate_houses[0]
                    if assignments.get(target_house) != value:
                        changed = _apply_assignment(values, namespace, target_house, value) or changed

            for house, candidate_values in domains["by_house"].items():
                if assignments.get(house) is None and len(candidate_values) == 1:
                    changed = _apply_assignment(values, namespace, house, candidate_values[0]) or changed


def apply_result_to_snapshot(snapshot: StateSnapshot, result: HypothesisResult) -> StateSnapshot:
    values = {key: dict(inner) for key, inner in snapshot.values.items()}
    metadata = result.metadata
    effects = metadata.get("propagation_effects", {}) if result.passed else {}
    for item in effects.get("assignments", ()):
        _apply_assignment(values, item["namespace"], item["key"], item["value"])
    if effects.get("eliminations"):
        elimination_store = values.setdefault("__eliminations__", {})
        for item in effects["eliminations"]:
            bucket = elimination_store.setdefault(item["namespace"], {})
            current = set(bucket.get(item["key"], ()))
            current.add(item["value"])
            bucket[item["key"]] = sorted(current)
    _propagate_singletons(values)
    notes = snapshot.notes + ((result.notes,) if result.notes else ())
    return StateSnapshot.from_values(values, notes=notes)


def expand_state_node(
    graph: StateGraph,
    node_id: str,
    entries: list[HypothesisEntry],
    *,
    max_depth: int,
) -> list[str]:
    node = graph.nodes[node_id]
    if node.depth >= max_depth:
        return []
    created_or_touched: list[str] = []
    for entry in entries:
        result = run_hypothesis_entry(entry, node.snapshot.values)
        edge_id = f"{node_id}->{entry.hypothesis_id}"
        if result.passed:
            next_snapshot = apply_result_to_snapshot(node.snapshot, result)
            if next_snapshot.values == node.snapshot.values:
                to_node_id = node_id
            else:
                to_node_id = next_snapshot.state_id
                if to_node_id not in graph.nodes:
                    graph.nodes[to_node_id] = StateNode(
                        node_id=to_node_id,
                        snapshot=next_snapshot,
                        depth=node.depth + 1,
                        status="open",
                        derived_from_edge_id=edge_id,
                    )
                created_or_touched.append(to_node_id)
        else:
            to_node_id = node_id
        graph.edges[edge_id] = StateEdge(
            edge_id=edge_id,
            from_node_id=node_id,
            to_node_id=to_node_id,
            hypothesis_id=entry.hypothesis_id,
            outcome_id=(result.branch_outcome.outcome_id if result.branch_outcome else f"{entry.hypothesis_id}-outcome"),
            status=result.status,
            consequences=(result.branch_outcome.consequences if result.branch_outcome else ()),
        )
    return created_or_touched


def expand_state_sequence(
    graph: StateGraph,
    start_node_id: str,
    entries: list[HypothesisEntry],
    *,
    max_depth: int,
) -> list[str]:
    frontier = [start_node_id]
    visited_nodes: list[str] = []
    for entry in entries:
        next_frontier: list[str] = []
        for node_id in frontier:
            created = expand_state_node(graph, node_id, [entry], max_depth=max_depth)
            next_frontier.extend(created)
        if not next_frontier:
            break
        visited_nodes.extend(next_frontier)
        frontier = next_frontier
    return visited_nodes




def choose_best_search_spec(
    planner: TickPlanner,
    specs: list[NodeSpec],
    snapshot: StateSnapshot,
    *,
    consumed_spec_ids: set[str] | None = None,
) -> tuple[NodeSpec | None, list[HypothesisEntry]]:
    consumed = consumed_spec_ids if consumed_spec_ids is not None else set()
    best_spec: NodeSpec | None = None
    best_entries: list[HypothesisEntry] = []
    for spec in specs:
        if spec.node_id in consumed:
            continue
        instances = planner.materialize(spec, snapshot)
        if not instances:
            continue
        entries = [node_instance_to_entry(spec, instance) for instance in instances]
        if best_spec is None or len(entries) < len(best_entries):
            best_spec = spec
            best_entries = entries
            if len(best_entries) == 1:
                break
    return best_spec, best_entries


def choose_best_branch_spec(
    planner: TickPlanner,
    specs: list[NodeSpec],
    snapshot: StateSnapshot,
    *,
    attempted_state_specs: set[tuple[str, str]] | None = None,
) -> tuple[NodeSpec | None, list[HypothesisEntry]]:
    attempted = attempted_state_specs if attempted_state_specs is not None else set()
    best_spec: NodeSpec | None = None
    best_entries: list[HypothesisEntry] = []
    for spec in specs:
        if (snapshot.state_id, spec.node_id) in attempted:
            continue
        instances = planner.materialize(spec, snapshot)
        if len(instances) <= 1:
            continue
        entries = [node_instance_to_entry(spec, instance) for instance in instances]
        if best_spec is None or len(entries) < len(best_entries):
            best_spec = spec
            best_entries = entries
    return best_spec, best_entries


def propagate_until_fixpoint(
    graph: StateGraph,
    start_node_id: str,
    planner: TickPlanner,
    specs: list[NodeSpec],
    *,
    max_depth: int,
    attempted_state_specs: set[tuple[str, str]] | None = None,
) -> tuple[str, list[tuple[str, list[str]]], str]:
    attempted = attempted_state_specs if attempted_state_specs is not None else set()
    current_node_id = start_node_id
    events: list[tuple[str, list[str]]] = []
    while True:
        node = graph.nodes[current_node_id]
        if node.depth >= max_depth:
            return current_node_id, events, "max_depth"
        progressed = False
        for spec in specs:
            signature = (current_node_id, spec.node_id)
            if signature in attempted:
                continue
            instances = planner.materialize(spec, node.snapshot)
            if len(instances) != 1:
                continue
            attempted.add(signature)
            entry = node_instance_to_entry(spec, instances[0])
            created = expand_state_node(graph, current_node_id, [entry], max_depth=max_depth)
            events.append((spec.node_id, created))
            if created:
                next_node_id = created[0]
                if next_node_id != current_node_id:
                    current_node_id = next_node_id
                    progressed = True
                    break
        if not progressed:
            return current_node_id, events, "fixpoint"


def branch_on_best_unresolved(
    graph: StateGraph,
    node_id: str,
    planner: TickPlanner,
    specs: list[NodeSpec],
    *,
    max_depth: int,
    attempted_state_specs: set[tuple[str, str]] | None = None,
) -> tuple[str | None, list[str]]:
    node = graph.nodes[node_id]
    attempted = attempted_state_specs if attempted_state_specs is not None else set()
    best_spec, entries = choose_best_branch_spec(
        planner,
        specs,
        node.snapshot,
        attempted_state_specs=attempted,
    )
    if best_spec is None:
        return None, []
    attempted.add((node_id, best_spec.node_id))
    created = expand_state_node(graph, node_id, entries, max_depth=max_depth)
    return best_spec.node_id, created


def search_step(
    graph: StateGraph,
    node_id: str,
    planner: TickPlanner,
    specs: list[NodeSpec],
    *,
    max_depth: int,
    consumed_spec_ids: set[str] | None = None,
) -> tuple[str | None, list[str]]:
    node = graph.nodes[node_id]
    best_spec, entries = choose_best_search_spec(
        planner,
        specs,
        node.snapshot,
        consumed_spec_ids=consumed_spec_ids,
    )
    if best_spec is None:
        return None, []
    created = expand_state_node(graph, node_id, entries, max_depth=max_depth)
    consumed = consumed_spec_ids if consumed_spec_ids is not None else set()
    consumed.add(best_spec.node_id)
    return best_spec.node_id, created


def search_n(
    graph: StateGraph,
    start_node_id: str,
    planner: TickPlanner,
    specs: list[NodeSpec],
    *,
    max_depth: int,
    steps: int,
    consumed_spec_ids: set[str] | None = None,
) -> list[tuple[str, list[str]]]:
    current_node_id = start_node_id
    events: list[tuple[str, list[str]]] = []
    for _ in range(steps):
        spec_id, created = search_step(
            graph,
            current_node_id,
            planner,
            specs,
            max_depth=max_depth,
            consumed_spec_ids=consumed_spec_ids,
        )
        if spec_id is None:
            break
        events.append((spec_id, created))
        if created:
            current_node_id = created[0]
    return events


def search_until_blocked(
    graph: StateGraph,
    start_node_id: str,
    planner: TickPlanner,
    specs: list[NodeSpec],
    *,
    max_depth: int,
    consumed_spec_ids: set[str] | None = None,
) -> tuple[list[tuple[str, list[str]]], str]:
    consumed = consumed_spec_ids if consumed_spec_ids is not None else set()
    remaining_specs = [spec for spec in specs if spec.node_id not in consumed]
    events = search_n(
        graph,
        start_node_id,
        planner,
        specs,
        max_depth=max_depth,
        steps=len(remaining_specs),
        consumed_spec_ids=consumed,
    )
    if len(events) == len(remaining_specs):
        return events, "exhausted"
    return events, "blocked"


def tick_once(
    graph: StateGraph,
    node_id: str,
    planner: TickPlanner,
    specs: list[NodeSpec],
    *,
    max_depth: int,
    consumed_spec_ids: set[str] | None = None,
) -> tuple[str | None, list[str]]:
    node = graph.nodes[node_id]
    consumed = consumed_spec_ids if consumed_spec_ids is not None else set()
    for spec in specs:
        if spec.node_id in consumed:
            continue
        instances = planner.materialize(spec, node.snapshot)
        if not instances:
            continue
        entries = [node_instance_to_entry(spec, instance) for instance in instances]
        created = expand_state_node(graph, node_id, entries, max_depth=max_depth)
        consumed.add(spec.node_id)
        return spec.node_id, created
    return None, []


def tick_n(
    graph: StateGraph,
    start_node_id: str,
    planner: TickPlanner,
    specs: list[NodeSpec],
    *,
    max_depth: int,
    steps: int,
    consumed_spec_ids: set[str] | None = None,
) -> list[tuple[str, list[str]]]:
    current_node_id = start_node_id
    events: list[tuple[str, list[str]]] = []
    for _ in range(steps):
        spec_id, created = tick_once(
            graph,
            current_node_id,
            planner,
            specs,
            max_depth=max_depth,
            consumed_spec_ids=consumed_spec_ids,
        )
        if spec_id is None:
            break
        events.append((spec_id, created))
        if created:
            current_node_id = created[0]
    return events


def tick_until_blocked(
    graph: StateGraph,
    start_node_id: str,
    planner: TickPlanner,
    specs: list[NodeSpec],
    *,
    max_depth: int,
    consumed_spec_ids: set[str] | None = None,
) -> tuple[list[tuple[str, list[str]]], str]:
    consumed = consumed_spec_ids if consumed_spec_ids is not None else set()
    remaining_specs = [spec for spec in specs if spec.node_id not in consumed]
    events = tick_n(
        graph,
        start_node_id,
        planner,
        specs,
        max_depth=max_depth,
        steps=len(remaining_specs),
        consumed_spec_ids=consumed,
    )
    if len(events) == len(remaining_specs):
        return events, "exhausted"
    return events, "blocked"
