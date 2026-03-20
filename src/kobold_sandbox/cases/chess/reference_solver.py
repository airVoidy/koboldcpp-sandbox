from __future__ import annotations

import os
import shutil
from dataclasses import dataclass

FILES = "abcdefgh"
RANKS = "12345678"
WHITE = "w"
BLACK = "b"
PIECE_SYMBOLS = {
    "K": "♔",
    "Q": "♕",
    "R": "♖",
    "B": "♗",
    "N": "♘",
    "P": "♙",
    "k": "♚",
    "q": "♛",
    "r": "♜",
    "b": "♝",
    "n": "♞",
    "p": "♟",
}


@dataclass(frozen=True)
class ChessMove:
    from_square: str
    to_square: str
    promotion: str | None = None

    def notation(self) -> str:
        if self.promotion:
            return f"{self.from_square}-{self.to_square}={self.promotion.upper()}"
        return f"{self.from_square}-{self.to_square}"


@dataclass(frozen=True)
class ChessPosition:
    pieces: tuple[tuple[str, str], ...]

    def board_map(self) -> dict[str, str]:
        return dict(self.pieces)


@dataclass(frozen=True)
class ChessSolveResult:
    outcome: str
    best_moves: tuple[str, ...]
    best_line: tuple[str, ...]
    reachable_states: int


@dataclass(frozen=True)
class ChessPhase1Result:
    prefix_line: tuple[str, ...]
    position: ChessPosition
    side_to_move: str
    runner_square: str
    promotion_square: str
    black_prep_moves: int


@dataclass(frozen=True)
class ChessPhase2Candidate:
    prep_line: tuple[str, ...]
    start_position: ChessPosition
    side_to_move: str
    promotion_square: str
    heuristic: int
    immediate_mate: bool
    survival_moves: int


@dataclass(frozen=True)
class ChessPhase2Result:
    candidates: tuple[ChessPhase2Candidate, ...]
    recommended_index: int


@dataclass(frozen=True)
class ChessPhase3Result:
    outcome: str
    score: int
    depth: int
    best_line: tuple[str, ...]
    exact: bool


@dataclass(frozen=True)
class ChessPhase3CandidateResult:
    candidate_index: int
    prep_line: tuple[str, ...]
    result: ChessPhase3Result


@dataclass(frozen=True)
class ChessStockfishCandidateResult:
    candidate_index: int
    prep_line: tuple[str, ...]
    fen: str
    best_move: str | None
    evaluation_type: str
    evaluation_value: int
    black_score: int
    wdl: tuple[int, int, int]
    black_wdl_score: int


@dataclass(frozen=True)
class ChessStockfishTreeResult:
    candidate_index: int
    prep_line: tuple[str, ...]
    black_score: int
    line: tuple[str, ...]
    leaf_fen: str
    leaf_eval_type: str
    leaf_eval_value: int
    leaf_wdl: tuple[int, int, int]
    black_wdl_score: int


@dataclass(frozen=True)
class ChessStockfishBeamResult:
    candidate_index: int
    prep_line: tuple[str, ...]
    black_score: int
    line: tuple[str, ...]
    leaf_fen: str
    leaf_eval_type: str
    leaf_eval_value: int
    explored_nodes: int
    leaf_wdl: tuple[int, int, int]
    black_wdl_score: int


def parse_square(square: str) -> tuple[int, int]:
    return FILES.index(square[0]), RANKS.index(square[1])


def format_square(cell: tuple[int, int]) -> str:
    return f"{FILES[cell[0]]}{RANKS[cell[1]]}"


def build_image_chess_position() -> ChessPosition:
    pieces = {
        "h1": "K",
        "a4": "P",
        "b4": "P",
        "c4": "P",
        "h8": "k",
        "a6": "p",
        "b6": "p",
        "c6": "p",
        "f7": "p",
        "g7": "p",
        "h7": "p",
    }
    return ChessPosition(tuple(sorted(pieces.items())))


def list_chess_moves(position: ChessPosition, side: str = WHITE) -> list[ChessMove]:
    board = position.board_map()
    moves: list[ChessMove] = []
    for square, piece in board.items():
        if _piece_color(piece) != side:
            continue
        moves.extend(_piece_moves(board, square, piece))
    legal: list[ChessMove] = []
    for move in moves:
        next_position = apply_chess_move(position, move)
        if not is_in_check(next_position, side):
            legal.append(move)
    return sorted(legal, key=lambda move: move.notation())


def apply_chess_move(position: ChessPosition, move: ChessMove) -> ChessPosition:
    board = dict(position.board_map())
    piece = board.pop(move.from_square)
    board.pop(move.to_square, None)
    board[move.to_square] = _promoted_piece(piece, move.promotion)
    return ChessPosition(tuple(sorted(board.items())))


def solve_chess_position(position: ChessPosition, side: str = WHITE) -> ChessSolveResult:
    cache: dict[tuple[ChessPosition, str], tuple[int, int, tuple[str, ...]]] = {}

    def better_line(candidate_score: int, candidate_plies: int, best_score: int, best_plies: int) -> bool:
        if candidate_score != best_score:
            return candidate_score > best_score
        if candidate_score == 1:
            return candidate_plies < best_plies
        if candidate_score == -1:
            return candidate_plies > best_plies
        return candidate_plies > best_plies

    def solve_node(current_position: ChessPosition, current_side: str) -> tuple[int, int, tuple[str, ...]]:
        node = (current_position, current_side)
        if node in cache:
            return cache[node]
        winner = _promotion_winner(current_position)
        if winner is not None:
            result = (1 if winner == current_side else -1, 0, ())
            cache[node] = result
            return result
        moves = _pawn_race_moves(current_position, current_side)
        if not moves:
            result = (0, 0, ())
            cache[node] = result
            return result
        next_side = BLACK if current_side == WHITE else WHITE
        best_score = -2
        best_plies = -1
        best_line: tuple[str, ...] = ()
        for move in moves:
            child = apply_chess_move(current_position, move)
            child_score, child_plies, child_line = solve_node(child, next_side)
            score = -child_score
            plies = child_plies + 1
            if better_line(score, plies, best_score, best_plies):
                best_score = score
                best_plies = plies
                best_line = (move.notation(),) + child_line
        result = (best_score, best_plies, best_line)
        cache[node] = result
        return result

    score, _plies, line = solve_node(position, side)
    outcome = {1: "win", 0: "draw", -1: "loss"}.get(score, "draw")
    best_moves = tuple(line[:1]) if line else tuple(move.notation() for move in _pawn_race_moves(position, side))
    return ChessSolveResult(
        outcome=outcome,
        best_moves=best_moves,
        best_line=line,
        reachable_states=len(cache),
    )


