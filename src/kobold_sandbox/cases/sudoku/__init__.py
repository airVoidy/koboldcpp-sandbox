__all__ = [
    "SUDOKU_9X9_CATEGORY_ORDER",
    "SUDOKU_9X9_SCHEMA_DATA",
    "build_sudoku_9x9_schema_data",
    "build_sudoku_9x9_schema",
    "normalize_sudoku_grid",
    "SudokuHint",
    "SudokuReferenceSolution",
    "build_sudoku_reference_grid",
    "build_sudoku_sieve_state",
    "find_sudoku_forced_move",
    "render_sudoku_reference_markdown",
    "render_sudoku_sieve_markdown",
    "solve_sudoku_reference",
]


def __getattr__(name: str):
    if name in {
        "SUDOKU_9X9_CATEGORY_ORDER",
        "SUDOKU_9X9_SCHEMA_DATA",
        "build_sudoku_9x9_schema_data",
        "build_sudoku_9x9_schema",
        "normalize_sudoku_grid",
    }:
        from . import schema_data

        return getattr(schema_data, name)
    if name in {
        "SudokuHint",
        "SudokuReferenceSolution",
        "build_sudoku_reference_grid",
        "build_sudoku_sieve_state",
        "find_sudoku_forced_move",
        "render_sudoku_reference_markdown",
        "render_sudoku_sieve_markdown",
        "solve_sudoku_reference",
    }:
        from . import reference_solver

        return getattr(reference_solver, name)
    raise AttributeError(name)
