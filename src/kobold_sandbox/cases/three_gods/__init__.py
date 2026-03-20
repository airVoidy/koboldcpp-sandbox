__all__ = [
    "GODS",
    "ROLES",
    "PredicateSpec",
    "StrategyNode",
    "ThreeGodsWorld",
    "build_default_predicates",
    "generate_three_gods_worlds",
    "meta_answers",
    "render_three_gods_strategy_markdown",
    "solve_three_gods_reference",
]


def __getattr__(name: str):
    if name in __all__:
        from . import reference_solver

        return getattr(reference_solver, name)
    raise AttributeError(name)