def solve_chess_phase1_prefix(position: ChessPosition | None = None, side: str = WHITE) -> ChessPhase1Result:
    current = position or build_image_chess_position()
    result = solve_chess_position(current, side)
    running = current
    current_side = side
    prefix: list[str] = []
    for notation in result.best_line:
        move = _find_move_by_notation(running, current_side, notation)
        running = apply_chess_move(running, move)
        prefix.append(notation)
        current_side = BLACK if current_side == WHITE else WHITE
        runner_square = _first_passed_pawn_square(running, WHITE)
        if runner_square is not None:
            promotion_square = f"{runner_square[0]}8"
            black_prep_moves = 8 - int(runner_square[1]) - (1 if current_side == BLACK else 0)
            return ChessPhase1Result(
                prefix_line=tuple(prefix),
                position=running,
                side_to_move=current_side,
                runner_square=runner_square,
                promotion_square=promotion_square,
                black_prep_moves=max(0, black_prep_moves),
            )
    raise ValueError("white passed pawn prefix was not found")


def solve_chess_phase2_preparation(phase1: ChessPhase1Result) -> ChessPhase2Result:
    leaves: list[ChessPhase2Candidate] = []

    def prep_heuristic(position: ChessPosition) -> int:
        board = position.board_map()
        tx, ty = parse_square(phase1.promotion_square)
        score = 0
        for square, piece in board.items():
            x, y = parse_square(square)
            if piece == "p":
                score += (7 - y) * 10
                if abs(x - tx) <= 1:
                    score += 6
            elif piece == "k":
                score -= abs(tx - x) + abs(ty - y)
        return score

    def walk(position: ChessPosition, side: str, black_moves_left: int, line: tuple[str, ...]) -> None:
        if _promotion_winner(position) == WHITE:
            leaves.append(
                ChessPhase2Candidate(
                    prep_line=line,
                    start_position=position,
                    side_to_move=side,
                    promotion_square=phase1.promotion_square,
                    heuristic=prep_heuristic(position),
                    immediate_mate=_is_immediate_mate_candidate(position, side),
                    survival_moves=_count_survival_moves(position, side),
                )
            )
            return
        if side == WHITE:
            move = _forced_runner_move(position, phase1.runner_square)
            if move is None:
                leaves.append(
                    ChessPhase2Candidate(
                        prep_line=line,
                        start_position=position,
                        side_to_move=side,
                        promotion_square=phase1.promotion_square,
                        heuristic=prep_heuristic(position),
                        immediate_mate=_is_immediate_mate_candidate(position, side),
                        survival_moves=_count_survival_moves(position, side),
                    )
                )
                return
            child = apply_chess_move(position, move)
            walk(child, BLACK, black_moves_left, line + (move.notation(),))
            return
        if black_moves_left <= 0:
            leaves.append(
                ChessPhase2Candidate(
                    prep_line=line,
                    start_position=position,
                    side_to_move=side,
                    promotion_square=phase1.promotion_square,
                    heuristic=prep_heuristic(position),
                    immediate_mate=_is_immediate_mate_candidate(position, side),
                    survival_moves=_count_survival_moves(position, side),
                )
            )
            return
        for move in list_chess_moves(position, BLACK):
            child = apply_chess_move(position, move)
            walk(child, WHITE, black_moves_left - 1, line + (move.notation(),))

    walk(phase1.position, phase1.side_to_move, phase1.black_prep_moves, ())
    ordered = tuple(
        sorted(
            leaves,
            key=lambda item: (
                item.immediate_mate,
                -item.survival_moves,
                -item.heuristic,
                item.prep_line,
            ),
        )
    )
    unique_candidates: list[ChessPhase2Candidate] = []
    seen_positions: set[ChessPosition] = set()
    for candidate in ordered:
        if candidate.immediate_mate or candidate.start_position in seen_positions:
            continue
        seen_positions.add(candidate.start_position)
        unique_candidates.append(candidate)
    candidates = tuple(unique_candidates)
    return ChessPhase2Result(
        candidates=candidates,
        recommended_index=0 if candidates else -1,
    )


