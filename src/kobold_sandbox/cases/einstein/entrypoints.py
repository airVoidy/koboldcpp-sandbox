from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from ...assertions import AtomicClaim, ClaimStatus, HypothesisTree
from ...core.checklist import HypothesisEntry, HypothesisResult
from ...core.structural_atoms import (
    attach_expression_atom,
    attach_position_bounds_guards,
    attach_position_uniqueness_guards,
    attach_value_uniqueness_guards,
)
from ...einstein_example import build_einstein_first_step_tree
from ...hypothesis_runtime import HypothesisRuntime
from ...outcomes import BranchOutcome, render_llm_step_output
from ...reactive import ReactiveAtom


def _attach_same_house_base_constraints(
    runtime: HypothesisRuntime,
    node,
    *,
    namespace: str,
    target_value: str,
    house: str,
) -> None:
    attach_value_uniqueness_guards(
        runtime,
        node,
        namespace=namespace,
        target_value=target_value,
        required_key=house,
    )


def _attach_positional_base_constraints(runtime: HypothesisRuntime, node, *, namespaces: tuple[str, ...]) -> None:
    for namespace in namespaces:
        attach_position_bounds_guards(runtime, node, namespace=namespace, lower=1, upper=5)
        attach_position_uniqueness_guards(runtime, node, namespace=namespace)


def _adjacent_candidates(anchor: int, namespace_values: Mapping[str, Any], target_value: str) -> list[int]:
    occupied = {int(value) for key, value in namespace_values.items() if key != target_value}
    return [
        candidate
        for candidate in (anchor - 1, anchor + 1)
        if 1 <= candidate <= 5 and candidate not in occupied
    ]


def _build_partial_positional_outcome(
    entry: HypothesisEntry,
    relation_id: str,
    relation_kind: str,
    left: Mapping[str, Any],
    right: Mapping[str, Any],
    *,
    assignments: tuple[dict[str, Any], ...],
    notes: str,
) -> HypothesisResult:
    affected_cells = tuple(
        f"{item['namespace']}:{item['key']}={item['value']}"
        for item in assignments
    )
    outcome = BranchOutcome(
        outcome_id=f"{entry.hypothesis_id}-outcome",
        branch_status="saturated",
        root_hypothesis_id=entry.hypothesis_id,
        checked_hypothesis_ids=(entry.hypothesis_id,),
        affected_hypothesis_ids=(entry.hypothesis_id,),
        affected_cells=affected_cells,
        consequences=(notes,),
        notes=notes,
    )
    worker_output = render_llm_step_output(outcome, [], include_python_block=True)
    return HypothesisResult(
        hypothesis_id=entry.hypothesis_id,
        title=entry.title,
        entrypoint=entry.entrypoint,
        status="saturated",
        passed=True,
        affected_subject_refs=outcome.affected_cells,
        derived_hypothesis_ids=outcome.checked_hypothesis_ids,
        notes=notes,
        worker_output=worker_output,
        branch_outcome=outcome,
        metadata={
            "relation_id": relation_id,
            "relation_kind": relation_kind,
            "left": dict(left),
            "right": dict(right),
            "propagation_effects": {
                "assignments": assignments,
                "eliminations": (),
            },
        },
    )


def _build_same_house_effects(
    house: str,
    left: Mapping[str, Any],
    right: Mapping[str, Any],
    *,
    universe_keys: tuple[str, ...],
) -> tuple[tuple[dict[str, Any], ...], tuple[dict[str, Any], ...]]:
    assignments = (
        {"namespace": left["namespace"], "key": house, "value": left["value"]},
        {"namespace": right["namespace"], "key": house, "value": right["value"]},
    )
    eliminations = tuple(
        {"namespace": namespace, "key": other_house, "value": target_value}
        for namespace, target_value in (
            (left["namespace"], left["value"]),
            (right["namespace"], right["value"]),
        )
        for other_house in universe_keys
        if other_house != house
    )
    return assignments, eliminations


