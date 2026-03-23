from __future__ import annotations

from collections.abc import Sequence

from ...core.schema_engine import PuzzleSchema

SUDOKU_9X9_CATEGORY_ORDER = ("digit",)
DEFAULT_SUDOKU_REFERENCE_GRID = (
    "530070000",
    "600195000",
    "098000060",
    "000000000",
    "000000000",
    "000000000",
    "000000000",
    "000000000",
    "000000000",
)


def _row_positions(row_index: int) -> list[int]:
    start = row_index * 9
    return list(range(start, start + 9))


def _col_positions(col_index: int) -> list[int]:
    return [row * 9 + col_index for row in range(9)]


def _box_positions(box_row: int, box_col: int) -> list[int]:
    positions: list[int] = []
    row_start = box_row * 3
    col_start = box_col * 3
    for row in range(row_start, row_start + 3):
        for col in range(col_start, col_start + 3):
            positions.append(row * 9 + col)
    return positions


def _group_rules() -> list[dict[str, object]]:
    rules: list[dict[str, object]] = []
    for row_index in range(9):
        rules.append(
            {
                "type": "all_different_group",
                "relation_id": f"row-{row_index + 1}",
                "statement": f"Row {row_index + 1} contains digits 1..9 without repetition.",
                "fact": ["digit", *_row_positions(row_index)],
            }
        )
    for col_index in range(9):
        rules.append(
            {
                "type": "all_different_group",
                "relation_id": f"col-{col_index + 1}",
                "statement": f"Column {col_index + 1} contains digits 1..9 without repetition.",
                "fact": ["digit", *_col_positions(col_index)],
            }
        )
    for box_row in range(3):
        for box_col in range(3):
            box_index = box_row * 3 + box_col + 1
            rules.append(
                {
                    "type": "all_different_group",
                    "relation_id": f"box-{box_index}",
                    "statement": f"Box {box_index} contains digits 1..9 without repetition.",
                    "fact": ["digit", *_box_positions(box_row, box_col)],
                }
            )
    return rules

def normalize_sudoku_grid(grid: Sequence[str] | None = None) -> tuple[str, ...]:
    raw_values = tuple(DEFAULT_SUDOKU_REFERENCE_GRID if grid is None else tuple(str(item).strip() for item in grid))
    if len(raw_values) == 9 and all(len(value) == 9 for value in raw_values):
        cells = tuple(cell for row in raw_values for cell in row)
    elif len(raw_values) == 81 and all(len(value) == 1 for value in raw_values):
        cells = raw_values
    else:
        raise ValueError("Sudoku grid must be 9 row strings or 81 single-cell values.")

    normalized: list[str] = []
    for value in cells:
        if value == ".":
            normalized.append("0")
            continue
        if value in {"0", "1", "2", "3", "4", "5", "6", "7", "8", "9"}:
            normalized.append(value)
            continue
        raise ValueError(f"Unsupported sudoku cell value: {value!r}")
    return tuple(normalized)


def build_sudoku_9x9_schema_data(
    grid: Sequence[str] | None = None,
    *,
    name: str = "Sudoku 9x9",
) -> dict[str, object]:
    givens = normalize_sudoku_grid(grid)
    rules: list[dict[str, object]] = []
    for index, value in enumerate(givens):
        if value == "0":
            continue
        row_index = index // 9 + 1
        col_index = index % 9 + 1
        rules.append(
            {
                "type": "position",
                "relation_id": f"r{row_index}c{col_index}={value}",
                "statement": f"Cell r{row_index}c{col_index} is {value}.",
                "fact": [f"digit:{value}", index],
            }
        )
    rules.extend(_group_rules())
    return {
        "metadata": {
            "name": name,
            "size": 81,
            "repeated_categories": ["digit"],
            "layout": {
                "kind": "grid",
                "rows": 9,
                "cols": 9,
                "box_rows": 3,
                "box_cols": 3,
            },
        },
        "categories": {
            "digit": [str(value) for value in range(1, 10)],
        },
        "rules": rules,
    }


SUDOKU_9X9_SCHEMA_DATA = build_sudoku_9x9_schema_data()


def build_sudoku_9x9_schema(
    grid: Sequence[str] | None = None,
    *,
    name: str = "Sudoku 9x9",
) -> PuzzleSchema:
    return PuzzleSchema.from_dict(build_sudoku_9x9_schema_data(grid, name=name))