def solve_chess_phase3_position(
    position: ChessPosition,
    side: str,
    max_depth: int = 6,
) -> ChessPhase3Result:
    cache: dict[tuple[ChessPosition, str, int], tuple[int, tuple[str, ...], bool]] = {}

    def evaluate(current_position: ChessPosition) -> int:
        board = current_position.board_map()
        score = 0
        for square, piece in board.items():
            if piece == "p":
                x, y = parse_square(square)
                score += (7 - y) * 30
                if _is_passed_black_pawn(board, square):
                    score += 80
                if _is_adjacent_to_black_king(board, square):
                    score += 35
                if _is_safe_white_capture_target(board, square):
                    score -= 70
                if x in {0, 7}:
                    score += 10
            elif piece == "q":
                score += 5000
            elif piece == "Q":
                score -= 400
        black_king = next((sq for sq, piece in board.items() if piece == "k"), None)
        if black_king is not None:
            if is_in_check(current_position, BLACK):
                score -= 150
            score += len(list_chess_moves(current_position, BLACK)) * 3
        return score

    def solve_node(current_position: ChessPosition, current_side: str, depth: int) -> tuple[int, tuple[str, ...], bool]:
        key = (current_position, current_side, depth)
        if key in cache:
            return cache[key]
        board = current_position.board_map()
        if "q" in board.values():
            result = (100000 - (max_depth - depth), (), True)
            cache[key] = result
            return result
        if all(piece != "p" for piece in board.values()):
            result = (-100000 + (max_depth - depth), (), True)
            cache[key] = result
            return result
        legal = _phase3_moves(current_position, current_side)
        enemy = BLACK if current_side == WHITE else WHITE
        if not legal:
            if is_in_check(current_position, current_side):
                result = (100000 - (max_depth - depth), (), True) if current_side == WHITE else (-100000 + (max_depth - depth), (), True)
            else:
                result = (0, (), True)
            cache[key] = result
            return result
        if depth == 0:
            result = (evaluate(current_position), (), False)
            cache[key] = result
            return result

        best_score = -10**9 if current_side == BLACK else 10**9
        best_line: tuple[str, ...] = ()
        best_exact = True
        for move in legal:
            child = apply_chess_move(current_position, move)
            child_score, child_line, child_exact = solve_node(child, enemy, depth - 1)
            candidate_line = (move.notation(),) + child_line
            if current_side == BLACK:
                if child_score > best_score or (child_score == best_score and len(candidate_line) < len(best_line or candidate_line + ("",))):
                    best_score = child_score
                    best_line = candidate_line
                    best_exact = child_exact
            else:
                if child_score < best_score or (child_score == best_score and len(candidate_line) < len(best_line or candidate_line + ("",))):
                    best_score = child_score
                    best_line = candidate_line
                    best_exact = child_exact
        result = (best_score, best_line, best_exact)
        cache[key] = result
        return result

    score, line, exact = solve_node(position, side, max_depth)
    if exact and score >= 100000 - max_depth:
        outcome = "win"
    elif exact and score <= -100000 + max_depth:
        outcome = "loss"
    elif exact and score == 0:
        outcome = "draw"
    else:
        outcome = "unknown"
    return ChessPhase3Result(outcome=outcome, score=score, depth=max_depth, best_line=line, exact=exact)


def solve_chess_phase3_candidates(
    phase2: ChessPhase2Result,
    max_depth: int = 4,
) -> tuple[ChessPhase3CandidateResult, ...]:
    results = [
        ChessPhase3CandidateResult(
            candidate_index=index,
            prep_line=candidate.prep_line,
            result=solve_chess_phase3_position(candidate.start_position, candidate.side_to_move, max_depth=max_depth),
        )
        for index, candidate in enumerate(phase2.candidates)
    ]
    return tuple(
        sorted(
            results,
            key=lambda item: (
                -item.result.score,
                len(item.result.best_line),
                item.candidate_index,
            ),
        )
    )


def find_stockfish_binary() -> str | None:
    candidates = (
        os.path.join(os.getcwd(), "tools", "stockfish", "stockfish", "stockfish-windows-x86-64-avx2.exe"),
        os.path.join(os.getcwd(), "tools", "stockfish", "stockfish.exe"),
        "stockfish",
    )
    for candidate in candidates:
        if os.path.isfile(candidate):
            return candidate
        if candidate == "stockfish":
            resolved = shutil.which(candidate)
            if resolved:
                return resolved
    return None


def chess_position_to_fen(position: ChessPosition, side: str) -> str:
    board = position.board_map()
    rows: list[str] = []
    for rank in range(8, 0, -1):
        empty = 0
        parts: list[str] = []
        for file_index in range(8):
            square = f"{FILES[file_index]}{rank}"
            piece = board.get(square)
            if piece is None:
                empty += 1
                continue
            if empty:
                parts.append(str(empty))
                empty = 0
            parts.append(piece)
        if empty:
            parts.append(str(empty))
        rows.append("".join(parts) or "8")
    return f"{'/'.join(rows)} {'w' if side == WHITE else 'b'} - - 0 1"


def solve_chess_phase3_candidates_with_stockfish(
    phase2: ChessPhase2Result,
    depth: int = 12,
    engine_path: str | None = None,
) -> tuple[ChessStockfishCandidateResult, ...]:
    from stockfish import Stockfish

    binary = engine_path or find_stockfish_binary()
    if binary is None:
        raise FileNotFoundError("stockfish binary not found")
    engine = Stockfish(path=binary, depth=depth, turn_perspective=False)

    def eval_black(fen: str) -> tuple[int, str, int, tuple[int, int, int], int]:
        engine.set_fen_position(fen)
        evaluation = engine.get_evaluation()
        wdl_raw = engine.get_wdl_stats()
        wdl = tuple(int(x) for x in wdl_raw) if wdl_raw is not None else (0, 1000, 0)
        value = int(evaluation["value"])
        black_score = -value if evaluation["type"] == "cp" else value
        black_wdl_score = wdl[2] - wdl[0]
        return black_score, str(evaluation["type"]), value, wdl, black_wdl_score

    results: list[ChessStockfishCandidateResult] = []
    try:
        for index, candidate in enumerate(phase2.candidates):
            fen = chess_position_to_fen(candidate.start_position, candidate.side_to_move)
            black_score, evaluation_type, value, wdl, black_wdl_score = eval_black(fen)
            engine.set_fen_position(fen)
            results.append(
                ChessStockfishCandidateResult(
                    candidate_index=index,
                    prep_line=candidate.prep_line,
                    fen=fen,
                    best_move=engine.get_best_move(),
                    evaluation_type=evaluation_type,
                    evaluation_value=value,
                    black_score=black_score,
                    wdl=wdl,
                    black_wdl_score=black_wdl_score,
                )
            )
    finally:
        engine.send_quit_command()
    return tuple(
        sorted(
            results,
            key=lambda item: (-item.black_wdl_score, -item.black_score, item.candidate_index),
        )
    )


