from __future__ import annotations

from dataclasses import dataclass, field
import shlex
from typing import Any
import yaml

from .loader import UiLayoutError
from .patch_ops import (
    AddNodeOp,
    MoveNodeOp,
    PatchOp,
    RemoveNodeOp,
    RenameNodeOp,
    ResizeNodeOp,
    UpdateNodeMetaOp,
)
from .schema import LayoutDocument, Rect


class ConsoleCommandError(ValueError):
    pass


@dataclass(slots=True)
class ConsolePatchContext:
    selected_id: str | None = None


@dataclass(slots=True)
class ConsoleCommandResult:
    ops: list[PatchOp] = field(default_factory=list)
    context: ConsolePatchContext = field(default_factory=ConsolePatchContext)
    control: str | None = None


def compile_console_command(
    command: str,
    layout_doc: LayoutDocument,
    context: ConsolePatchContext | None = None,
) -> ConsoleCommandResult:
    ctx = ConsolePatchContext(selected_id=context.selected_id if context else None)
    text = str(command or '').strip()
    if not text:
        raise ConsoleCommandError('Empty command')

    lowered = text.lower()
    if lowered in frozenset({'undo', 'apply', 'diff', 'preview'}):
        return ConsoleCommandResult(ops=[], context=ctx, control=lowered)

    tokens = shlex.split(text)
    if not tokens:
        raise ConsoleCommandError('Empty command')

    head = tokens[0].lower()
    if head == 'select':
        return _compile_select(tokens, layout_doc, ctx)
    if head == 'parent':
        return _compile_parent(layout_doc, ctx)
    if head == 'child':
        return _compile_child(tokens, layout_doc, ctx)
    if head == 'set':
        return _compile_set(text, layout_doc, ctx)
    if head == 'add':
        return _compile_add(text, layout_doc, ctx)
    if head == 'on':
        return _compile_on(tokens, layout_doc, ctx)
    if head == 'rename':
        return _compile_rename(tokens, layout_doc, ctx)
    if head == 'move':
        return _compile_move(tokens, layout_doc, ctx)
    if head == 'resize':
        return _compile_resize(tokens, layout_doc, ctx)
    if head == 'delete':
        return _compile_delete(tokens, layout_doc, ctx)

    raise ConsoleCommandError(f'Unsupported command: {tokens[0]}')


def _compile_select(tokens: list[str], layout_doc: LayoutDocument, ctx: ConsolePatchContext) -> ConsoleCommandResult:
    if len(tokens) != 2:
        raise ConsoleCommandError('Usage: select <node_id>')
    node_id = tokens[1]
    _require_node(layout_doc, node_id)
    ctx.selected_id = node_id
    return ConsoleCommandResult(ops=[], context=ctx)


def _compile_parent(layout_doc: LayoutDocument, ctx: ConsolePatchContext) -> ConsoleCommandResult:
    node_id = _require_selected(ctx)
    node = _require_node(layout_doc, node_id)
    if node.parent is None:
        raise ConsoleCommandError(f"Node '{node_id}' has no parent")
    ctx.selected_id = node.parent
    return ConsoleCommandResult(ops=[], context=ctx)


def _compile_child(tokens: list[str], layout_doc: LayoutDocument, ctx: ConsolePatchContext) -> ConsoleCommandResult:
    node_id = _require_selected(ctx)
    node = _require_node(layout_doc, node_id)
    if len(tokens) != 2:
        raise ConsoleCommandError('Usage: child <index>')
    try:
        index = int(tokens[1])
    except ValueError as exc:
        raise ConsoleCommandError('child index must be an integer') from exc
    if index < 1 or index > len(node.children):
        raise ConsoleCommandError(f'child index out of range: {index}')
    ctx.selected_id = node.children[index - 1]
    return ConsoleCommandResult(ops=[], context=ctx)


def _compile_set(text: str, layout_doc: LayoutDocument, ctx: ConsolePatchContext) -> ConsoleCommandResult:
    node_id = _require_selected(ctx)
    _require_node(layout_doc, node_id)
    rest = text[4:].strip()
    if not rest:
        raise ConsoleCommandError('Usage: set <path> <value>')
    path, sep, raw_value = rest.partition(' ')
    if not sep:
        raise ConsoleCommandError('Usage: set <path> <value>')
    value = _parse_value(raw_value.strip())
    patch = _build_nested_patch(path, value)
    return ConsoleCommandResult(ops=[UpdateNodeMetaOp(node_id, patch)], context=ctx)