def _build_partial_same_house_outcome(
    entry: HypothesisEntry,
    relation_id: str,
    left: Mapping[str, Any],
    right: Mapping[str, Any],
    *,
    house: str,
    universe_keys: tuple[str, ...],
    notes: str,
) -> HypothesisResult:
    assignments, eliminations = _build_same_house_effects(
        house,
        left,
        right,
        universe_keys=universe_keys,
    )
    affected_cells = tuple(
        f"{item['namespace']}:{item['key']}={item['value']}"
        for item in assignments
    )
    outcome = BranchOutcome(
        outcome_id=f"{entry.hypothesis_id}-outcome",
        branch_status="saturated",
        root_hypothesis_id=entry.hypothesis_id,
        checked_hypothesis_ids=(entry.hypothesis_id,),
        affected_hypothesis_ids=(entry.hypothesis_id,),
        affected_cells=affected_cells,
        consequences=(notes,),
        notes=notes,
    )
    worker_output = render_llm_step_output(outcome, [], include_python_block=True)
    return HypothesisResult(
        hypothesis_id=entry.hypothesis_id,
        title=entry.title,
        entrypoint=entry.entrypoint,
        status="saturated",
        passed=True,
        affected_subject_refs=outcome.affected_cells,
        derived_hypothesis_ids=outcome.checked_hypothesis_ids,
        notes=notes,
        worker_output=worker_output,
        branch_outcome=outcome,
        metadata={
            "house": house,
            "relation_id": relation_id,
            "relation_kind": "same_house_pair",
            "left": dict(left),
            "right": dict(right),
            "propagation_effects": {
                "assignments": assignments,
                "eliminations": eliminations,
            },
        },
    )


def run_first_step_hypothesis(entry: HypothesisEntry, context: Mapping[str, Any]) -> HypothesisResult:
    tree, runtime = build_einstein_first_step_tree()
    reaction = runtime.evaluate_connected(tree, entry.hypothesis_id, dict(context))
    branch_status = "saturated" if all(result.passed for result in reaction.results) else "contradicted"
    outcome = BranchOutcome.from_reaction(
        reaction,
        outcome_id=f"{entry.hypothesis_id}-outcome",
        branch_status=branch_status,
        notes=entry.metadata.get("description", ""),
    )
    worker_output = render_llm_step_output(outcome, [], include_python_block=True)
    return HypothesisResult(
        hypothesis_id=entry.hypothesis_id,
        title=entry.title,
        entrypoint=entry.entrypoint,
        status=branch_status,
        passed=branch_status != "contradicted",
        affected_subject_refs=outcome.affected_cells,
        derived_hypothesis_ids=outcome.checked_hypothesis_ids,
        notes=outcome.notes,
        worker_output=worker_output,
        branch_outcome=outcome,
        metadata={"checked_hypothesis_ids": outcome.checked_hypothesis_ids},
    )


