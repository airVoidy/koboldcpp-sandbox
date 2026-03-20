__all__ = [
    "build_einstein_schema",
    "EINSTEIN_CATEGORY_ORDER",
    "EINSTEIN_SCHEMA_DATA",
    "EinsteinReferenceSolution",
    "render_reference_solution_markdown",
    "render_reference_stage_counts",
    "run_binary_relation_candidate",
    "run_first_step_hypothesis",
    "run_positional_relation_candidate",
    "solve_einstein_reference",
    "solve_einstein_reference_staged",
]


def __getattr__(name: str):
    if name in {"run_binary_relation_candidate", "run_first_step_hypothesis", "run_positional_relation_candidate"}:
        from . import entrypoints

        return getattr(entrypoints, name)
    if name in {
        "EinsteinReferenceSolution",
        "render_reference_solution_markdown",
        "render_reference_stage_counts",
        "solve_einstein_reference",
        "solve_einstein_reference_staged",
    }:
        from . import reference_solver

        return getattr(reference_solver, name)
    if name in {"EINSTEIN_CATEGORY_ORDER", "EINSTEIN_SCHEMA_DATA", "build_einstein_schema"}:
        from . import schema_data

        return getattr(schema_data, name)
    raise AttributeError(name)