def _compile_add(text: str, layout_doc: LayoutDocument, ctx: ConsolePatchContext) -> ConsoleCommandResult:
    parent_id = _require_selected(ctx)
    _require_node(layout_doc, parent_id)
    rest = text[4:].strip()
    if not rest:
        raise ConsoleCommandError('Usage: add <id>: [x, y, w, h]')
    head, sep, raw_rect = rest.partition(':')
    head = head.strip()
    if not sep or not head:
        raise ConsoleCommandError('Usage: add <id>: [x, y, w, h] | add <kind> <id>: [x, y, w, h]')
    head_tokens = head.split()
    if len(head_tokens) == 1:
        kind = 'panel'
        node_id = head_tokens[0]
    elif len(head_tokens) == 2:
        kind, node_id = head_tokens
    else:
        raise ConsoleCommandError('Usage: add <id>: [x, y, w, h] | add <kind> <id>: [x, y, w, h]')
    if node_id in layout_doc.nodes:
        raise ConsoleCommandError(f"Node '{node_id}' already exists")
    rect_value = _parse_value(raw_rect.strip())
    if not (isinstance(rect_value, list) and len(rect_value) == 4 and all(isinstance(v, int) for v in rect_value)):
        raise ConsoleCommandError('add rect must be [x, y, w, h]')
    rect = Rect(x=rect_value[0], y=rect_value[1], w=rect_value[2], h=rect_value[3])
    if rect.w <= 0 or rect.h <= 0:
        raise ConsoleCommandError('add rect must have positive width and height')
    return ConsoleCommandResult(
        ops=[AddNodeOp(node_id, parent_id, kind, rect)],
        context=ConsolePatchContext(selected_id=node_id),
    )


def _compile_on(tokens: list[str], layout_doc: LayoutDocument, ctx: ConsolePatchContext) -> ConsoleCommandResult:
    node_id = _require_selected(ctx)
    _require_node(layout_doc, node_id)
    if len(tokens) < 4:
        raise ConsoleCommandError('Usage: on <event> emit <name> | on <event> set <target>')
    event_name = tokens[1]
    action_kind = tokens[2].lower()
    if action_kind == 'emit':
        if len(tokens) != 4:
            raise ConsoleCommandError('Usage: on <event> emit <name>')
        patch = {'events': {event_name: {'emit': tokens[3]}}}
        return ConsoleCommandResult(ops=[UpdateNodeMetaOp(node_id, patch)], context=ctx)
    if action_kind == 'set':
        if len(tokens) != 4:
            raise ConsoleCommandError('Usage: on <event> set <target>')
        patch = {'events': {event_name: {'set': tokens[3]}}}
        return ConsoleCommandResult(ops=[UpdateNodeMetaOp(node_id, patch)], context=ctx)
    raise ConsoleCommandError(f'Unsupported event action: {tokens[2]}')


def _compile_rename(tokens: list[str], layout_doc: LayoutDocument, ctx: ConsolePatchContext) -> ConsoleCommandResult:
    node_id = _require_selected(ctx)
    _require_node(layout_doc, node_id)
    if len(tokens) != 2:
        raise ConsoleCommandError('Usage: rename <new_id>')
    new_id = tokens[1]
    ctx.selected_id = new_id
    return ConsoleCommandResult(ops=[RenameNodeOp(node_id, new_id)], context=ctx)


def _compile_move(tokens: list[str], layout_doc: LayoutDocument, ctx: ConsolePatchContext) -> ConsoleCommandResult:
    node_id = _require_selected(ctx)
    _require_node(layout_doc, node_id)
    if len(tokens) != 3:
        raise ConsoleCommandError('Usage: move <dx> <dy>')
    return ConsoleCommandResult(
        ops=[MoveNodeOp(node_id, _parse_int(tokens[1], 'dx'), _parse_int(tokens[2], 'dy'))],
        context=ctx,
    )


def _compile_resize(tokens: list[str], layout_doc: LayoutDocument, ctx: ConsolePatchContext) -> ConsoleCommandResult:
    node_id = _require_selected(ctx)
    _require_node(layout_doc, node_id)
    if len(tokens) != 3:
        raise ConsoleCommandError('Usage: resize <dw> <dh>')
    return ConsoleCommandResult(
        ops=[ResizeNodeOp(node_id, _parse_int(tokens[1], 'dw'), _parse_int(tokens[2], 'dh'))],
        context=ctx,
    )


def _compile_delete(tokens: list[str], layout_doc: LayoutDocument, ctx: ConsolePatchContext) -> ConsoleCommandResult:
    node_id = _require_selected(ctx)
    node = _require_node(layout_doc, node_id)
    delete_subtree = len(tokens) > 1 and tokens[1].lower() == 'subtree'
    return ConsoleCommandResult(
        ops=[RemoveNodeOp(node_id, delete_subtree=delete_subtree)],
        context=ConsolePatchContext(selected_id=node.parent),
    )


def _build_nested_patch(path: str, value: Any) -> dict[str, Any]:
    parts = [part for part in path.split('.') if part]
    if not parts:
        raise ConsoleCommandError('set path must not be empty')
    patch = value
    for part in reversed(parts):
        patch = {part: patch}
    return patch


def _parse_value(raw: str) -> Any:
    if not raw:
        return ''
    try:
        return yaml.safe_load(raw)
    except yaml.YAMLError:
        return raw


def _parse_int(raw: str, name: str) -> int:
    try:
        return int(raw)
    except ValueError as exc:
        raise ConsoleCommandError(f'{name} must be an integer') from exc


def _require_selected(ctx: ConsolePatchContext) -> str:
    if not ctx.selected_id:
        raise ConsoleCommandError('No selected node')
    return ctx.selected_id


def _require_node(layout_doc: LayoutDocument, node_id: str):
    node = layout_doc.nodes.get(node_id)
    if node is None:
        raise UiLayoutError(f"Unknown node id '{node_id}'")
    return node