def run_binary_relation_candidate(entry: HypothesisEntry, context: Mapping[str, Any]) -> HypothesisResult:
    house = entry.metadata["house"]
    left = entry.metadata["left"]
    right = entry.metadata["right"]
    relation_id = entry.metadata["relation_id"]
    relation_kind = entry.metadata["relation_kind"]
    materialization_kind = entry.metadata.get("materialization_kind", "anchored")
    universe_keys = tuple(entry.metadata.get("universe_keys", ()))
    if relation_kind != "same_house_pair":
        raise ValueError(f"Unsupported relation_kind: {relation_kind}")

    left_values = context.get(left["namespace"], {})
    right_values = context.get(right["namespace"], {})
    left_known = left_values.get(house) if isinstance(left_values, Mapping) else None
    right_known = right_values.get(house) if isinstance(right_values, Mapping) else None

    if left_known == left["value"] and right_known is None:
        return _build_partial_same_house_outcome(
            entry,
            relation_id,
            left,
            right,
            house=house,
            universe_keys=universe_keys,
            notes=f"Derived {right['label']} at {house} from {left['label']}.",
        )
    if right_known == right["value"] and left_known is None:
        return _build_partial_same_house_outcome(
            entry,
            relation_id,
            left,
            right,
            house=house,
            universe_keys=universe_keys,
            notes=f"Derived {left['label']} at {house} from {right['label']}.",
        )
    if materialization_kind == "domain_branch" and left_known is None and right_known is None:
        return _build_partial_same_house_outcome(
            entry,
            relation_id,
            left,
            right,
            house=house,
            universe_keys=universe_keys,
            notes=f"Branched {relation_id} into candidate {house} from candidate domains.",
        )

    tree = HypothesisTree.from_problem(f"{relation_id} {house}", title=f"{relation_id} candidate {house}")
    runtime = HypothesisRuntime()

    left_claim = AtomicClaim(
        claim_id=f"{left['value']}__{house}",
        title=f"{left['label']} at {house}",
        python_code=f"assert {left['namespace']}[{house!r}] == {left['value']!r}",
        variables=(left["namespace"],),
        status=ClaimStatus.HYPOTHESIS,
        consequences=[f"{house} satisfies {left['label']}"],
    )
    right_claim = AtomicClaim(
        claim_id=f"{house}__{right['value']}__yes",
        title=f"{right['label']} at {house}",
        python_code=f"assert {right['namespace']}[{house!r}] == {right['value']!r}",
        variables=(right["namespace"],),
        status=ClaimStatus.HYPOTHESIS,
        consequences=[f"{house} satisfies {right['label']}"],
    )

    left_node = tree.create_child(
        tree.root,
        left_claim,
        related_cells=(f"{left['cell_prefix']}:{house}:{left['value']}", f"relation-link:{relation_id}:{house}"),
    )
    right_node = tree.create_child(
        tree.root,
        right_claim,
        related_cells=(f"{right['cell_prefix']}:{house}:{right['value']}", f"relation-link:{relation_id}:{house}"),
    )
    left_node.link_hypothesis(right_node.node_id)
    right_node.link_hypothesis(left_node.node_id)
    runtime.attach_atom(left_node, ReactiveAtom.from_claim(left_claim))
    runtime.attach_atom(right_node, ReactiveAtom.from_claim(right_claim))
    _attach_same_house_base_constraints(
        runtime,
        left_node,
        namespace=left["namespace"],
        target_value=left["value"],
        house=house,
    )
    _attach_same_house_base_constraints(
        runtime,
        right_node,
        namespace=right["namespace"],
        target_value=right["value"],
        house=house,
    )

    reaction = runtime.evaluate_connected(tree, left_node.node_id, dict(context))
    branch_status = "saturated" if all(result.passed for result in reaction.results) else "contradicted"
    assignments, eliminations = (
        _build_same_house_effects(house, left, right, universe_keys=universe_keys)
        if branch_status == "saturated"
        else ((), ())
    )
    notes = (
        f"Candidate {house} satisfies relation {relation_id}."
        if branch_status == "saturated"
        else f"Collision detected for {house}: relation {relation_id} is not aligned."
    )
    outcome = BranchOutcome.from_reaction(
        reaction,
        outcome_id=f"{entry.hypothesis_id}-outcome",
        branch_status=branch_status,
        notes=notes,
    )
    worker_output = render_llm_step_output(outcome, [], include_python_block=True)
    return HypothesisResult(
        hypothesis_id=entry.hypothesis_id,
        title=entry.title,
        entrypoint=entry.entrypoint,
        status=branch_status,
        passed=branch_status != "contradicted",
        affected_subject_refs=outcome.affected_cells,
        derived_hypothesis_ids=outcome.checked_hypothesis_ids,
        notes=notes,
        worker_output=worker_output,
        branch_outcome=outcome,
        metadata={
            "house": house,
            "relation_id": relation_id,
            "relation_kind": relation_kind,
            "left": left,
            "right": right,
            "propagation_effects": {
                "assignments": assignments,
                "eliminations": eliminations,
            },
        },
    )