def solve_chess_phase3_tree_with_stockfish(
    phase2: ChessPhase2Result,
    depth: int = 10,
    top_k: int = 5,
    reply_k: int = 3,
    plies: int = 4,
    engine_path: str | None = None,
) -> tuple[ChessStockfishTreeResult, ...]:
    from stockfish import Stockfish

    binary = engine_path or find_stockfish_binary()
    if binary is None:
        raise FileNotFoundError("stockfish binary not found")
    engine = Stockfish(path=binary, depth=depth, turn_perspective=False)

    def eval_black(fen: str) -> tuple[int, str, int, tuple[int, int, int], int]:
        engine.set_fen_position(fen)
        evaluation = engine.get_evaluation()
        wdl_raw = engine.get_wdl_stats()
        wdl = tuple(int(x) for x in wdl_raw) if wdl_raw is not None else (0, 1000, 0)
        value = int(evaluation["value"])
        black_score = -value if evaluation["type"] == "cp" else value
        black_wdl_score = wdl[2] - wdl[0]
        return black_score, str(evaluation["type"]), value, wdl, black_wdl_score

    def search(position: ChessPosition, side: str, remaining_plies: int) -> tuple[int, tuple[str, ...], str, str, int, tuple[int, int, int], int]:
        fen = chess_position_to_fen(position, side)
        score, eval_type, eval_value, wdl, black_wdl_score = eval_black(fen)
        if remaining_plies <= 0:
            return score, (), fen, eval_type, eval_value, wdl, black_wdl_score

        top_moves = engine.get_top_moves(top_k if side == BLACK else reply_k)
        if not top_moves:
            return score, (), fen, eval_type, eval_value, wdl, black_wdl_score

        best_score = -10**9 if side == BLACK else 10**9
        best_line: tuple[str, ...] = ()
        best_fen = fen
        best_eval_type = eval_type
        best_eval_value = eval_value
        best_wdl = wdl
        best_black_wdl_score = black_wdl_score
        next_side = WHITE if side == BLACK else BLACK

        for item in top_moves:
            move_uci = str(item["Move"])
            move = _uci_to_move(move_uci)
            if move is None:
                continue
            legal = list_chess_moves(position, side)
            matching = next((candidate for candidate in legal if candidate.notation().replace("-", "").replace("=", "").lower() == move_uci.lower()), None)
            move = matching or move
            if move not in legal:
                continue
            child = apply_chess_move(position, move)
            child_score, child_line, child_fen, child_eval_type, child_eval_value, child_wdl, child_black_wdl_score = search(child, next_side, remaining_plies - 1)
            candidate_line = (move.notation(),) + child_line
            if side == BLACK:
                if (child_black_wdl_score, child_score) > (best_black_wdl_score, best_score):
                    best_score = child_score
                    best_line = candidate_line
                    best_fen = child_fen
                    best_eval_type = child_eval_type
                    best_eval_value = child_eval_value
                    best_wdl = child_wdl
                    best_black_wdl_score = child_black_wdl_score
            else:
                if (child_black_wdl_score, child_score) < (best_black_wdl_score, best_score):
                    best_score = child_score
                    best_line = candidate_line
                    best_fen = child_fen
                    best_eval_type = child_eval_type
                    best_eval_value = child_eval_value
                    best_wdl = child_wdl
                    best_black_wdl_score = child_black_wdl_score
        if best_score == (-10**9 if side == BLACK else 10**9):
            return score, (), fen, eval_type, eval_value, wdl, black_wdl_score
        return best_score, best_line, best_fen, best_eval_type, best_eval_value, best_wdl, best_black_wdl_score

    results: list[ChessStockfishTreeResult] = []
    try:
        for index, candidate in enumerate(phase2.candidates):
            score, line, leaf_fen, eval_type, eval_value, leaf_wdl, black_wdl_score = search(candidate.start_position, candidate.side_to_move, plies)
            results.append(
                ChessStockfishTreeResult(
                    candidate_index=index,
                    prep_line=candidate.prep_line,
                    black_score=score,
                    line=line,
                    leaf_fen=leaf_fen,
                    leaf_eval_type=eval_type,
                    leaf_eval_value=eval_value,
                    leaf_wdl=leaf_wdl,
                    black_wdl_score=black_wdl_score,
                )
            )
    finally:
        engine.send_quit_command()

    return tuple(sorted(results, key=lambda item: (-item.black_wdl_score, -item.black_score, item.candidate_index)))


