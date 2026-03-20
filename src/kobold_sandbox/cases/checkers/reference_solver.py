from __future__ import annotations

from dataclasses import dataclass

FILES = "abcdefgh"
WHITE = "w"
BLACK = "b"
WHITE_DIRS = ((-1, 1), (1, 1))
BLACK_DIRS = ((-1, -1), (1, -1))
ALL_DIRS = ((-1, 1), (1, 1), (-1, -1), (1, -1))


@dataclass(frozen=True)
class CheckersMove:
    path: tuple[str, ...]
    is_capture: bool = False

    def notation(self) -> str:
        separator = ":" if self.is_capture else "-"
        return separator.join(self.path)


@dataclass(frozen=True)
class CheckersPosition:
    white_men: tuple[str, ...]
    black_men: tuple[str, ...]
    white_kings: tuple[str, ...] = ()
    black_kings: tuple[str, ...] = ()

    def board_map(self) -> dict[tuple[int, int], str]:
        board: dict[tuple[int, int], str] = {}
        for square in self.white_men:
            board[parse_square(square)] = "w"
        for square in self.black_men:
            board[parse_square(square)] = "b"
        for square in self.white_kings:
            board[parse_square(square)] = "wK"
        for square in self.black_kings:
            board[parse_square(square)] = "bK"
        return board


@dataclass(frozen=True)
class CheckersSolveResult:
    outcome: str
    best_moves: tuple[str, ...]
    best_line: tuple[str, ...]
    reachable_states: int


def parse_square(square: str) -> tuple[int, int]:
    return FILES.index(square[0]), int(square[1]) - 1


def format_square(cell: tuple[int, int]) -> str:
    return f"{FILES[cell[0]]}{cell[1] + 1}"


def build_image_checkers_position() -> CheckersPosition:
    return CheckersPosition(
        white_men=("c1", "e1", "h4"),
        black_men=("a3", "a5", "h6"),
    )


def list_russian_checkers_moves(position: CheckersPosition, side: str = WHITE) -> list[CheckersMove]:
    board = position.board_map()
    capture_paths = _capture_paths(board, side)
    if capture_paths:
        return [CheckersMove(path=tuple(format_square(cell) for cell in path), is_capture=True) for path in capture_paths]
    return [CheckersMove(path=tuple(format_square(cell) for cell in path), is_capture=False) for path in _quiet_paths(board, side)]


def apply_russian_checkers_move(position: CheckersPosition, move: CheckersMove, side: str = WHITE) -> CheckersPosition:
    board = dict(position.board_map())
    start = parse_square(move.path[0])
    piece = board.pop(start)
    current = start
    for next_square in move.path[1:]:
        target = parse_square(next_square)
        if move.is_capture:
            _remove_captured_piece(board, current, target, side)
        piece = _promote(piece, target[1])
        current = target
    board[current] = piece
    return _position_from_board(board)


def next_russian_checkers_positions(position: CheckersPosition, side: str = WHITE) -> list[tuple[CheckersMove, CheckersPosition]]:
    return [
        (move, apply_russian_checkers_move(position, move, side))
        for move in list_russian_checkers_moves(position, side)
    ]


def solve_russian_checkers_position(position: CheckersPosition, side: str = WHITE) -> CheckersSolveResult:
    cache: dict[tuple[CheckersPosition, str], tuple[int, tuple[str, ...], int]] = {}

    def solve_node(current_position: CheckersPosition, current_side: str) -> tuple[int, tuple[str, ...], int]:
        node = (current_position, current_side)
        if node in cache:
            return cache[node]
        if current_position.white_kings or current_position.black_kings:
            winner = WHITE if current_position.white_kings else BLACK
            result = (1 if winner == current_side else -1, (), 1)
            cache[node] = result
            return result
        moves = next_russian_checkers_positions(current_position, current_side)
        if not moves:
            result = (-1, (), 1)
            cache[node] = result
            return result
        next_side = BLACK if current_side == WHITE else WHITE
        best_score = -2
        best_lines: tuple[str, ...] = ()
        seen_states = 1
        for move, child in moves:
            child_score, child_line, child_seen = solve_node(child, next_side)
            score = -child_score
            seen_states += child_seen
            if score > best_score:
                best_score = score
                best_lines = (move.notation(),) + child_line
            if best_score == 1:
                break
        result = (best_score, best_lines, seen_states)
        cache[node] = result
        return result

    score, line, reachable_states = solve_node(position, side)
    root_outcome = {1: "win", 0: "draw", -1: "loss"}.get(score, "draw")
    best_moves = list(line[:1]) or [move.notation() for move in list_russian_checkers_moves(position, side)]
    return CheckersSolveResult(
        outcome=root_outcome,
        best_moves=tuple(best_moves),
        best_line=line,
        reachable_states=reachable_states,
    )


