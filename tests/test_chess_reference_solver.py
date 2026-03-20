from kobold_sandbox.cases.chess import (
    WHITE,
    build_image_chess_position,
    chess_position_to_fen,
    find_stockfish_binary,
    list_chess_moves,
    render_chess_phase_breakdown_markdown,
    render_chess_position_markdown,
    render_chess_solution_markdown,
    solve_chess_phase1_prefix,
    solve_chess_phase2_preparation,
    solve_chess_phase3_candidates,
    solve_chess_phase3_candidates_with_stockfish,
    solve_chess_phase3_beam_with_stockfish,
    solve_chess_phase3_tree_with_stockfish,
    solve_chess_position,
)


def test_image_chess_position_parses_expected_pieces() -> None:
    position = build_image_chess_position()
    board = position.board_map()

    assert board["h1"] == "K"
    assert board["h8"] == "k"
    assert board["a4"] == "P"
    assert board["h7"] == "p"


def test_chess_opening_moves_from_image_position() -> None:
    moves = [move.notation() for move in list_chess_moves(build_image_chess_position(), WHITE)]

    assert "h1-g1" in moves
    assert "h1-g2" in moves
    assert "a4-a5" in moves
    assert "b4-b5" in moves
    assert "c4-c5" in moves


def test_chess_position_markdown_renders_unicode_board() -> None:
    markdown = render_chess_position_markdown()

    assert "# Chess Position" in markdown
    assert "♔" in markdown
    assert "♚" in markdown
    assert "♙" in markdown
    assert "♟" in markdown


def test_solve_chess_position_returns_stable_result() -> None:
    result = solve_chess_position(build_image_chess_position(), WHITE)

    assert result.outcome in {"win", "loss", "draw"}
    assert result.reachable_states > 0
    assert isinstance(result.best_moves, tuple)
    assert isinstance(result.best_line, tuple)


def test_chess_solution_markdown_contains_solver_summary() -> None:
    markdown = render_chess_solution_markdown()

    assert "## Solve Result" in markdown
    assert "- `best_line`:" in markdown
    assert "- `terminal_promotion`:" in markdown


def test_chess_phase_breakdown_builds_prefix_and_prep_position() -> None:
    phase1 = solve_chess_phase1_prefix(build_image_chess_position(), WHITE)
    phase2 = solve_chess_phase2_preparation(phase1)

    assert phase1.prefix_line
    assert phase1.runner_square == "a5"
    assert phase1.promotion_square == "a8"
    assert phase1.black_prep_moves == 2
    assert phase2.candidates
    assert phase2.recommended_index == 0
    assert isinstance(phase2.candidates[0].prep_line, tuple)
    assert phase2.candidates[0].side_to_move in {"w", "b"}
    assert isinstance(phase2.candidates[0].immediate_mate, bool)
    assert phase2.candidates[0].survival_moves >= 0


def test_chess_phase_breakdown_markdown_contains_sections() -> None:
    markdown = render_chess_phase_breakdown_markdown()

    assert "## Phase 1" in markdown
    assert "## Phase 2" in markdown
    assert "## Phase 3" in markdown
    assert "- `promotion_square`: `a8`" in markdown
    assert "- `candidate_count`:" in markdown
    assert "- `immediate_mate`:" in markdown
    assert "### All Candidates" in markdown


def test_chess_phase3_candidates_rank_finishes() -> None:
    phase1 = solve_chess_phase1_prefix(build_image_chess_position(), WHITE)
    phase2 = solve_chess_phase2_preparation(phase1)
    phase3 = solve_chess_phase3_candidates(phase2, max_depth=2)

    assert phase3
    assert phase3[0].candidate_index >= 0
    assert phase3[0].result.outcome in {"win", "draw", "loss", "unknown"}
    assert isinstance(phase3[0].result.exact, bool)


def test_chess_position_can_render_fen() -> None:
    fen = chess_position_to_fen(build_image_chess_position(), WHITE)

    assert fen.startswith("7k/5ppp/ppp5/8/PPP5/8/8/7K w")


def test_chess_stockfish_backend_smoke() -> None:
    binary = find_stockfish_binary()
    assert binary is not None

    phase1 = solve_chess_phase1_prefix(build_image_chess_position(), WHITE)
    phase2 = solve_chess_phase2_preparation(phase1)
    phase3 = solve_chess_phase3_candidates_with_stockfish(phase2, depth=10, engine_path=binary)

    assert phase3
    assert phase3[0].evaluation_type in {"cp", "mate"}


def test_chess_stockfish_tree_backend_smoke() -> None:
    binary = find_stockfish_binary()
    assert binary is not None

    phase1 = solve_chess_phase1_prefix(build_image_chess_position(), WHITE)
    phase2 = solve_chess_phase2_preparation(phase1)
    phase3 = solve_chess_phase3_tree_with_stockfish(phase2, depth=8, top_k=2, reply_k=2, plies=2, engine_path=binary)

    assert phase3
    assert isinstance(phase3[0].line, tuple)


def test_chess_stockfish_beam_backend_smoke() -> None:
    binary = find_stockfish_binary()
    assert binary is not None

    phase1 = solve_chess_phase1_prefix(build_image_chess_position(), WHITE)
    phase2 = solve_chess_phase2_preparation(phase1)
    phase3 = solve_chess_phase3_beam_with_stockfish(phase2, depth=8, top_k=2, beam_width=8, plies=2, engine_path=binary)

    assert phase3
    assert phase3[0].explored_nodes > 0
