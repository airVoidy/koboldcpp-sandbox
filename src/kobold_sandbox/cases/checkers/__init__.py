__all__ = [
    "BLACK",
    "CheckersMove",
    "CheckersPosition",
    "CheckersSolveResult",
    "FILES",
    "WHITE",
    "apply_russian_checkers_move",
    "build_image_checkers_position",
    "format_square",
    "list_russian_checkers_moves",
    "next_russian_checkers_positions",
    "parse_square",
    "render_checkers_position_markdown",
    "render_checkers_solution_line_markdown",
    "render_checkers_solution_markdown",
    "solve_russian_checkers_position",
]


def __getattr__(name: str):
    if name in __all__:
        from . import reference_solver

        return getattr(reference_solver, name)
    raise AttributeError(name)
