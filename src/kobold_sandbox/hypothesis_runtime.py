from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from .assertions import HypothesisNode, HypothesisTree
from .reactive import AtomEvaluation, AtomRuntime, ReactiveAtom


@dataclass(frozen=True)
class HypothesisCheckResult:
    hypothesis_id: str
    title: str
    passed: bool
    affected_cells: tuple[str, ...]
    related_hypothesis_ids: tuple[str, ...]
    consequences: tuple[str, ...]
    atom_results: tuple[AtomEvaluation, ...] = ()


@dataclass(frozen=True)
class HypothesisReaction:
    root_hypothesis_id: str
    checked_hypothesis_ids: tuple[str, ...]
    affected_hypothesis_ids: tuple[str, ...]
    affected_cells: tuple[str, ...]
    consequences: tuple[str, ...]
    results: tuple[HypothesisCheckResult, ...]


@dataclass(frozen=True)
class HypothesisDependencyGraph:
    adjacency: dict[str, tuple[str, ...]]
    reasons: dict[str, tuple[str, ...]] = field(default_factory=dict)

    def neighbors(self, hypothesis_id: str) -> tuple[str, ...]:
        return self.adjacency.get(hypothesis_id, ())


class HypothesisRuntime:
    def __init__(self, atom_runtime: AtomRuntime | None = None) -> None:
        self.atom_runtime = atom_runtime or AtomRuntime()

    def register_atom(self, atom: ReactiveAtom) -> ReactiveAtom:
        return self.atom_runtime.register(atom)

    def attach_atom(self, hypothesis: HypothesisNode, atom: ReactiveAtom) -> ReactiveAtom:
        registered = self.register_atom(atom)
        hypothesis.add_atom(registered.atom_id)
        return registered

    def build_dependency_graph(self, tree: HypothesisTree) -> HypothesisDependencyGraph:
        nodes = [node for node in tree.iter_nodes() if node.node_id != tree.root.node_id]
        adjacency: dict[str, set[str]] = {node.node_id: set() for node in nodes}
        reasons: dict[str, set[str]] = {}

        for node in nodes:
            for linked_id in node.related_hypothesis_ids:
                if linked_id in adjacency:
                    adjacency[node.node_id].add(linked_id)
                    adjacency[linked_id].add(node.node_id)
                    _add_reason(reasons, node.node_id, linked_id, "semantic-link")
                    _add_reason(reasons, linked_id, node.node_id, "semantic-link")

        for index, left in enumerate(nodes):
            left_vars = self._node_variables(left)
            left_terms = set(left.assumptions) | set(left.consequences)
            left_cells = set(left.related_cells)
            for right in nodes[index + 1 :]:
                relation_reasons: list[str] = []
                if left_cells & set(right.related_cells):
                    relation_reasons.append("shared-cell")
                if left_vars & self._node_variables(right):
                    relation_reasons.append("shared-variable")
                if left_terms & (set(right.assumptions) | set(right.consequences)):
                    relation_reasons.append("semantic-overlap")
                if relation_reasons:
                    adjacency[left.node_id].add(right.node_id)
                    adjacency[right.node_id].add(left.node_id)
                    _add_reason(reasons, left.node_id, right.node_id, ",".join(relation_reasons))
                    _add_reason(reasons, right.node_id, left.node_id, ",".join(relation_reasons))

        return HypothesisDependencyGraph(
            adjacency={node_id: tuple(sorted(neighbors)) for node_id, neighbors in adjacency.items()},
            reasons={key: tuple(sorted(values)) for key, values in reasons.items()},
        )

    def evaluate_connected(
        self,
        tree: HypothesisTree,
        hypothesis_id: str,
        context: dict[str, Any],
    ) -> HypothesisReaction:
        graph = self.build_dependency_graph(tree)
        component = self._component_from_graph(tree, graph, hypothesis_id)
        results: list[HypothesisCheckResult] = []
        affected_cells: list[str] = []
        affected_hypotheses: list[str] = []
        consequences: list[str] = []

        for node in component:
            atom_results = tuple(self.atom_runtime.evaluate(atom_id, context) for atom_id in node.atom_ids)
            passed = all(result.passed for result in atom_results) if atom_results else True
            if passed:
                affected_hypotheses.append(node.node_id)
                for cell in node.related_cells:
                    if cell not in affected_cells:
                        affected_cells.append(cell)
                for consequence in node.consequences:
                    if consequence not in consequences:
                        consequences.append(consequence)
            results.append(
                HypothesisCheckResult(
                    hypothesis_id=node.node_id,
                    title=node.title,
                    passed=passed,
                    affected_cells=tuple(node.related_cells),
                    related_hypothesis_ids=tuple(node.related_hypothesis_ids),
                    consequences=tuple(node.consequences),
                    atom_results=atom_results,
                )
            )

        return HypothesisReaction(
            root_hypothesis_id=hypothesis_id,
            checked_hypothesis_ids=tuple(node.node_id for node in component),
            affected_hypothesis_ids=tuple(affected_hypotheses),
            affected_cells=tuple(affected_cells),
            consequences=tuple(consequences),
            results=tuple(results),
        )

    def _component_from_graph(
        self,
        tree: HypothesisTree,
        graph: HypothesisDependencyGraph,
        hypothesis_id: str,
    ) -> list[HypothesisNode]:
        nodes = {node.node_id: node for node in tree.iter_nodes()}
        queue = [hypothesis_id]
        visited: set[str] = set()
        component: list[HypothesisNode] = []
        while queue:
            current_id = queue.pop(0)
            if current_id in visited or current_id not in nodes:
                continue
            visited.add(current_id)
            node = nodes[current_id]
            if not node.is_active:
                continue
            component.append(node)
            for neighbor_id in graph.neighbors(current_id):
                if neighbor_id not in visited:
                    queue.append(neighbor_id)
        return component

    def _node_variables(self, node: HypothesisNode) -> set[str]:
        variables: set[str] = set()
        for atom_id in node.atom_ids:
            try:
                atom = self.atom_runtime.get(atom_id)
            except KeyError:
                continue
            variables.update(atom.variables)
        return variables


def _add_reason(reasons: dict[str, set[str]], left: str, right: str, reason: str) -> None:
    key = f"{left}->{right}"
    reasons.setdefault(key, set()).add(reason)
