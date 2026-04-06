from __future__ import annotations

from copy import deepcopy
from dataclasses import dataclass
from typing import Any

from .loader import (
    UiLayoutError,
    build_ui_runtime,
)
from .patch_ops import (
    AddNodeOp,
    MoveNodeOp,
    PatchOp,
    RemoveNodeOp,
    RenameNodeOp,
    ResizeNodeOp,
    SetNodeRectOp,
    UpdateNodeMetaOp,
)
from .schema import (
    LayoutDocument,
    LayoutNode,
    NlpMeta,
    NodeMeta,
    Rect,
    UiRuntime,
)


@dataclass(slots=True)
class PatchApplyResult:
    layout_doc: LayoutDocument
    node_meta: dict[str, NodeMeta]
    runtime: UiRuntime


def apply_patch_ops(
    layout_doc: LayoutDocument,
    node_meta: dict[str, NodeMeta],
    ops: list[PatchOp],
) -> PatchApplyResult:
    next_layout = _clone_layout(layout_doc)
    next_meta = _clone_node_meta(node_meta)
    for op in ops:
        _apply_single_op(next_layout, next_meta, op)
        build_ui_runtime(next_layout, next_meta)
    runtime = build_ui_runtime(next_layout, next_meta)
    return PatchApplyResult(layout_doc=next_layout, node_meta=next_meta, runtime=runtime)


def _apply_single_op(
    layout_doc: LayoutDocument,
    node_meta: dict[str, NodeMeta],
    op: PatchOp,
) -> None:
    if isinstance(op, AddNodeOp):
        _apply_add_node(layout_doc, node_meta, op)
        return
    if isinstance(op, RemoveNodeOp):
        _apply_remove_node(layout_doc, node_meta, op)
        return
    if isinstance(op, MoveNodeOp):
        _apply_move_node(layout_doc, op)
        return
    if isinstance(op, ResizeNodeOp):
        _apply_resize_node(layout_doc, op)
        return
    if isinstance(op, SetNodeRectOp):
        _apply_set_node_rect(layout_doc, op)
        return
    if isinstance(op, RenameNodeOp):
        _apply_rename_node(layout_doc, node_meta, op)
        return
    if isinstance(op, UpdateNodeMetaOp):
        _apply_update_node_meta(layout_doc, node_meta, op)
        return
    raise UiLayoutError(f"Unsupported patch op: {type(op).__name__}")


def _apply_add_node(
    layout_doc: LayoutDocument,
    node_meta: dict[str, NodeMeta],
    op: AddNodeOp,
) -> None:
    if op.id in layout_doc.nodes:
        raise UiLayoutError(f"Cannot add node '{op.id}': id already exists")
    if op.parent is not None and op.parent not in layout_doc.nodes:
        raise UiLayoutError(f"Cannot add node '{op.id}': missing parent '{op.parent}'")
    layout_doc.nodes[op.id] = LayoutNode(
        id=op.id,
        kind=op.kind,
        rect=_clone_rect(op.rect),
        parent=op.parent,
        children=[],
    )
    if op.parent is not None:
        layout_doc.nodes[op.parent].children.append(op.id)
    node_meta[op.id] = NodeMeta(title='', role='node.unknown', kind=op.kind)


def _apply_remove_node(
    layout_doc: LayoutDocument,
    node_meta: dict[str, NodeMeta],
    op: RemoveNodeOp,
) -> None:
    node = _require_node(layout_doc, op.id)
    if op.id == layout_doc.screen.root:
        raise UiLayoutError('Cannot remove root node')
    if node.children and not op.delete_subtree:
        raise UiLayoutError(f"Cannot remove node '{op.id}': node has children")
    ids_to_remove = _collect_subtree_ids(layout_doc, op.id) if op.delete_subtree else [op.id]
    parent_id = node.parent
    if parent_id is not None:
        parent = layout_doc.nodes[parent_id]
        parent.children = [child_id for child_id in parent.children if child_id not in ids_to_remove]
    for remove_id in ids_to_remove:
        layout_doc.nodes.pop(remove_id, None)
        node_meta.pop(remove_id, None)


def _apply_move_node(layout_doc: LayoutDocument, op: MoveNodeOp) -> None:
    for node_id in _collect_subtree_ids(layout_doc, op.id):
        node = _require_node(layout_doc, node_id)
        node.rect = Rect(
            x=node.rect.x + op.dx,
            y=node.rect.y + op.dy,
            w=node.rect.w,
            h=node.rect.h,
        )


def _apply_resize_node(layout_doc: LayoutDocument, op: ResizeNodeOp) -> None:
    node = _require_node(layout_doc, op.id)
    node.rect = Rect(
        x=node.rect.x,
        y=node.rect.y,
        w=node.rect.w + op.dw,
        h=node.rect.h + op.dh,
    )


def _apply_set_node_rect(layout_doc: LayoutDocument, op: SetNodeRectOp) -> None:
    node = _require_node(layout_doc, op.id)
    node.rect = _clone_rect(op.rect)