def solve_chess_phase3_beam_with_stockfish(
    phase2: ChessPhase2Result,
    depth: int = 10,
    top_k: int = 4,
    beam_width: int = 128,
    plies: int = 6,
    engine_path: str | None = None,
) -> tuple[ChessStockfishBeamResult, ...]:
    from stockfish import Stockfish

    @dataclass(frozen=True)
    class BeamNode:
        position: ChessPosition
        side: str
        line: tuple[str, ...]
        black_score: int
        black_wdl_score: int
        fen: str
        eval_type: str
        eval_value: int
        wdl: tuple[int, int, int]

    binary = engine_path or find_stockfish_binary()
    if binary is None:
        raise FileNotFoundError("stockfish binary not found")
    engine = Stockfish(path=binary, depth=depth, turn_perspective=False)

    def eval_black(fen: str) -> tuple[int, str, int, tuple[int, int, int], int]:
        engine.set_fen_position(fen)
        evaluation = engine.get_evaluation()
        wdl_raw = engine.get_wdl_stats()
        wdl = tuple(int(x) for x in wdl_raw) if wdl_raw is not None else (0, 1000, 0)
        value = int(evaluation["value"])
        black_score = -value if evaluation["type"] == "cp" else value
        black_wdl_score = wdl[2] - wdl[0]
        return black_score, str(evaluation["type"]), value, wdl, black_wdl_score

    def expand_node(node: BeamNode) -> list[BeamNode]:
        engine.set_fen_position(node.fen)
        top_moves = engine.get_top_moves(top_k)
        if not top_moves:
            return []
        legal = list_chess_moves(node.position, node.side)
        children: list[BeamNode] = []
        next_side = WHITE if node.side == BLACK else BLACK
        for item in top_moves:
            move = _uci_to_move(str(item["Move"]))
            if move is None:
                continue
            matching = next(
                (
                    candidate
                    for candidate in legal
                    if candidate.from_square == move.from_square
                    and candidate.to_square == move.to_square
                    and (candidate.promotion or None) == (move.promotion or None)
                ),
                None,
            )
            if matching is None:
                continue
            child = apply_chess_move(node.position, matching)
            fen = chess_position_to_fen(child, next_side)
            black_score, eval_type, eval_value, wdl, black_wdl_score = eval_black(fen)
            children.append(
                BeamNode(
                    position=child,
                    side=next_side,
                    line=node.line + (matching.notation(),),
                    black_score=black_score,
                    black_wdl_score=black_wdl_score,
                    fen=fen,
                    eval_type=eval_type,
                    eval_value=eval_value,
                    wdl=wdl,
                )
            )
        return children

    results: list[ChessStockfishBeamResult] = []
    try:
        for index, candidate in enumerate(phase2.candidates):
            root_fen = chess_position_to_fen(candidate.start_position, candidate.side_to_move)
            root_score, root_eval_type, root_eval_value, root_wdl, root_black_wdl_score = eval_black(root_fen)
            frontier = [
                BeamNode(
                    position=candidate.start_position,
                    side=candidate.side_to_move,
                    line=(),
                    black_score=root_score,
                    black_wdl_score=root_black_wdl_score,
                    fen=root_fen,
                    eval_type=root_eval_type,
                    eval_value=root_eval_value,
                    wdl=root_wdl,
                )
            ]
            explored_nodes = 1
            for ply in range(plies):
                expanded: list[BeamNode] = []
                for node in frontier:
                    children = expand_node(node)
                    explored_nodes += len(children)
                    expanded.extend(children)
                if not expanded:
                    break
                next_side = expanded[0].side
                expanded.sort(
                    key=lambda item: (
                        item.black_wdl_score if next_side == BLACK else -item.black_wdl_score,
                        item.black_score if next_side == BLACK else -item.black_score,
                        -len(item.line),
                    ),
                    reverse=True,
                )
                frontier = expanded[:beam_width]
            if not frontier:
                frontier = [
                    BeamNode(
                        position=candidate.start_position,
                        side=candidate.side_to_move,
                        line=(),
                        black_score=root_score,
                        black_wdl_score=root_black_wdl_score,
                        fen=root_fen,
                        eval_type=root_eval_type,
                        eval_value=root_eval_value,
                        wdl=root_wdl,
                    )
                ]
            best = max(frontier, key=lambda item: (item.black_wdl_score, item.black_score))
            results.append(
                ChessStockfishBeamResult(
                    candidate_index=index,
                    prep_line=candidate.prep_line,
                    black_score=best.black_score,
                    line=best.line,
                    leaf_fen=best.fen,
                    leaf_eval_type=best.eval_type,
                    leaf_eval_value=best.eval_value,
                    explored_nodes=explored_nodes,
                    leaf_wdl=best.wdl,
                    black_wdl_score=best.black_wdl_score,
                )
            )
    finally:
        engine.send_quit_command()

    return tuple(sorted(results, key=lambda item: (-item.black_wdl_score, -item.black_score, item.candidate_index)))


def render_chess_position_markdown(position: ChessPosition | None = None) -> str:
    current = position or build_image_chess_position()
    board = current.board_map()
    lines = [
        "# Chess Position",
        "",
        "| r/c | a | b | c | d | e | f | g | h |",
        "| --- | --- | --- | --- | --- | --- | --- | --- | --- |",
    ]
    for rank in range(8, 0, -1):
        row = [f"| {rank} |"]
        for file_index in range(8):
            square = f"{FILES[file_index]}{rank}"
            piece = board.get(square)
            row.append(f" {PIECE_SYMBOLS.get(piece, '.')} |")
        lines.append("".join(row))
    return "\n".join(lines)


def render_chess_solution_line_markdown(
    position: ChessPosition,
    line: tuple[str, ...],
    side: str = WHITE,
) -> str:
    current = position
    current_side = side
    segments: list[str] = []
    for move_index, notation in enumerate(line, start=1):
        move = _find_move_by_notation(current, current_side, notation)
        current = apply_chess_move(current, move)
        mover = "white" if current_side == WHITE else "black"
        segments.extend(
            [
                f"### {move_index}. {mover}: `{notation}`",
                "",
                render_chess_position_markdown(current),
                "",
            ]
        )
        if _promotion_winner(current) is not None:
            break
        current_side = BLACK if current_side == WHITE else WHITE
    return "\n".join(segments).rstrip()


def render_chess_solution_markdown(position: ChessPosition | None = None, side: str = WHITE) -> str:
    current = position or build_image_chess_position()
    result = solve_chess_position(current, side)
    lines = [
        render_chess_position_markdown(current),
        "",
        "## Solve Result (First Promotion Objective)",
        "",
        f"- `side_to_move`: `{'white' if side == WHITE else 'black'}`",
        f"- `outcome`: `{result.outcome}`",
        f"- `reachable_states`: `{result.reachable_states}`",
        f"- `best_moves`: `{', '.join(result.best_moves) if result.best_moves else '-'}`",
        f"- `best_line`: `{', '.join(result.best_line) if result.best_line else '-'}`",
        f"- `terminal_promotion`: `{_promotion_winner(current) or '-'}`",
        "",
        "## Best Line",
        "",
        render_chess_solution_line_markdown(current, result.best_line, side),
    ]
    return "\n".join(lines)