def render_checkers_position_markdown(position: CheckersPosition | None = None) -> str:
    current = position or build_image_checkers_position()
    board = current.board_map()
    lines = [
        "# Checkers Position",
        "",
        "| r/c | a | b | c | d | e | f | g | h |",
        "| --- | --- | --- | --- | --- | --- | --- | --- | --- |",
    ]
    for rank in range(8, 0, -1):
        row = [f"| {rank} |"]
        for file_index in range(8):
            piece = board.get((file_index, rank - 1), "")
            row.append(f" {piece or '.'} |")
        lines.append("".join(row))
    return "\n".join(lines)


def render_checkers_solution_markdown(
    position: CheckersPosition | None = None,
    side: str = WHITE,
) -> str:
    current = position or build_image_checkers_position()
    result = solve_russian_checkers_position(current, side)
    line_views = render_checkers_solution_line_markdown(current, result.best_line, side)
    lines = [
        render_checkers_position_markdown(current),
        "",
        "## Solve Result (First King Objective)",
        "",
        f"- `side_to_move`: `{'white' if side == WHITE else 'black'}`",
        f"- `outcome`: `{result.outcome}`",
        f"- `reachable_states`: `{result.reachable_states}`",
        f"- `best_moves`: `{', '.join(result.best_moves) if result.best_moves else '-'}`",
        f"- `best_line`: `{', '.join(result.best_line) if result.best_line else '-'}`",
        "",
        "## Best Line",
        "",
        line_views,
    ]
    return "\n".join(lines)


def render_checkers_solution_line_markdown(
    position: CheckersPosition,
    line: tuple[str, ...],
    side: str = WHITE,
) -> str:
    current = position
    current_side = side
    segments: list[str] = []
    for move_index, notation in enumerate(line, start=1):
        move = _find_move_by_notation(current, current_side, notation)
        current = apply_russian_checkers_move(current, move, current_side)
        mover = "white" if current_side == WHITE else "black"
        segments.extend(
            [
                f"### {move_index}. {mover}: `{notation}`",
                "",
                render_checkers_position_markdown(current),
                "",
            ]
        )
        current_side = BLACK if current_side == WHITE else WHITE
        if current.white_kings or current.black_kings:
            break
    return "\n".join(segments).rstrip()


def _inside(x: int, y: int) -> bool:
    return 0 <= x < 8 and 0 <= y < 8


def _piece_color(piece: str) -> str:
    return piece[0]


def _is_king(piece: str) -> bool:
    return piece.endswith("K")


def _promote(piece: str, y: int) -> str:
    if piece == "w" and y == 7:
        return "wK"
    if piece == "b" and y == 0:
        return "bK"
    return piece


def _remove_captured_piece(
    board: dict[tuple[int, int], str],
    start: tuple[int, int],
    target: tuple[int, int],
    side: str,
) -> None:
    dx = 0 if target[0] == start[0] else (1 if target[0] > start[0] else -1)
    dy = 0 if target[1] == start[1] else (1 if target[1] > start[1] else -1)
    x, y = start[0] + dx, start[1] + dy
    captured: tuple[int, int] | None = None
    while (x, y) != target:
        piece = board.get((x, y))
        if piece is not None:
            if _piece_color(piece) == side:
                raise ValueError("illegal capture over own piece")
            if captured is not None:
                raise ValueError("illegal capture over multiple pieces")
            captured = (x, y)
        x += dx
        y += dy
    if captured is None:
        raise ValueError("capture path without captured piece")
    board.pop(captured)


