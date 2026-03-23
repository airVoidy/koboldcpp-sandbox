from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass

from ...core import UniversalSieveEngine
from .schema_data import build_sudoku_9x9_schema, normalize_sudoku_grid


def _row(index: int) -> int:
    return index // 9


def _col(index: int) -> int:
    return index % 9


def _box(index: int) -> int:
    return (_row(index) // 3) * 3 + (_col(index) // 3)


@dataclass(frozen=True)
class SudokuReferenceSolution:
    cells: tuple[str, ...]

    def rows(self) -> list[tuple[str, ...]]:
        return [self.cells[row * 9 : (row + 1) * 9] for row in range(9)]


@dataclass(frozen=True)
class SudokuHint:
    index: int
    row: int
    col: int
    candidates: tuple[str, ...]

    @property
    def cell_id(self) -> str:
        return f"r{self.row}c{self.col}"


def build_sudoku_reference_grid() -> list[str]:
    return list(normalize_sudoku_grid())


def _is_safe(grid: list[str], index: int, value: str) -> bool:
    row = _row(index)
    col = _col(index)
    box = _box(index)
    for other_index, other_value in enumerate(grid):
        if other_value == "0":
            continue
        if other_index != index and other_value == value:
            if _row(other_index) == row or _col(other_index) == col or _box(other_index) == box:
                return False
    return True


def solve_sudoku_reference(grid: Sequence[str] | None = None) -> SudokuReferenceSolution:
    working = list(normalize_sudoku_grid(grid))

    def backtrack() -> bool:
        try:
            index = working.index("0")
        except ValueError:
            return True

        for value in map(str, range(1, 10)):
            if _is_safe(working, index, value):
                working[index] = value
                if backtrack():
                    return True
                working[index] = "0"
        return False

    if not backtrack():
        raise RuntimeError("Sudoku reference solver found no solution.")
    return SudokuReferenceSolution(cells=tuple(working))


def render_sudoku_reference_markdown(
    solution: SudokuReferenceSolution | None = None,
    *,
    grid: Sequence[str] | None = None,
    title: str = "# Sudoku Reference Solution",
) -> str:
    solved = solution or solve_sudoku_reference(grid)
    lines = [
        title,
        "",
        "| r/c | c1 | c2 | c3 | c4 | c5 | c6 | c7 | c8 | c9 |",
        "| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |",
    ]
    for row_index, row in enumerate(solved.rows(), start=1):
        lines.append(f"| r{row_index} | " + " | ".join(row) + " |")
    return "\n".join(lines)


def build_sudoku_sieve_state(
    grid: Sequence[str] | None = None,
    *,
    name: str = "Sudoku 9x9",
) -> list[dict[str, set[str]]]:
    schema = build_sudoku_9x9_schema(grid, name=name)
    engine = UniversalSieveEngine(schema)
    return engine.run_until_fixpoint()


def find_sudoku_forced_move(
    state: list[dict[str, set[str]]] | None = None,
    *,
    grid: Sequence[str] | None = None,
) -> SudokuHint | None:
    current = state or build_sudoku_sieve_state(grid)
    best_index: int | None = None
    best_candidates: tuple[str, ...] | None = None
    for index, house in enumerate(current):
        candidates = tuple(sorted(house["digit"]))
        if len(candidates) <= 1:
            continue
        if best_candidates is None or len(candidates) < len(best_candidates):
            best_index = index
            best_candidates = candidates
    if best_index is None or best_candidates is None:
        return None
    return SudokuHint(
        index=best_index,
        row=_row(best_index) + 1,
        col=_col(best_index) + 1,
        candidates=best_candidates,
    )


def render_sudoku_sieve_markdown(
    state: list[dict[str, set[str]]] | None = None,
    *,
    grid: Sequence[str] | None = None,
    title: str = "# Sudoku Sieve State",
) -> str:
    current = state or build_sudoku_sieve_state(grid)
    lines = [
        title,
        "",
        "| r/c | c1 | c2 | c3 | c4 | c5 | c6 | c7 | c8 | c9 |",
        "| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |",
    ]
    for row_index in range(9):
        cells: list[str] = []
        for col_index in range(9):
            index = row_index * 9 + col_index
            cells.append("".join(sorted(current[index]["digit"])))
        lines.append(f"| r{row_index + 1} | " + " | ".join(cells) + " |")
    hint = find_sudoku_forced_move(current)
    if hint is not None:
        lines.extend(
            [
                "",
                "## Next Hint",
                "",
                f"- cell: `{hint.cell_id}`",
                f"- candidates: `{', '.join(hint.candidates)}`",
            ]
        )
    return "\n".join(lines)
