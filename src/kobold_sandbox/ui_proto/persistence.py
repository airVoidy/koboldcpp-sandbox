from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import yaml

from .schema import LayoutDocument, NodeMeta


def save_ui(
    layout_path: str | Path,
    nodes_dir: str | Path,
    layout_doc: LayoutDocument,
    node_meta: dict[str, NodeMeta],
) -> None:
    save_layout_document(layout_path, layout_doc)
    save_node_meta_dir(nodes_dir, layout_doc, node_meta)


def save_layout_document(
    layout_path: str | Path,
    layout_doc: LayoutDocument,
) -> None:
    path = Path(layout_path)
    path.parent.mkdir(parents=True, exist_ok=True)

    payload = {
        'screen': {
            'cols': layout_doc.screen.cols,
            'rows': layout_doc.screen.rows,
            'root': layout_doc.screen.root,
        },
        'nodes': [
            _layout_node_to_dict(layout_doc.nodes[node_id])
            for node_id in _sort_layout_ids(layout_doc)
        ],
    }

    with path.open('w', encoding='utf-8', newline='\n') as handle:
        yaml.safe_dump(payload, handle, sort_keys=False, allow_unicode=True)


def save_node_meta_dir(
    nodes_dir: str | Path,
    layout_doc: LayoutDocument,
    node_meta: dict[str, NodeMeta],
) -> None:
    path = Path(nodes_dir)
    path.mkdir(parents=True, exist_ok=True)

    live_ids = set(layout_doc.nodes.keys())

    for pattern in ('*.yaml', '*.json'):
        for meta_path in path.glob(pattern):
            if meta_path.stem not in live_ids:
                meta_path.unlink()

    for node_id in _sort_layout_ids(layout_doc):
        meta = node_meta.get(node_id, NodeMeta())
        payload = _node_meta_to_dict(meta)

        meta_yaml_path = path / f'{node_id}.yaml'
        with meta_yaml_path.open('w', encoding='utf-8', newline='\n') as handle:
            yaml.safe_dump(payload, handle, sort_keys=False, allow_unicode=True)

        meta_json_path = path / f'{node_id}.json'
        with meta_json_path.open('w', encoding='utf-8', newline='\n') as handle:
            json.dump(payload, handle, ensure_ascii=False, indent=2)
            handle.write('\n')


def _layout_node_to_dict(node: Any) -> dict[str, Any]:
    payload = {
        'id': node.id,
        'kind': node.kind,
        'rect': node.rect.to_list(),
    }

    if node.parent is not None:
        payload['parent'] = node.parent

    if node.children:
        payload['children'] = list(node.children)

    return payload


def _node_meta_to_dict(meta: NodeMeta) -> dict[str, Any]:
    return {
        'title': meta.title,
        'role': meta.role,
        'kind': meta.kind,
        'renderer': meta.renderer,
        'data': dict(meta.data),
        'bind': dict(meta.bind),
        'actions': dict(meta.actions),
        'view': dict(meta.view),
        'binding': dict(meta.binding),
        'events': dict(meta.events),
        'nlp': {
            'synonyms': list(meta.nlp.synonyms),
            'description': meta.nlp.description,
            'tags': list(meta.nlp.tags),
        },
        'props': dict(meta.props),
    }


def _sort_layout_ids(layout_doc: LayoutDocument) -> list[str]:
    ordered: list[str] = []
    root_id = layout_doc.screen.root
    seen: set[str] = set()

    def visit(node_id: str) -> None:
        if node_id in seen:
            return
        seen.add(node_id)
        ordered.append(node_id)
        node = layout_doc.nodes[node_id]
        for child_id in node.children:
            if child_id in layout_doc.nodes:
                visit(child_id)

    if root_id in layout_doc.nodes:
        visit(root_id)

    for node_id in sorted(layout_doc.nodes.keys()):
        if node_id not in seen:
            visit(node_id)

    return ordered