def _find_move_by_notation(position: CheckersPosition, side: str, notation: str) -> CheckersMove:
    for move in list_russian_checkers_moves(position, side):
        if move.notation() == notation:
            return move
    raise ValueError(f"move {notation!r} is not legal in current position")


def _position_from_board(board: dict[tuple[int, int], str]) -> CheckersPosition:
    white_men: list[str] = []
    black_men: list[str] = []
    white_kings: list[str] = []
    black_kings: list[str] = []
    for cell in sorted(board):
        piece = board[cell]
        square = format_square(cell)
        if piece == "w":
            white_men.append(square)
        elif piece == "b":
            black_men.append(square)
        elif piece == "wK":
            white_kings.append(square)
        elif piece == "bK":
            black_kings.append(square)
    return CheckersPosition(
        white_men=tuple(white_men),
        black_men=tuple(black_men),
        white_kings=tuple(white_kings),
        black_kings=tuple(black_kings),
    )


def _capture_paths(board: dict[tuple[int, int], str], side: str) -> list[tuple[tuple[int, int], ...]]:
    enemy = BLACK if side == WHITE else WHITE
    paths: list[tuple[tuple[int, int], ...]] = []

    def walk(current_board: dict[tuple[int, int], str], start: tuple[int, int], path: list[tuple[int, int]]) -> None:
        piece = current_board[start]
        x, y = start
        found = False
        if _is_king(piece):
            for dx, dy in ALL_DIRS:
                nx, ny = x + dx, y + dy
                seen_enemy: tuple[int, int] | None = None
                while _inside(nx, ny):
                    target = current_board.get((nx, ny))
                    if target is None:
                        if seen_enemy is not None:
                            found = True
                            nxt = dict(current_board)
                            mover = nxt.pop(start)
                            nxt.pop(seen_enemy)
                            nxt[(nx, ny)] = mover
                            walk(nxt, (nx, ny), path + [(nx, ny)])
                        nx += dx
                        ny += dy
                        continue
                    if _piece_color(target) == side or seen_enemy is not None:
                        break
                    seen_enemy = (nx, ny)
                    nx += dx
                    ny += dy
        else:
            for dx, dy in ALL_DIRS:
                mid = (x + dx, y + dy)
                land = (x + 2 * dx, y + 2 * dy)
                if not _inside(*land):
                    continue
                target = current_board.get(mid)
                if target is None or _piece_color(target) != enemy or land in current_board:
                    continue
                found = True
                nxt = dict(current_board)
                mover = _promote(nxt.pop(start), land[1])
                nxt.pop(mid)
                nxt[land] = mover
                walk(nxt, land, path + [land])
        if not found and len(path) > 1:
            paths.append(tuple(path))

    for cell, piece in board.items():
        if _piece_color(piece) == side:
            walk(board, cell, [cell])
    return sorted(set(paths))


def _quiet_paths(board: dict[tuple[int, int], str], side: str) -> list[tuple[tuple[int, int], ...]]:
    paths: list[tuple[tuple[int, int], ...]] = []
    for (x, y), piece in board.items():
        if _piece_color(piece) != side:
            continue
        if _is_king(piece):
            for dx, dy in ALL_DIRS:
                nx, ny = x + dx, y + dy
                while _inside(nx, ny) and (nx, ny) not in board:
                    paths.append(((x, y), (nx, ny)))
                    nx += dx
                    ny += dy
        else:
            dirs = WHITE_DIRS if side == WHITE else BLACK_DIRS
            for dx, dy in dirs:
                nx, ny = x + dx, y + dy
                if _inside(nx, ny) and (nx, ny) not in board:
                    paths.append(((x, y), (nx, ny)))
    return sorted(paths)
