from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml

from .schema import (
    LayoutDocument,
    LayoutNode,
    NlpMeta,
    NodeMeta,
    Rect,
    ScreenSpec,
    SnapLink,
    UiNode,
    UiRuntime,
)


class UiLayoutError(ValueError):
    pass


@dataclass(slots=True)
class LoadedUi:
    layout_doc: LayoutDocument
    node_meta: dict[str, NodeMeta]


def load_ui(layout_path: str | Path, nodes_dir: str | Path) -> LoadedUi:
    layout_doc = load_layout_document(layout_path)
    node_meta = load_node_meta_dir(nodes_dir, layout_doc.nodes.keys())
    return LoadedUi(layout_doc=layout_doc, node_meta=node_meta)


def build_ui_runtime(layout_doc: LayoutDocument, node_meta: dict[str, NodeMeta]) -> UiRuntime:
    _validate_layout_document(layout_doc)
    nodes = {}
    for node_id, layout_node in layout_doc.nodes.items():
        meta = node_meta.get(node_id, NodeMeta())

        resolved = {
            'renderer': meta.renderer,
            'data': dict(meta.data),
            'bind': dict(meta.bind),
            'props': dict(meta.props),
        }

        nodes[node_id] = UiNode(
            id=layout_node.id,
            kind=layout_node.kind,
            rect=layout_node.rect,
            parent=layout_node.parent,
            children=list(layout_node.children),
            title=meta.title or layout_node.id,
            role=meta.role,
            renderer=meta.renderer,
            data=dict(meta.data),
            bind=dict(meta.bind),
            actions=dict(meta.actions),
            view=dict(meta.view),
            binding=dict(meta.binding),
            events=dict(meta.events),
            nlp=meta.nlp,
            props=dict(meta.props),
            resolved=resolved,
            snap=[],
        )

    _infer_snap_links(layout_doc, nodes)
    return UiRuntime(
        cols=layout_doc.screen.cols,
        rows=layout_doc.screen.rows,
        root_id=layout_doc.screen.root,
        nodes=nodes,
    )


def load_layout_document(layout_path: str | Path) -> LayoutDocument:
    path = Path(layout_path)
    data = _load_yaml_file(path)
    screen_raw = _require_mapping(data.get('screen'), f'{path}: screen')
    screen = ScreenSpec(
        cols=_require_int(screen_raw.get('cols'), f'{path}: screen.cols'),
        rows=_require_int(screen_raw.get('rows'), f'{path}: screen.rows'),
        root=_require_str(screen_raw.get('root'), f'{path}: screen.root'),
    )
    raw_nodes = data.get('nodes')
    if not isinstance(raw_nodes, list):
        raise UiLayoutError(f'{path}: nodes must be a list')

    nodes = {}
    for index, raw_node in enumerate(raw_nodes):
        node = _parse_layout_node(raw_node, f'{path}: nodes[{index}]')
        if node.id in nodes:
            raise UiLayoutError(f"{path}: duplicate node id '{node.id}'")
        nodes[node.id] = node

    layout_doc = LayoutDocument(screen=screen, nodes=nodes)
    _normalize_children(layout_doc)
    _validate_layout_document(layout_doc)
    return layout_doc


def load_node_meta_dir(nodes_dir: str | Path, expected_ids: Any) -> dict[str, NodeMeta]:
    path = Path(nodes_dir)
    expected = {str(item) for item in expected_ids}
    meta_by_id = {node_id: NodeMeta() for node_id in expected}
    if not path.exists():
        return meta_by_id
    if not path.is_dir():
        raise UiLayoutError(f'{path} is not a directory')

    for meta_path in path.glob('*.yaml'):
        node_id = meta_path.stem
        if node_id not in expected:
            continue
        data = _load_yaml_file(meta_path)
        meta_by_id[node_id] = _parse_node_meta(data, meta_path)

    return meta_by_id


def _parse_layout_node(raw_node: Any, ctx: str) -> LayoutNode:
    mapping = _require_mapping(raw_node, ctx)
    rect = _parse_rect(mapping.get('rect'), f'{ctx}.rect')
    parent = mapping.get('parent')
    if parent is not None and not isinstance(parent, str):
        raise UiLayoutError(f'{ctx}.parent must be a string or null')
    children_raw = mapping.get('children') or []
    if not isinstance(children_raw, list) or not all(isinstance(item, str) for item in children_raw):
        raise UiLayoutError(f'{ctx}.children must be a list of strings')
    return LayoutNode(
        id=_require_str(mapping.get('id'), f'{ctx}.id'),
        kind=_require_str(mapping.get('kind'), f'{ctx}.kind'),
        rect=rect,
        parent=parent,
        children=list(children_raw),
    )


def _parse_node_meta(data: Any, path: Path) -> NodeMeta:
    mapping = _require_mapping(data, str(path))
    nlp_raw = mapping.get('nlp') or {}
    nlp_map = _require_mapping(nlp_raw, f'{path}: nlp')
    synonyms = nlp_map.get('synonyms') or []
    tags = nlp_map.get('tags') or []
    if not isinstance(synonyms, list) or not all(isinstance(item, str) for item in synonyms):
        raise UiLayoutError(f'{path}: nlp.synonyms must be a list of strings')
    if not isinstance(tags, list) or not all(isinstance(item, str) for item in tags):
        raise UiLayoutError(f'{path}: nlp.tags must be a list of strings')
    return NodeMeta(
        title=str(mapping.get('title') or ''),
        role=str(mapping.get('role') or 'node.unknown'),
        kind=str(mapping.get('kind') or 'panel'),
        renderer=str(mapping.get('renderer') or 'utf_panel'),
        data=_coerce_mapping(mapping.get('data')),
        bind=_coerce_mapping(mapping.get('bind')),
        actions=_coerce_mapping(mapping.get('actions')),
        view=_coerce_mapping(mapping.get('view')),
        binding=_coerce_mapping(mapping.get('binding')),
        events=_coerce_mapping(mapping.get('events')),
        nlp=NlpMeta(
            synonyms=list(synonyms),
            description=str(nlp_map.get('description') or ''),
            tags=list(tags),
        ),
        props=_coerce_mapping(mapping.get('props')),
    )