def render_chess_phase_breakdown_markdown(
    position: ChessPosition | None = None,
    side: str = WHITE,
    include_stockfish_beam: bool = False,
) -> str:
    current = position or build_image_chess_position()
    phase1 = solve_chess_phase1_prefix(current, side)
    phase2 = solve_chess_phase2_preparation(phase1)
    phase3 = solve_chess_phase3_candidates(phase2)[:10]
    stockfish_phase3: tuple[ChessStockfishCandidateResult, ...] = ()
    stockfish_tree_phase3: tuple[ChessStockfishTreeResult, ...] = ()
    binary = find_stockfish_binary()
    if binary is not None:
        stockfish_phase3 = solve_chess_phase3_candidates_with_stockfish(phase2, depth=12, engine_path=binary)[:10]
        stockfish_tree_phase3 = solve_chess_phase3_tree_with_stockfish(phase2, depth=10, top_k=5, reply_k=3, plies=4, engine_path=binary)[:10]
    stockfish_beam_phase3: tuple[ChessStockfishBeamResult, ...] = ()
    if include_stockfish_beam and binary is not None:
        stockfish_beam_phase3 = solve_chess_phase3_beam_with_stockfish(phase2, depth=10, top_k=4, beam_width=128, plies=6, engine_path=binary)[:10]
    recommended = phase2.candidates[phase2.recommended_index] if phase2.candidates else None
    lines = [
        render_chess_position_markdown(current),
        "",
        "## Phase 1",
        "",
        f"- `prefix_line`: `{', '.join(phase1.prefix_line)}`",
        f"- `runner_square`: `{phase1.runner_square}`",
        f"- `promotion_square`: `{phase1.promotion_square}`",
        f"- `side_to_move_after_prefix`: `{'white' if phase1.side_to_move == WHITE else 'black'}`",
        f"- `black_prep_moves`: `{phase1.black_prep_moves}`",
        "",
        render_chess_position_markdown(phase1.position),
        "",
        "## Phase 2",
        "",
        f"- `candidate_count`: `{len(phase2.candidates)}`",
        f"- `recommended_index`: `{phase2.recommended_index}`",
        "",
    ]
    if recommended is not None:
        lines.extend(
            [
                "### Recommended",
                "",
                f"- `prep_line`: `{', '.join(recommended.prep_line) if recommended.prep_line else '-'}`",
                f"- `heuristic`: `{recommended.heuristic}`",
                f"- `immediate_mate`: `{recommended.immediate_mate}`",
                f"- `survival_moves`: `{recommended.survival_moves}`",
                f"- `phase3_side_to_move`: `{'white' if recommended.side_to_move == WHITE else 'black'}`",
                "",
                render_chess_position_markdown(recommended.start_position),
                "",
                "### All Candidates",
                "",
            ]
        )
        for index, candidate in enumerate(phase2.candidates):
            lines.extend(
                [
                    f"- `{index}`: `{', '.join(candidate.prep_line) if candidate.prep_line else '-'}` | heuristic=`{candidate.heuristic}` | immediate_mate=`{candidate.immediate_mate}` | survival_moves=`{candidate.survival_moves}` | side_to_move=`{'white' if candidate.side_to_move == WHITE else 'black'}`",
                ]
            )
    if phase3:
        lines.extend(
            [
                "",
                "## Phase 3",
                "",
                "### Top Candidate Finishes",
                "",
            ]
        )
        for item in phase3:
            lines.append(
                f"- `candidate {item.candidate_index}`: outcome=`{item.result.outcome}` score=`{item.result.score}` line=`{', '.join(item.result.best_line) if item.result.best_line else '-'}`"
            )
    if stockfish_phase3:
        lines.extend(
            [
                "",
                "## Phase 3 Stockfish",
                "",
            ]
        )
        for item in stockfish_phase3:
            lines.append(
                f"- `candidate {item.candidate_index}`: best_move=`{item.best_move or '-'}` eval=`{item.evaluation_type}:{item.evaluation_value}` wdl=`{item.wdl}` black_score=`{item.black_score}`"
            )
    if stockfish_tree_phase3:
        lines.extend(
            [
                "",
                "## Phase 3 Stockfish Tree",
                "",
            ]
        )
        for item in stockfish_tree_phase3:
            lines.append(
                f"- `candidate {item.candidate_index}`: black_score=`{item.black_score}` wdl=`{item.leaf_wdl}` line=`{', '.join(item.line) if item.line else '-'}` eval=`{item.leaf_eval_type}:{item.leaf_eval_value}`"
            )
    if stockfish_beam_phase3:
        lines.extend(
            [
                "",
                "## Phase 3 Stockfish Beam",
                "",
            ]
        )
        for item in stockfish_beam_phase3:
            lines.append(
                f"- `candidate {item.candidate_index}`: black_score=`{item.black_score}` wdl=`{item.leaf_wdl}` nodes=`{item.explored_nodes}` line=`{', '.join(item.line) if item.line else '-'}` eval=`{item.leaf_eval_type}:{item.leaf_eval_value}`"
            )
    return "\n".join(lines)


def _side_has_mate_in_one(position: ChessPosition, side: str) -> bool:
    enemy = BLACK if side == WHITE else WHITE
    for move in list_chess_moves(position, side):
        child = apply_chess_move(position, move)
        if is_in_check(child, enemy) and not list_chess_moves(child, enemy):
            return True
    return False


def _count_survival_moves(position: ChessPosition, side: str) -> int:
    if side == WHITE:
        return 0 if _side_has_mate_in_one(position, WHITE) else 1
    legal = list_chess_moves(position, BLACK)
    if not legal:
        return 0
    survivors = 0
    for move in legal:
        child = apply_chess_move(position, move)
        if not _side_has_mate_in_one(child, WHITE):
            survivors += 1
    return survivors