def _apply_rename_node(
    layout_doc: LayoutDocument,
    node_meta: dict[str, NodeMeta],
    op: RenameNodeOp,
) -> None:
    if op.old_id == layout_doc.screen.root:
        layout_doc.screen.root = op.new_id
    if op.new_id in layout_doc.nodes:
        raise UiLayoutError(f"Cannot rename '{op.old_id}' to '{op.new_id}': target id already exists")
    node = _require_node(layout_doc, op.old_id)
    updated = LayoutNode(
        id=op.new_id,
        kind=node.kind,
        rect=_clone_rect(node.rect),
        parent=node.parent,
        children=list(node.children),
    )
    layout_doc.nodes.pop(op.old_id)
    layout_doc.nodes[op.new_id] = updated

    if updated.parent is not None:
        parent = layout_doc.nodes[updated.parent]
        parent.children = [op.new_id if child_id == op.old_id else child_id for child_id in parent.children]

    for child_id in updated.children:
        child = layout_doc.nodes[child_id]
        child.parent = op.new_id

    for other in layout_doc.nodes.values():
        if other.id == op.new_id:
            continue
        other.children = [op.new_id if child_id == op.old_id else child_id for child_id in other.children]

    meta = node_meta.pop(op.old_id, NodeMeta())
    node_meta[op.new_id] = meta


def _apply_update_node_meta(
    layout_doc: LayoutDocument,
    node_meta: dict[str, NodeMeta],
    op: UpdateNodeMetaOp,
) -> None:
    _require_node(layout_doc, op.id)
    current = node_meta.get(op.id, NodeMeta())
    node_meta[op.id] = _merge_node_meta(current, op.patch)


def _merge_node_meta(meta: NodeMeta, patch: dict[str, Any]) -> NodeMeta:
    data = _node_meta_to_dict(meta)
    merged = _deep_merge_dict(data, patch)
    return _node_meta_from_dict(merged)


def _deep_merge_dict(base: dict[str, Any], patch: dict[str, Any]) -> dict[str, Any]:
    merged = deepcopy(base)
    for key, value in patch.items():
        if isinstance(value, dict) and isinstance(merged.get(key), dict):
            merged[key] = _deep_merge_dict(merged[key], value)
        else:
            merged[key] = deepcopy(value)
    return merged


def _node_meta_to_dict(meta: NodeMeta) -> dict[str, Any]:
    return {
        'title': meta.title,
        'role': meta.role,
        'kind': meta.kind,
        'renderer': meta.renderer,
        'data': deepcopy(meta.data),
        'bind': deepcopy(meta.bind),
        'actions': deepcopy(meta.actions),
        'view': deepcopy(meta.view),
        'binding': deepcopy(meta.binding),
        'events': deepcopy(meta.events),
        'nlp': {
            'synonyms': list(meta.nlp.synonyms),
            'description': meta.nlp.description,
            'tags': list(meta.nlp.tags),
        },
        'props': deepcopy(meta.props),
    }


def _node_meta_from_dict(data: dict[str, Any]) -> NodeMeta:
    nlp_raw = data.get('nlp') or {}
    synonyms = nlp_raw.get('synonyms') or []
    tags = nlp_raw.get('tags') or []
    if not (isinstance(synonyms, list) and all(isinstance(item, str) for item in synonyms)):
        raise UiLayoutError('Node meta patch produced invalid nlp.synonyms')
    if not (isinstance(tags, list) and all(isinstance(item, str) for item in tags)):
        raise UiLayoutError('Node meta patch produced invalid nlp.tags')
    return NodeMeta(
        title=str(data.get('title') or ''),
        role=str(data.get('role') or 'node.unknown'),
        kind=str(data.get('kind') or 'panel'),
        renderer=str(data.get('renderer') or 'utf_panel'),
        data=_require_mapping(data.get('data'), 'data'),
        bind=_require_mapping(data.get('bind'), 'bind'),
        actions=_require_mapping(data.get('actions'), 'actions'),
        view=_require_mapping(data.get('view'), 'view'),
        binding=_require_mapping(data.get('binding'), 'binding'),
        events=_require_mapping(data.get('events'), 'events'),
        nlp=NlpMeta(
            synonyms=list(synonyms),
            description=str(nlp_raw.get('description') or ''),
            tags=list(tags),
        ),
        props=_require_mapping(data.get('props'), 'props'),
    )


def _clone_layout(layout_doc: LayoutDocument) -> LayoutDocument:
    return LayoutDocument(
        screen=deepcopy(layout_doc.screen),
        nodes={
            node_id: LayoutNode(
                id=node.id,
                kind=node.kind,
                rect=_clone_rect(node.rect),
                parent=node.parent,
                children=list(node.children),
            )
            for node_id, node in layout_doc.nodes.items()
        },
    )


def _clone_node_meta(node_meta: dict[str, NodeMeta]) -> dict[str, NodeMeta]:
    return {
        node_id: _node_meta_from_dict(_node_meta_to_dict(meta))
        for node_id, meta in node_meta.items()
    }


def _clone_rect(rect: Rect) -> Rect:
    return Rect(x=rect.x, y=rect.y, w=rect.w, h=rect.h)


def _collect_subtree_ids(layout_doc: LayoutDocument, root_id: str) -> list[str]:
    ids: list[str] = []
    stack = [root_id]
    while stack:
        current = stack.pop()
        ids.append(current)
        node = layout_doc.nodes[current]
        stack.extend(node.children)
    return ids


def _require_node(layout_doc: LayoutDocument, node_id: str) -> LayoutNode:
    node = layout_doc.nodes.get(node_id)
    if node is None:
        raise UiLayoutError(f"Unknown node id '{node_id}'")
    return node


def _require_mapping(value: Any, name: str) -> dict[str, Any]:
    if value is None:
        return {}
    if not isinstance(value, dict):
        raise UiLayoutError(f"Expected mapping for '{name}'")
    return dict(value)