def run_positional_relation_candidate(entry: HypothesisEntry, context: Mapping[str, Any]) -> HypothesisResult:
    left = entry.metadata["left"]
    right = entry.metadata["right"]
    relation_id = entry.metadata["relation_id"]
    relation_kind = entry.metadata["relation_kind"]
    materialization_kind = entry.metadata.get("materialization_kind", "anchored")
    anchor_side = entry.metadata.get("anchor_side")
    candidate_position = entry.metadata.get("candidate_position")
    left_position = entry.metadata.get("left_position")
    right_position = entry.metadata.get("right_position")
    distance = int(entry.metadata.get("distance", 1))
    if relation_kind not in {"adjacent_pair", "offset_pair"}:
        raise ValueError(f"Unsupported relation_kind: {relation_kind}")

    left_values = context.get(left["namespace"], {})
    right_values = context.get(right["namespace"], {})
    left_known = left_values.get(left["value"]) if isinstance(left_values, Mapping) else None
    right_known = right_values.get(right["value"]) if isinstance(right_values, Mapping) else None

    if materialization_kind == "domain_branch" and relation_kind == "adjacent_pair" and candidate_position is not None:
        if anchor_side == "left":
            return _build_partial_positional_outcome(
                entry,
                relation_id,
                relation_kind,
                left,
                right,
                assignments=(
                    {"namespace": right["namespace"], "key": right["value"], "value": int(candidate_position)},
                ),
                notes=f"Branched {relation_id} into {right['label']}@{int(candidate_position)} from adjacent candidates.",
            )
        if anchor_side == "right":
            return _build_partial_positional_outcome(
                entry,
                relation_id,
                relation_kind,
                left,
                right,
                assignments=(
                    {"namespace": left["namespace"], "key": left["value"], "value": int(candidate_position)},
                ),
                notes=f"Branched {relation_id} into {left['label']}@{int(candidate_position)} from adjacent candidates.",
            )
    if materialization_kind == "domain_branch" and relation_kind == "adjacent_pair" and left_position is not None and right_position is not None:
        return _build_partial_positional_outcome(
            entry,
            relation_id,
            relation_kind,
            left,
            right,
            assignments=(
                {"namespace": left["namespace"], "key": left["value"], "value": int(left_position)},
                {"namespace": right["namespace"], "key": right["value"], "value": int(right_position)},
            ),
            notes=f"Branched {relation_id} into {left['label']}@{int(left_position)} and {right['label']}@{int(right_position)} from adjacent candidates.",
        )
    if materialization_kind == "domain_branch" and relation_kind == "offset_pair" and left_position is not None and right_position is not None:
        return _build_partial_positional_outcome(
            entry,
            relation_id,
            relation_kind,
            left,
            right,
            assignments=(
                {"namespace": left["namespace"], "key": left["value"], "value": int(left_position)},
                {"namespace": right["namespace"], "key": right["value"], "value": int(right_position)},
            ),
            notes=f"Branched {relation_id} into {right['label']}@{int(right_position)} and {left['label']}@{int(left_position)} from offset candidates.",
        )

    if relation_kind == "adjacent_pair" and left_known is not None and right_known is None:
        candidates = _adjacent_candidates(int(left_known), right_values if isinstance(right_values, Mapping) else {}, right["value"])
        if len(candidates) == 1:
            candidate = candidates[0]
            return _build_partial_positional_outcome(
                entry,
                relation_id,
                relation_kind,
                left,
                right,
                assignments=(
                    {"namespace": right["namespace"], "key": right["value"], "value": candidate},
                ),
                notes=f"Derived {right['label']} position {candidate} from {left['label']}.",
            )
    if relation_kind == "adjacent_pair" and right_known is not None and left_known is None:
        candidates = _adjacent_candidates(int(right_known), left_values if isinstance(left_values, Mapping) else {}, left["value"])
        if len(candidates) == 1:
            candidate = candidates[0]
            return _build_partial_positional_outcome(
                entry,
                relation_id,
                relation_kind,
                left,
                right,
                assignments=(
                    {"namespace": left["namespace"], "key": left["value"], "value": candidate},
                ),
                notes=f"Derived {left['label']} position {candidate} from {right['label']}.",
            )
    if relation_kind == "offset_pair" and left_known is not None and right_known is None:
        candidate = int(left_known) - distance
        if 1 <= candidate <= 5:
            occupied = {int(value) for key, value in right_values.items() if key != right["value"]} if isinstance(right_values, Mapping) else set()
            if candidate not in occupied:
                return _build_partial_positional_outcome(
                    entry,
                    relation_id,
                    relation_kind,
                    left,
                    right,
                    assignments=(
                        {"namespace": right["namespace"], "key": right["value"], "value": candidate},
                    ),
                    notes=f"Derived {right['label']} position {candidate} from {left['label']}.",
                )
    if relation_kind == "offset_pair" and right_known is not None and left_known is None:
        candidate = int(right_known) + distance
        if 1 <= candidate <= 5:
            occupied = {int(value) for key, value in left_values.items() if key != left["value"]} if isinstance(left_values, Mapping) else set()
            if candidate not in occupied:
                return _build_partial_positional_outcome(
                    entry,
                    relation_id,
                    relation_kind,
                    left,
                    right,
                    assignments=(
                        {"namespace": left["namespace"], "key": left["value"], "value": candidate},
                    ),
                    notes=f"Derived {left['label']} position {candidate} from {right['label']}.",
                )

    tree = HypothesisTree.from_problem(relation_id, title=f"{relation_id} positional relation")
    runtime = HypothesisRuntime()

    relation_claim = AtomicClaim(
        claim_id=relation_id,
        title=entry.title,
        variables=(left["namespace"], right["namespace"]),
        status=ClaimStatus.HYPOTHESIS,
        consequences=[f"relation {relation_id} satisfied"],
    )
    node = tree.create_child(
        tree.root,
        relation_claim,
        related_cells=(
            f"{left['cell_prefix']}:{left['value']}",
            f"{right['cell_prefix']}:{right['value']}",
            f"relation-link:{relation_id}",
        ),
    )
    if relation_kind == "adjacent_pair":
        attach_expression_atom(
            runtime,
            node,
            atom_id=relation_id,
            expression=f"assert abs({left['namespace']}[{left['value']!r}] - {right['namespace']}[{right['value']!r}]) == 1",
            variables=(left["namespace"], right["namespace"]),
        )
    else:
        attach_expression_atom(
            runtime,
            node,
            atom_id=relation_id,
            expression=f"assert {left['namespace']}[{left['value']!r}] == ({right['namespace']}[{right['value']!r}] + {distance})",
            variables=(left["namespace"], right["namespace"]),
        )
    _attach_positional_base_constraints(runtime, node, namespaces=(left["namespace"], right["namespace"]))

    reaction = runtime.evaluate_connected(tree, node.node_id, dict(context))
    branch_status = "saturated" if all(result.passed for result in reaction.results) else "contradicted"
    assignments = (
        (
            {"namespace": left["namespace"], "key": left["value"], "value": context[left["namespace"]][left["value"]]},
            {"namespace": right["namespace"], "key": right["value"], "value": context[right["namespace"]][right["value"]]},
        )
        if branch_status == "saturated"
        else ()
    )
    notes = (
        f"Positional relation {relation_id} satisfied."
        if branch_status == "saturated"
        else f"Collision detected for positional relation {relation_id}."
    )
    outcome = BranchOutcome.from_reaction(
        reaction,
        outcome_id=f"{entry.hypothesis_id}-outcome",
        branch_status=branch_status,
        notes=notes,
    )
    worker_output = render_llm_step_output(outcome, [], include_python_block=True)
    return HypothesisResult(
        hypothesis_id=entry.hypothesis_id,
        title=entry.title,
        entrypoint=entry.entrypoint,
        status=branch_status,
        passed=branch_status != "contradicted",
        affected_subject_refs=outcome.affected_cells,
        derived_hypothesis_ids=outcome.checked_hypothesis_ids,
        notes=notes,
        worker_output=worker_output,
        branch_outcome=outcome,
        metadata={
            "relation_id": relation_id,
            "relation_kind": relation_kind,
            "left": left,
            "right": right,
            "propagation_effects": {
                "assignments": assignments,
                "eliminations": (),
            },
        },
    )
