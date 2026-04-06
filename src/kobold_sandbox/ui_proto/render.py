from __future__ import annotations

from dataclasses import dataclass

from .schema import Rect, UiRuntime


@dataclass(slots=True)
class UtfRenderResult:
    cols: int
    rows: int
    lines: list[str]


def render_utf_runtime(
    runtime: UiRuntime,
    selected_id: str | None = None,
    root_id: str | None = None,
) -> UtfRenderResult:
    render_root_id = root_id if root_id in runtime.nodes else runtime.root_id
    root = runtime.nodes.get(render_root_id)
    cols = root.rect.w if root is not None and render_root_id != runtime.root_id else runtime.cols
    rows = root.rect.h if root is not None and render_root_id != runtime.root_id else runtime.rows
    grid = [[' ' for _ in range(cols)] for _ in range(rows)]
    if root is not None:
        origin_x = root.rect.x if render_root_id != runtime.root_id else 0
        origin_y = root.rect.y if render_root_id != runtime.root_id else 0
        _render_subtree(runtime, root.id, grid, selected_id, origin_x=origin_x, origin_y=origin_y)
    lines = [''.join(row) for row in grid]
    return UtfRenderResult(cols=cols, rows=rows, lines=lines)


def _render_subtree(
    runtime: UiRuntime,
    node_id: str,
    grid: list[list[str]],
    selected_id: str | None,
    *,
    origin_x: int,
    origin_y: int,
) -> None:
    node = runtime.nodes[node_id]
    _render_node(node, grid, is_selected=node.id == selected_id, origin_x=origin_x, origin_y=origin_y)
    for child_id in node.children:
        if child_id not in runtime.nodes:
            continue
        _render_subtree(runtime, child_id, grid, selected_id, origin_x=origin_x, origin_y=origin_y)


def _render_node(
    node,
    grid: list[list[str]],
    is_selected: bool,
    origin_x: int,
    origin_y: int,
) -> None:
    kind = node.kind
    title = node.title
    rect = Rect(
        x=node.rect.x - origin_x,
        y=node.rect.y - origin_y,
        w=node.rect.w,
        h=node.rect.h,
    )
    props = node.props
    view = node.view
    renderer = getattr(node, 'renderer', '') or ''

    if kind == 'screen':
        return

    if kind == 'label':
        text = str(props.get('text') or view.get('text') or title or '')
        _put_text(grid, rect.y, rect.x, text[:rect.w])
        return

    if rect.w < 2 or rect.h < 2:
        return

    chars = _border_chars(is_selected)
    left = rect.x
    top = rect.y
    right = rect.right - 1
    bottom = rect.bottom - 1

    _put(grid, top, left, chars['tl'])
    _put(grid, top, right, chars['tr'])
    _put(grid, bottom, left, chars['bl'])
    _put(grid, bottom, right, chars['br'])
    for x in range(left + 1, right):
        _put(grid, top, x, chars['h'])
        _put(grid, bottom, x, chars['h'])
    for y in range(top + 1, bottom):
        _put(grid, y, left, chars['v'])
        _put(grid, y, right, chars['v'])

    if renderer == 'utf_button' or kind == 'button':
        text = str(props.get('text') or view.get('text') or title or '')
        label = f'[{text}]'
        _put_text(grid, top + max(0, rect.h // 2), left + 1, label[:max(0, rect.w - 2)])
        return

    if renderer == 'utf_input' or kind == 'editbox':
        value = str(props.get('value') or view.get('text') or '')
        placeholder = str(props.get('placeholder') or view.get('placeholder') or '')
        text = value or placeholder
        _put_text(grid, top + 1, left + 1, text[:max(0, rect.w - 2)])
        return

    if kind == 'checkbox':
        text = str(view.get('text') or title or '')
        checked = bool(view.get('checked'))
        label = ('[x] ' if checked else '[ ] ') + text
        _put_text(grid, top + 1, left + 1, label[:max(0, rect.w - 2)])
        return

    inner_title = str(props.get('text') or view.get('text') or title or '')
    if inner_title:
        _put_text(grid, top, left + 1, f' {inner_title} '[:max(0, rect.w - 2)])
    inner_width = max(0, rect.w - 2)
    inner_height = max(0, rect.h - 2)
    if inner_width <= 0 or inner_height <= 0:
        return

    lines = _body_lines_for_node(node, inner_width, inner_height)
    for index, line in enumerate(lines[:inner_height]):
        _put_text(grid, top + 1 + index, left + 1, line[:inner_width])


def _body_lines_for_node(node, inner_width: int, inner_height: int) -> list[str]:
    renderer = getattr(node, 'renderer', '') or ''
    props = node.props
    bind = getattr(node, 'bind', {}) or {}
    data = getattr(node, 'data', {}) or {}
    resolved = getattr(node, 'resolved', {}) or {}

    if renderer == 'utf_list':
        items = resolved.get('items')
        if isinstance(items, list):
            bullet = str(props.get('bullet') or '\u2022')
            return [f'{bullet} {str(item)}' for item in items]
        if 'items' in bind:
            return [f'items <- {bind["items"]}']
        if data:
            return [f'data: {", ".join(data.keys())}']

    if renderer == 'utf_log':
        items = resolved.get('items')
        if isinstance(items, list):
            return [str(item) for item in items]
        if 'items' in bind:
            return [f'log <- {bind["items"]}']

    if renderer == 'utf_panel':
        if data:
            return [f'data: {", ".join(data.keys())}']
        if bind:
            return [f'bind: {", ".join(bind.keys())}']

    preview_lines = props.get('preview_lines')
    if isinstance(preview_lines, list):
        return [str(item) for item in preview_lines]

    if data:
        return [f'data: {", ".join(data.keys())}']
    if bind:
        return [f'bind: {", ".join(bind.keys())}']

    return []


def _border_chars(is_selected: bool) -> dict[str, str]:
    if is_selected:
        return {'tl': '\u2554', 'tr': '\u2557', 'bl': '\u255a', 'br': '\u255d', 'h': '\u2550', 'v': '\u2551'}
    return {'tl': '\u250c', 'tr': '\u2510', 'bl': '\u2514', 'br': '\u2518', 'h': '\u2500', 'v': '\u2502'}


def _put(grid: list[list[str]], y: int, x: int, ch: str) -> None:
    if 0 <= y < len(grid):
        if 0 <= x < len(grid[y]):
            grid[y][x] = ch


def _put_text(grid: list[list[str]], y: int, x: int, text: str) -> None:
    if not (0 <= y < len(grid)):
        return
    row = grid[y]
    for index, ch in enumerate(text):
        cx = x + index
        if not (0 <= cx < len(row)):
            continue
        row[cx] = ch