def _parse_rect(raw_rect: Any, ctx: str) -> Rect:
    if not isinstance(raw_rect, list) or len(raw_rect) != 4:
        raise UiLayoutError(f'{ctx} must be [x, y, w, h]')
    values = [_require_int(value, f'{ctx}[{index}]') for index, value in enumerate(raw_rect)]
    rect = Rect(x=values[0], y=values[1], w=values[2], h=values[3])
    if rect.w <= 0 or rect.h <= 0:
        raise UiLayoutError(f'{ctx} must have positive width and height')
    return rect


def _normalize_children(layout_doc: LayoutDocument) -> None:
    for node in layout_doc.nodes.values():
        node.children = []
    for node in layout_doc.nodes.values():
        if node.parent is None:
            continue
        parent = layout_doc.nodes.get(node.parent)
        if parent is None:
            continue
        parent.children.append(node.id)


def _validate_layout_document(layout_doc: LayoutDocument) -> None:
    screen = layout_doc.screen
    if screen.root not in layout_doc.nodes:
        raise UiLayoutError(f"Root node '{screen.root}' not found in layout nodes")

    for node in layout_doc.nodes.values():
        if node.rect.w <= 0 or node.rect.h <= 0:
            raise UiLayoutError(f"Node '{node.id}' must have positive width and height")
        if not node.rect.within_bounds(screen.cols, screen.rows):
            raise UiLayoutError(
                f"Node '{node.id}' rect {node.rect.to_list()} exceeds screen bounds {screen.cols}x{screen.rows}"
            )
        if node.parent is not None:
            parent = layout_doc.nodes.get(node.parent)
            if parent is None:
                raise UiLayoutError(f"Node '{node.id}' references missing parent '{node.parent}'")
            if not parent.rect.contains_rect(node.rect):
                raise UiLayoutError(f"Node '{node.id}' is not fully contained inside parent '{parent.id}'")
        for child_id in node.children:
            if child_id not in layout_doc.nodes:
                raise UiLayoutError(f"Node '{node.id}' references missing child '{child_id}'")


def _infer_snap_links(layout_doc: LayoutDocument, nodes: dict[str, UiNode], min_overlap: int = 2) -> None:
    for node in nodes.values():
        if node.parent is None:
            continue
        parent = nodes[node.parent]
        if node.rect.x == parent.rect.x:
            node.snap.append(SnapLink(side='left', target_id=parent.id, target_side='left'))
        if node.rect.right == parent.rect.right:
            node.snap.append(SnapLink(side='right', target_id=parent.id, target_side='right'))
        if node.rect.y == parent.rect.y:
            node.snap.append(SnapLink(side='top', target_id=parent.id, target_side='top'))
        if node.rect.bottom == parent.rect.bottom:
            node.snap.append(SnapLink(side='bottom', target_id=parent.id, target_side='bottom'))

    siblings_by_parent: dict = {}
    for node in nodes.values():
        siblings_by_parent.setdefault(node.parent, []).append(node)

    for sibling_group in siblings_by_parent.values():
        for index, node in enumerate(sibling_group):
            for other in sibling_group[index + 1:]:
                _infer_sibling_snap(node, other, min_overlap=min_overlap)
                _infer_sibling_snap(other, node, min_overlap=min_overlap)


def _infer_sibling_snap(node: UiNode, other: UiNode, min_overlap: int) -> None:
    overlap_y = min(node.rect.bottom, other.rect.bottom) - max(node.rect.y, other.rect.y)
    overlap_x = min(node.rect.right, other.rect.right) - max(node.rect.x, other.rect.x)
    if node.rect.right == other.rect.x and overlap_y >= min_overlap:
        node.snap.append(SnapLink(side='right', target_id=other.id, target_side='left'))
    if node.rect.x == other.rect.right and overlap_y >= min_overlap:
        node.snap.append(SnapLink(side='left', target_id=other.id, target_side='right'))
    if node.rect.bottom == other.rect.y and overlap_x >= min_overlap:
        node.snap.append(SnapLink(side='bottom', target_id=other.id, target_side='top'))
    if node.rect.y == other.rect.bottom and overlap_x >= min_overlap:
        node.snap.append(SnapLink(side='top', target_id=other.id, target_side='bottom'))


def _load_yaml_file(path: Path) -> dict[str, Any]:
    if not path.exists():
        raise UiLayoutError(f'YAML file not found: {path}')
    with path.open('r', encoding='utf-8') as handle:
        data = yaml.safe_load(handle)
    if data is None:
        return {}
    if not isinstance(data, dict):
        raise UiLayoutError(f'{path} must contain a YAML object at the top level')
    return data


def _require_mapping(value: Any, ctx: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise UiLayoutError(f'{ctx} must be a mapping')
    return value


def _coerce_mapping(value: Any) -> dict[str, Any]:
    if value is None:
        return {}
    if not isinstance(value, dict):
        raise UiLayoutError('Expected mapping value')
    return dict(value)


def _require_str(value: Any, ctx: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise UiLayoutError(f'{ctx} must be a non-empty string')
    return value


def _require_int(value: Any, ctx: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise UiLayoutError(f'{ctx} must be an integer')
    return value
