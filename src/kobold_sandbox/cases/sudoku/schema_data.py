from __future__ import annotations

from ...core.schema_engine import PuzzleSchema

SUDOKU_9X9_CATEGORY_ORDER = ("digit",)


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

# A small starter puzzle. Position indexes are 0..80 in row-major order.
SUDOKU_9X9_SCHEMA_DATA = {
    "metadata": {
        "name": "Sudoku 9x9",
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
    "rules": [
        {
            "type": "position",
            "relation_id": "r1c1=5",
            "statement": "Cell r1c1 is 5.",
            "fact": ["digit:5", 0],
        },
        {
            "type": "position",
            "relation_id": "r1c2=3",
            "statement": "Cell r1c2 is 3.",
            "fact": ["digit:3", 1],
        },
        {
            "type": "position",
            "relation_id": "r1c5=7",
            "statement": "Cell r1c5 is 7.",
            "fact": ["digit:7", 4],
        },
        {
            "type": "position",
            "relation_id": "r2c1=6",
            "statement": "Cell r2c1 is 6.",
            "fact": ["digit:6", 9],
        },
        {
            "type": "position",
            "relation_id": "r2c4=1",
            "statement": "Cell r2c4 is 1.",
            "fact": ["digit:1", 12],
        },
        {
            "type": "position",
            "relation_id": "r2c5=9",
            "statement": "Cell r2c5 is 9.",
            "fact": ["digit:9", 13],
        },
        {
            "type": "position",
            "relation_id": "r2c6=5",
            "statement": "Cell r2c6 is 5.",
            "fact": ["digit:5", 14],
        },
        {
            "type": "position",
            "relation_id": "r3c2=9",
            "statement": "Cell r3c2 is 9.",
            "fact": ["digit:9", 19],
        },
        {
            "type": "position",
            "relation_id": "r3c3=8",
            "statement": "Cell r3c3 is 8.",
            "fact": ["digit:8", 20],
        },
        {
            "type": "position",
            "relation_id": "r3c8=6",
            "statement": "Cell r3c8 is 6.",
            "fact": ["digit:6", 25],
        },
        *_group_rules(),
    ],
}


def build_sudoku_9x9_schema() -> PuzzleSchema:
    return PuzzleSchema.from_dict(SUDOKU_9X9_SCHEMA_DATA)
