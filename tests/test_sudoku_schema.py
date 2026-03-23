from kobold_sandbox.cases.sudoku import SUDOKU_9X9_CATEGORY_ORDER, SUDOKU_9X9_SCHEMA_DATA, build_sudoku_9x9_schema
from kobold_sandbox.core import PuzzleSchema, UniversalSieveEngine

CUSTOM_SUDOKU_GRID = (
    "8........",
    "..36.....",
    ".7..9.2..",
    ".5...7...",
    "....457..",
    "...1...3.",
    "..1....68",
    "..85...1.",
    ".9....4..",
)


def test_sudoku_schema_roundtrips_basic_9x9_data() -> None:
    schema = PuzzleSchema.from_dict(SUDOKU_9X9_SCHEMA_DATA)

    assert schema.name == "Sudoku 9x9"
    assert schema.size == 81
    assert schema.categories["digit"] == tuple(str(value) for value in range(1, 10))
    assert schema.rules[0].type == "position"
    assert schema.rules[0].metadata["relation_id"] == "r1c1=5"
    assert any(rule.type == "all_different_group" and rule.metadata["relation_id"] == "row-1" for rule in schema.rules)
    assert any(rule.type == "all_different_group" and rule.metadata["relation_id"] == "box-1" for rule in schema.rules)


def test_sudoku_sieve_engine_applies_given_positions() -> None:
    schema = build_sudoku_9x9_schema()
    engine = UniversalSieveEngine(schema)
    state = engine.run_until_fixpoint()

    assert state[0]["digit"] == {"5"}
    assert state[1]["digit"] == {"3"}
    assert state[4]["digit"] == {"7"}
    assert state[9]["digit"] == {"6"}
    assert state[25]["digit"] == {"6"}
    assert "5" not in state[1]["digit"]
    assert "5" not in state[2]["digit"]
    assert "5" not in state[10]["digit"]
    assert "5" not in state[11]["digit"]


def test_sudoku_schema_declares_single_digit_axis_order() -> None:
    assert SUDOKU_9X9_CATEGORY_ORDER == ("digit",)


def test_sudoku_group_rules_reduce_candidates_in_row_column_and_box() -> None:
    schema = build_sudoku_9x9_schema()
    engine = UniversalSieveEngine(schema)
    state = engine.run_until_fixpoint()

    # r1c3 shares row with 5,3,7 and box with 5,3,6,9,8
    assert state[2]["digit"] == {"1", "2", "4"}


def test_sudoku_schema_accepts_custom_grid_rows() -> None:
    schema = build_sudoku_9x9_schema(CUSTOM_SUDOKU_GRID, name="Custom Sudoku")

    assert schema.name == "Custom Sudoku"
    assert any(rule.type == "position" and rule.metadata["relation_id"] == "r1c1=8" for rule in schema.rules)
    assert any(rule.type == "position" and rule.metadata["relation_id"] == "r8c8=1" for rule in schema.rules)
    assert any(rule.type == "position" and rule.metadata["relation_id"] == "r9c7=4" for rule in schema.rules)