def _is_immediate_mate_candidate(position: ChessPosition, side: str) -> bool:
    if side == WHITE:
        return _side_has_mate_in_one(position, WHITE)
    return _count_survival_moves(position, BLACK) == 0


def is_in_check(position: ChessPosition, side: str) -> bool:
    board = position.board_map()
    king_piece = "K" if side == WHITE else "k"
    king_square = next((square for square, piece in board.items() if piece == king_piece), None)
    if king_square is None:
        return True
    enemy = BLACK if side == WHITE else WHITE
    return _is_square_attacked(board, king_square, enemy)


def _pawn_race_moves(position: ChessPosition, side: str) -> list[ChessMove]:
    board = position.board_map()
    moves: list[ChessMove] = []
    for square, piece in board.items():
        if piece != ("P" if side == WHITE else "p"):
            continue
        moves.extend(_pawn_moves(board, square, piece))
    return sorted(moves, key=lambda move: move.notation())


def _promotion_winner(position: ChessPosition) -> str | None:
    board = position.board_map()
    if "Q" in board.values():
        return WHITE
    if "q" in board.values():
        return BLACK
    return None


def _first_passed_pawn_square(position: ChessPosition, side: str) -> str | None:
    board = position.board_map()
    pawn = "P" if side == WHITE else "p"
    enemy = "p" if side == WHITE else "P"
    candidates: list[tuple[int, str]] = []
    for square, piece in board.items():
        if piece != pawn:
            continue
        x, y = parse_square(square)
        blocked = False
        for enemy_square, enemy_piece in board.items():
            if enemy_piece != enemy:
                continue
            ex, ey = parse_square(enemy_square)
            if abs(ex - x) > 1:
                continue
            if side == WHITE and ey > y:
                blocked = True
                break
            if side == BLACK and ey < y:
                blocked = True
                break
        if not blocked:
            progress = y if side == WHITE else (7 - y)
            candidates.append((progress, square))
    if not candidates:
        return None
    return sorted(candidates)[-1][1]


def _is_passed_black_pawn(board: dict[str, str], square: str) -> bool:
    x, y = parse_square(square)
    for enemy_square, enemy_piece in board.items():
        if enemy_piece != "P":
            continue
        ex, ey = parse_square(enemy_square)
        if abs(ex - x) <= 1 and ey < y:
            return False
    return True


def _is_adjacent_to_black_king(board: dict[str, str], square: str) -> bool:
    king_square = next((sq for sq, piece in board.items() if piece == "k"), None)
    if king_square is None:
        return False
    return _squares_adjacent(square, king_square)


def _is_safe_white_capture_target(board: dict[str, str], square: str) -> bool:
    return not _is_adjacent_to_black_king(board, square)


def _squares_adjacent(left: str, right: str) -> bool:
    lx, ly = parse_square(left)
    rx, ry = parse_square(right)
    return max(abs(lx - rx), abs(ly - ry)) == 1


def _forced_runner_move(position: ChessPosition, runner_square: str) -> ChessMove | None:
    board = position.board_map()
    piece = board.get(runner_square)
    if piece != "P":
        runner_square = _first_passed_pawn_square(position, WHITE) or runner_square
        piece = board.get(runner_square)
    if piece != "P":
        return None
    moves = [move for move in _pawn_race_moves(position, WHITE) if move.from_square == runner_square]
    if not moves:
        return None
    return sorted(moves, key=lambda move: (0 if move.promotion else 1, move.to_square))[0]


def _phase3_moves(position: ChessPosition, side: str) -> list[ChessMove]:
    legal = list_chess_moves(position, side)
    if side == WHITE:
        capture_pawns = [
            move
            for move in legal
            if position.board_map().get(move.to_square) == "p"
            and _is_safe_white_capture_target(position.board_map(), move.to_square)
        ]
        if capture_pawns:
            return sorted(capture_pawns, key=lambda move: move.notation())
        checks = [move for move in legal if _move_gives_check(position, move, BLACK)]
        if checks:
            return sorted(checks, key=lambda move: move.notation())
        return legal

    pawn_moves = [move for move in legal if position.board_map().get(move.from_square) == "p"]
    if pawn_moves:
        return sorted(pawn_moves, key=lambda move: (-_black_pawn_push_score(position, move), move.notation()))
    escort_moves = [
        move
        for move in legal
        if position.board_map().get(move.from_square) == "k"
        and _black_king_escort_score(position, move) > 0
    ]
    if escort_moves:
        return sorted(escort_moves, key=lambda move: (-_black_king_escort_score(position, move), move.notation()))
    return legal


def _move_gives_check(position: ChessPosition, move: ChessMove, target_side: str) -> bool:
    child = apply_chess_move(position, move)
    return is_in_check(child, target_side)


def _black_pawn_push_score(position: ChessPosition, move: ChessMove) -> int:
    board = position.board_map()
    piece = board.get(move.from_square)
    if piece != "p":
        return -10**6
    x, y = parse_square(move.to_square)
    score = (7 - y) * 20
    if _is_adjacent_to_black_king(apply_chess_move(position, move).board_map(), move.to_square):
        score += 40
    if x in {5, 6, 7}:
        score += 15
    return score


def _black_king_escort_score(position: ChessPosition, move: ChessMove) -> int:
    child_board = apply_chess_move(position, move).board_map()
    king_square = move.to_square
    score = 0
    for square, piece in child_board.items():
        if piece == "p" and _squares_adjacent(square, king_square):
            score += 20
    return score


def _piece_color(piece: str) -> str:
    return WHITE if piece.isupper() else BLACK


def _promoted_piece(piece: str, promotion: str | None) -> str:
    if promotion is None:
        return piece
    return promotion.upper() if piece.isupper() else promotion.lower()


