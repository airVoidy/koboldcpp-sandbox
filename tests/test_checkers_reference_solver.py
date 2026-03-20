from kobold_sandbox.cases.checkers import (
    WHITE,
    apply_russian_checkers_move,
    build_image_checkers_position,
    list_russian_checkers_moves,
    render_checkers_position_markdown,
    render_checkers_solution_markdown,
    solve_russian_checkers_position,
)


def test_image_checkers_position_parses_expected_pieces() -> None:
    position = build_image_checkers_position()

    assert position.white_men == ("c1", "e1", "h4")
    assert position.black_men == ("a3", "a5", "h6")
    assert position.white_kings == ()
    assert position.black_kings == ()


def test_russian_checkers_opening_moves_from_image_position() -> None:
    position = build_image_checkers_position()
    moves = list_russian_checkers_moves(position, WHITE)

    assert [move.notation() for move in moves] == [
        "c1-b2",
        "c1-d2",
        "e1-d2",
        "e1-f2",
        "h4-g5",
    ]


def test_checkers_position_markdown_renders_board() -> None:
    markdown = render_checkers_position_markdown()

    assert "# Checkers Position" in markdown
    assert "| r/c | a | b | c | d | e | f | g | h |" in markdown
    assert "| 6 | . | . | . | . | . | . | . | b |" in markdown
    assert "| 4 | . | . | . | . | . | . | . | w |" in markdown


def test_apply_russian_checkers_move_updates_position() -> None:
    position = build_image_checkers_position()
    move = list_russian_checkers_moves(position, WHITE)[-1]

    next_position = apply_russian_checkers_move(position, move, WHITE)

    assert move.notation() == "h4-g5"
    assert next_position.white_men == ("c1", "e1", "g5")
    assert next_position.black_men == ("a3", "a5", "h6")


def test_solve_russian_checkers_position_returns_stable_result() -> None:
    result = solve_russian_checkers_position(build_image_checkers_position(), WHITE)

    assert result.outcome in {"win", "loss", "draw"}
    assert result.reachable_states > 0
    assert result.best_moves
    assert result.best_line
    assert result.best_moves[0] == result.best_line[0]


def test_checkers_solution_markdown_contains_solver_summary() -> None:
    markdown = render_checkers_solution_markdown()

    assert "## Solve Result" in markdown
    assert "- `outcome`:" in markdown
    assert "- `best_moves`:" in markdown
    assert "- `best_line`:" in markdown
    assert "### 1. white:" in markdown
