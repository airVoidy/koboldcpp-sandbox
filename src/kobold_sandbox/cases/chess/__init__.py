__all__ = [
    "BLACK",
    "ChessMove",
    "ChessPhase1Result",
    "ChessPhase2Candidate",
    "ChessPhase2Result",
    "ChessPhase3CandidateResult",
    "ChessPhase3Result",
    "ChessStockfishCandidateResult",
    "ChessStockfishBeamResult",
    "ChessStockfishTreeResult",
    "ChessPosition",
    "ChessSolveResult",
    "FILES",
    "PIECE_SYMBOLS",
    "WHITE",
    "apply_chess_move",
    "build_image_chess_position",
    "chess_position_to_fen",
    "find_stockfish_binary",
    "format_square",
    "list_chess_moves",
    "parse_square",
    "render_chess_position_markdown",
    "render_chess_phase_breakdown_markdown",
    "render_chess_solution_line_markdown",
    "render_chess_solution_markdown",
    "solve_chess_phase1_prefix",
    "solve_chess_phase2_preparation",
    "solve_chess_phase3_candidates",
    "solve_chess_phase3_position",
    "solve_chess_phase3_candidates_with_stockfish",
    "solve_chess_phase3_beam_with_stockfish",
    "solve_chess_phase3_tree_with_stockfish",
    "solve_chess_position",
]


def __getattr__(name: str):
    if name in __all__:
        from . import reference_solver

        return getattr(reference_solver, name)
    raise AttributeError(name)