def _piece_moves(board: dict[str, str], square: str, piece: str) -> list[ChessMove]:
    kind = piece.upper()
    if kind == "P":
        return _pawn_moves(board, square, piece)
    if kind == "K":
        return _king_moves(board, square, piece)
    if kind == "N":
        return _jump_moves(board, square, piece, ((1, 2), (2, 1), (-1, 2), (-2, 1), (1, -2), (2, -1), (-1, -2), (-2, -1)))
    if kind == "B":
        return _slider_moves(board, square, piece, ((1, 1), (1, -1), (-1, 1), (-1, -1)))
    if kind == "R":
        return _slider_moves(board, square, piece, ((1, 0), (-1, 0), (0, 1), (0, -1)))
    if kind == "Q":
        return _slider_moves(board, square, piece, ((1, 1), (1, -1), (-1, 1), (-1, -1), (1, 0), (-1, 0), (0, 1), (0, -1)))
    return []


def _pawn_moves(board: dict[str, str], square: str, piece: str) -> list[ChessMove]:
    x, y = parse_square(square)
    direction = 1 if piece.isupper() else -1
    start_rank = 1 if piece.isupper() else 6
    promotion_rank = 7 if piece.isupper() else 0
    moves: list[ChessMove] = []

    one_step = (x, y + direction)
    if _inside(*one_step) and format_square(one_step) not in board:
        to_square = format_square(one_step)
        if one_step[1] == promotion_rank:
            moves.extend(ChessMove(square, to_square, promo) for promo in ("q", "r", "b", "n"))
        else:
            moves.append(ChessMove(square, to_square))
            two_step = (x, y + 2 * direction)
            if y == start_rank and _inside(*two_step) and format_square(two_step) not in board:
                moves.append(ChessMove(square, format_square(two_step)))

    for dx in (-1, 1):
        target = (x + dx, y + direction)
        if not _inside(*target):
            continue
        target_square = format_square(target)
        target_piece = board.get(target_square)
        if target_piece is None or _piece_color(target_piece) == _piece_color(piece):
            continue
        if target[1] == promotion_rank:
            moves.extend(ChessMove(square, target_square, promo) for promo in ("q", "r", "b", "n"))
        else:
            moves.append(ChessMove(square, target_square))
    return moves


def _king_moves(board: dict[str, str], square: str, piece: str) -> list[ChessMove]:
    return _jump_moves(board, square, piece, ((1, 1), (1, 0), (1, -1), (0, 1), (0, -1), (-1, 1), (-1, 0), (-1, -1)))


def _jump_moves(board: dict[str, str], square: str, piece: str, deltas: tuple[tuple[int, int], ...]) -> list[ChessMove]:
    x, y = parse_square(square)
    moves: list[ChessMove] = []
    for dx, dy in deltas:
        target = (x + dx, y + dy)
        if not _inside(*target):
            continue
        target_square = format_square(target)
        target_piece = board.get(target_square)
        if target_piece is not None and _piece_color(target_piece) == _piece_color(piece):
            continue
        moves.append(ChessMove(square, target_square))
    return moves


def _slider_moves(board: dict[str, str], square: str, piece: str, deltas: tuple[tuple[int, int], ...]) -> list[ChessMove]:
    x, y = parse_square(square)
    moves: list[ChessMove] = []
    for dx, dy in deltas:
        nx, ny = x + dx, y + dy
        while _inside(nx, ny):
            target_square = format_square((nx, ny))
            target_piece = board.get(target_square)
            if target_piece is None:
                moves.append(ChessMove(square, target_square))
            else:
                if _piece_color(target_piece) != _piece_color(piece):
                    moves.append(ChessMove(square, target_square))
                break
            nx += dx
            ny += dy
    return moves


def _is_square_attacked(board: dict[str, str], square: str, by_side: str) -> bool:
    target = parse_square(square)
    for origin, piece in board.items():
        if _piece_color(piece) != by_side:
            continue
        kind = piece.upper()
        ox, oy = parse_square(origin)
        if kind == "P":
            direction = 1 if by_side == WHITE else -1
            for dx in (-1, 1):
                if (ox + dx, oy + direction) == target:
                    return True
            continue
        if kind == "N":
            if (target[0] - ox, target[1] - oy) in ((1, 2), (2, 1), (-1, 2), (-2, 1), (1, -2), (2, -1), (-1, -2), (-2, -1)):
                return True
            continue
        if kind == "K":
            if max(abs(target[0] - ox), abs(target[1] - oy)) == 1:
                return True
            continue
        directions = ()
        if kind == "B":
            directions = ((1, 1), (1, -1), (-1, 1), (-1, -1))
        elif kind == "R":
            directions = ((1, 0), (-1, 0), (0, 1), (0, -1))
        elif kind == "Q":
            directions = ((1, 1), (1, -1), (-1, 1), (-1, -1), (1, 0), (-1, 0), (0, 1), (0, -1))
        for dx, dy in directions:
            nx, ny = ox + dx, oy + dy
            while _inside(nx, ny):
                if (nx, ny) == target:
                    return True
                if format_square((nx, ny)) in board:
                    break
                nx += dx
                ny += dy
    return False


def _find_move_by_notation(position: ChessPosition, side: str, notation: str) -> ChessMove:
    for move in list_chess_moves(position, side):
        if move.notation() == notation:
            return move
    raise ValueError(f"move {notation!r} is not legal in current position")


def _uci_to_move(uci: str) -> ChessMove | None:
    if len(uci) < 4:
        return None
    from_square = uci[:2]
    to_square = uci[2:4]
    promotion = uci[4] if len(uci) > 4 else None
    return ChessMove(from_square=from_square, to_square=to_square, promotion=promotion)


def _inside(x: int, y: int) -> bool:
    return 0 <= x < 8 and 0 <= y < 8
