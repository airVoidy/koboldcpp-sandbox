from kobold_sandbox.cases.sudoku import (
    build_sudoku_sieve_state,
    build_sudoku_reference_grid,
    find_sudoku_forced_move,
    render_sudoku_reference_markdown,
    render_sudoku_sieve_markdown,
    solve_sudoku_reference,
)

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


def test_sudoku_reference_grid_contains_expected_givens() -> None:
    grid = build_sudoku_reference_grid()

    assert grid[0] == "5"
    assert grid[1] == "3"
    assert grid[4] == "7"
    assert grid[9] == "6"
    assert grid[12] == "1"
    assert grid[25] == "6"


def test_sudoku_reference_solver_finds_complete_solution() -> None:
    solution = solve_sudoku_reference()
    rows = solution.rows()

    assert rows[0] == ("5", "3", "1", "6", "7", "8", "2", "4", "9")
    assert rows[1] == ("6", "2", "4", "1", "9", "5", "3", "7", "8")
    assert rows[2] == ("7", "9", "8", "2", "3", "4", "1", "6", "5")
    assert rows[0][0] == "5"
    assert rows[0][1] == "3"
    assert rows[0][4] == "7"
    assert rows[1][0] == "6"
    assert rows[1][3] == "1"
    assert rows[2][7] == "6"


def test_sudoku_reference_markdown_renders_grid() -> None:
    markdown = render_sudoku_reference_markdown()

    assert "# Sudoku Reference Solution" in markdown
    assert "| r/c | c1 | c2 | c3 | c4 | c5 | c6 | c7 | c8 | c9 |" in markdown
    assert "| r1 | 5 | 3 | 1 | 6 | 7 | 8 | 2 | 4 | 9 |" in markdown


def test_sudoku_sieve_state_and_hint_expose_candidate_domains() -> None:
    state = build_sudoku_sieve_state()
    hint = find_sudoku_forced_move(state)

    assert state[2]["digit"] == {"1", "2", "4"}
    assert hint is not None
    assert hint.cell_id == "r1c3"
    assert hint.candidates == ("1", "2", "4")


def test_sudoku_sieve_markdown_renders_domains_and_hint() -> None:
    markdown = render_sudoku_sieve_markdown()

    assert "# Sudoku Sieve State" in markdown
    assert "| r1 | 5 | 3 | 124 | 2468 | 7 | 2468 | 12489 | 12489 | 12489 |" in markdown
    assert "## Next Hint" in markdown
    assert "- cell: `r1c3`" in markdown


def test_sudoku_reference_solver_accepts_custom_row_strings() -> None:
    solution = solve_sudoku_reference(CUSTOM_SUDOKU_GRID)
    rows = solution.rows()

    assert rows[0] == ("8", "1", "2", "7", "5", "3", "6", "4", "9")
    assert rows[7] == ("4", "3", "8", "5", "2", "6", "9", "1", "7")
    assert rows[8] == ("7", "9", "6", "3", "1", "8", "4", "5", "2")


def test_sudoku_sieve_state_supports_custom_grid_override() -> None:
    state = build_sudoku_sieve_state(CUSTOM_SUDOKU_GRID)
    hint = find_sudoku_forced_move(state)

    assert state[0]["digit"] == {"8"}
    assert state[69]["digit"] == {"3", "9"}
    assert hint is not None
    assert hint.cell_id == "r8c7"
    assert hint.candidates == ("3", "9")
