from __future__ import annotations

from ..hypothesis_runtime import HypothesisRuntime
from ..reactive import ReactiveAtom


def attach_expression_atom(
    runtime: HypothesisRuntime,
    node,
    *,
    atom_id: str,
    expression: str,
    variables: tuple[str, ...],
) -> None:
    runtime.attach_atom(
        node,
        ReactiveAtom(
            atom_id=atom_id,
            expression=expression,
            variables=variables,
        ),
    )


def attach_value_uniqueness_guards(
    runtime: HypothesisRuntime,
    node,
    *,
    namespace: str,
    target_value: str,
    required_key: str | None = None,
) -> None:
    attach_expression_atom(
        runtime,
        node,
        atom_id=f"{node.node_id}-{namespace}-{target_value}-unique",
        expression=f"assert sum(1 for value in {namespace}.values() if value == {target_value!r}) <= 1",
        variables=(namespace,),
    )
    if required_key is not None:
        attach_expression_atom(
            runtime,
            node,
            atom_id=f"{node.node_id}-{namespace}-{required_key}-present",
            expression=f"assert {required_key!r} in {namespace}",
            variables=(namespace,),
        )


def attach_position_bounds_guards(
    runtime: HypothesisRuntime,
    node,
    *,
    namespace: str,
    lower: int,
    upper: int,
) -> None:
    attach_expression_atom(
        runtime,
        node,
        atom_id=f"{node.node_id}-{namespace}-bounds",
        expression=f"assert all({lower} <= value <= {upper} for value in {namespace}.values())",
        variables=(namespace,),
    )


def attach_position_uniqueness_guards(
    runtime: HypothesisRuntime,
    node,
    *,
    namespace: str,
) -> None:
    attach_expression_atom(
        runtime,
        node,
        atom_id=f"{node.node_id}-{namespace}-unique",
        expression=f"assert len(set({namespace}.values())) == len({namespace}.values())",
        variables=(namespace,),
    )
