from __future__ import annotations

from dataclasses import dataclass

from .hypothesis_runner import run_hypothesis_entry
from .node_specs import NodeSpec, TickPlanner, node_instance_to_entry
from .state_graph import StateGraph, StateNode, apply_result_to_snapshot


@dataclass(frozen=True)
class DecisionNode:
    decision_id: str
    state_node_id: str
    spec_id: str
    branch_instance_ids: tuple[str, ...]
    branch_group_id: str | None
    exclusion_group_id: str | None
    status: str


@dataclass(frozen=True)
class DecisionEdge:
    edge_id: str
    decision_id: str
    branch_instance_id: str
    hypothesis_id: str
    to_state_id: str
    status: str


@dataclass
class DecisionTree:
    decisions: dict[str, DecisionNode]
    edges: dict[str, DecisionEdge]

    @classmethod
    def empty(cls) -> "DecisionTree":
        return cls(decisions={}, edges={})


def render_decision_tree_markdown(tree: DecisionTree) -> str:
    lines = [
        "| decision_id | state_node_id | spec_id | branch_group | exclusion_group | status | branches |",
        "| --- | --- | --- | --- | --- | --- | --- |",
    ]
    for decision in sorted(tree.decisions.values(), key=lambda item: item.decision_id):
        branches = ", ".join(decision.branch_instance_ids)
        lines.append(
            f"| {decision.decision_id} | {decision.state_node_id} | {decision.spec_id} | {decision.branch_group_id or '-'} | {decision.exclusion_group_id or '-'} | {decision.status} | {branches} |"
        )
    lines.append("")
    lines.extend(
        [
            "| edge_id | decision_id | branch_instance_id | hypothesis_id | status | to_state_id |",
            "| --- | --- | --- | --- | --- | --- |",
        ]
    )
    for edge in sorted(tree.edges.values(), key=lambda item: item.edge_id):
        lines.append(
            f"| {edge.edge_id} | {edge.decision_id} | {edge.branch_instance_id} | {edge.hypothesis_id} | {edge.status} | {edge.to_state_id} |"
        )
    return "\n".join(lines)


def expand_decision_spec(
    tree: DecisionTree,
    graph: StateGraph,
    state_node_id: str,
    planner: TickPlanner,
    spec: NodeSpec,
    *,
    max_depth: int,
    branch_group_id: str | None = None,
    exclusion_group_id: str | None = None,
) -> tuple[DecisionNode | None, list[str]]:
    state_node = graph.nodes[state_node_id]
    if state_node.depth >= max_depth:
        return None, []
    instances = planner.materialize(spec, state_node.snapshot)
    if len(instances) < 2:
        return None, []

    decision_id = f"{state_node_id}::{spec.node_id}"
    branch_ids = tuple(instance.instance_id for instance in instances)
    decision = DecisionNode(
        decision_id=decision_id,
        state_node_id=state_node_id,
        spec_id=spec.node_id,
        branch_instance_ids=branch_ids,
        branch_group_id=branch_group_id,
        exclusion_group_id=exclusion_group_id,
        status="open",
    )
    tree.decisions[decision_id] = decision

    created_or_touched: list[str] = []
    for instance in instances:
        entry = node_instance_to_entry(spec, instance)
        result = run_hypothesis_entry(entry, state_node.snapshot.values)
        if result.passed:
            next_snapshot = apply_result_to_snapshot(state_node.snapshot, result)
            to_state_id = next_snapshot.state_id
            if to_state_id not in graph.nodes:
                graph.nodes[to_state_id] = StateNode(
                    node_id=to_state_id,
                    snapshot=next_snapshot,
                    depth=state_node.depth + 1,
                    status="open",
                    derived_from_edge_id=f"{decision_id}->{instance.instance_id}",
                )
            created_or_touched.append(to_state_id)
        else:
            to_state_id = state_node_id

        edge_id = f"{decision_id}->{instance.instance_id}"
        tree.edges[edge_id] = DecisionEdge(
            edge_id=edge_id,
            decision_id=decision_id,
            branch_instance_id=instance.instance_id,
            hypothesis_id=entry.hypothesis_id,
            to_state_id=to_state_id,
            status=result.status,
        )

    tree.decisions[decision_id] = DecisionNode(
        decision_id=decision.decision_id,
        state_node_id=decision.state_node_id,
        spec_id=decision.spec_id,
        branch_instance_ids=decision.branch_instance_ids,
        branch_group_id=decision.branch_group_id,
        exclusion_group_id=decision.exclusion_group_id,
        status="branched" if created_or_touched else "contradicted",
    )
    return tree.decisions[decision_id], created_or_touched


def reconcile_decision_branch(
    tree: DecisionTree,
    decision_id: str,
    accepted_branch_instance_id: str,
) -> None:
    decision = tree.decisions[decision_id]
    if accepted_branch_instance_id not in decision.branch_instance_ids:
        raise KeyError(accepted_branch_instance_id)
    for edge_id, edge in list(tree.edges.items()):
        if edge.decision_id != decision_id:
            continue
        if edge.branch_instance_id == accepted_branch_instance_id:
            continue
        tree.edges[edge_id] = DecisionEdge(
            edge_id=edge.edge_id,
            decision_id=edge.decision_id,
            branch_instance_id=edge.branch_instance_id,
            hypothesis_id=edge.hypothesis_id,
            to_state_id=edge.to_state_id,
            status="excluded",
        )
    tree.decisions[decision_id] = DecisionNode(
        decision_id=decision.decision_id,
        state_node_id=decision.state_node_id,
        spec_id=decision.spec_id,
        branch_instance_ids=decision.branch_instance_ids,
        branch_group_id=decision.branch_group_id,
        exclusion_group_id=decision.exclusion_group_id,
        status="reconciled",
    )


def auto_reconcile_single_survivor(tree: DecisionTree, decision_id: str) -> str | None:
    decision = tree.decisions[decision_id]
    surviving = [
        edge.branch_instance_id
        for edge in tree.edges.values()
        if edge.decision_id == decision_id and edge.status not in {"contradicted", "excluded"}
    ]
    if len(surviving) != 1:
        return None
    reconcile_decision_branch(tree, decision_id, surviving[0])
    return surviving[0]
