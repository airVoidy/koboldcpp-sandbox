from __future__ import annotations
from pathlib import Path
from typing import Any
import json
import yaml


# ── line 10 ──
class ReactiveUiError(ValueError):
    pass


# ── line 14 ──
def ensure_project(project_root: str | Path) -> None:
    root = Path(project_root)
    aabb_path = root / 'aabb.yaml'
    if aabb_path.exists():
        return
    root.mkdir(parents=True, exist_ok=True)
    (root / 'text').mkdir(parents=True, exist_ok=True)
    project = default_project()
    save_project(root, project)


# ── line 25 ──
def default_project() -> dict[str, Any]:
    cols = 30
    rows = 29
    base = '\n'.join([
        ' ' * cols,
        ' WORKERS'.ljust(cols),
        ' ' * cols,
        ' ' * cols,
        ' http://127.0.0.1:5001     +'.ljust(cols),
        ' ' * cols,
        ' ' * cols,
        ' ' * cols,
        ' ' * cols,
        ' \u25cf http://localhost:5001   x'.ljust(cols),
        ' ' * cols,
        '   generator'.ljust(cols),
        ' ' * cols,
        ' ' * cols,
        ' ' * cols,
        ' ' * cols,
        ' \u25cf http://192.168.1.15:5050 x'.ljust(cols),
        ' ' * cols,
        '   analyzer'.ljust(cols),
        ' ' * cols,
        ' ' * cols,
        ' ' * cols,
        ' ' * cols,
        ' ' * cols,
        ' ' * cols,
        ' ' * cols,
        ' ' * cols,
        ' ' * cols,
        ' ' * cols,
    ])

    events = (
        'on workers.add_button.OnClick\n'
        '  POST /api/behavior/agents {\n'
        '    endpoint: value(workers.new_url)\n'
        '  }\n'
        '  REFRESH workers.panel\n'
        '\n'
        'on worker.delete_button.OnClick\n'
        '  POST /api/behavior/agents/remove {\n'
        '    endpoint: text(worker.endpoint)\n'
        '  }\n'
        '  REFRESH workers.panel\n'
        '\n'
        'on worker.role_input.OnSubmit\n'
        '  POST /api/behavior/agents/update {\n'
        '    endpoint: text(worker.endpoint),\n'
        '    role: value(worker.role_input)\n'
        '  }\n'
        '  REFRESH workers.panel\n'
    )

    return {
        'screen': {
            'cols': cols,
            'rows': rows,
            'root': 'workers_panel',
        },
        'nodes': [
            {
                'id': 'workers_panel',
                'rect': [0, 0, 30, 29],
                'name': 'workers',
                'alias': 'panel',
                'children': [*('workers_label', 'new_worker_url', 'add_worker_button', 'worker_card_1', 'worker_card_2')],
            },
            {
                'id': 'workers_label',
                'parent': 'workers_panel',
                'rect': [*(1, 1, 10, 1)],
                'name': 'workers',
                'alias': 'label',
                'meta': {'editable': False},
            },
            {
                'id': 'new_worker_url',
                'parent': 'workers_panel',
                'rect': [*(1, 4, 23, 3)],
                'name': 'workers',
                'alias': 'new_url',
                'meta': {'editable': True, 'ui_hint': 'input'},
            },
            {
                'id': 'add_worker_button',
                'parent': 'workers_panel',
                'rect': [*(24, 4, 4, 3)],
                'name': 'workers',
                'alias': 'add_button',
                'meta': {'editable': False, 'ui_hint': 'button'},
            },
            {
                'id': 'worker_card_1',
                'parent': 'workers_panel',
                'rect': [*(1, 9, 27, 6)],
                'name': 'worker_card',
                'alias': 'first',
                'children': [*('worker_status_1', 'worker_endpoint_1', 'worker_role_1', 'worker_delete_1')],
            },
            {
                'id': 'worker_status_1',
                'parent': 'worker_card_1',
                'rect': [*(2, 10, 2, 1)],
                'name': 'worker',
                'alias': 'status',
            },
            {
                'id': 'worker_endpoint_1',
                'parent': 'worker_card_1',
                'rect': [*(5, 10, 20, 1)],
                'name': 'worker',
                'alias': 'endpoint',
            },
            {
                'id': 'worker_role_1',
                'parent': 'worker_card_1',
                'rect': [*(5, 12, 12, 2)],
                'name': 'worker',
                'alias': 'role_input',
                'meta': {'editable': True, 'ui_hint': 'input'},
            },
            {
                'id': 'worker_delete_1',
                'parent': 'worker_card_1',
                'rect': [*(25, 10, 2, 1)],
                'name': 'worker',
                'alias': 'delete_button',
                'meta': {'ui_hint': 'button'},
            },
            {
                'id': 'worker_card_2',
                'parent': 'workers_panel',
                'rect': [*(1, 16, 27, 6)],
                'name': 'worker_card',
                'alias': 'second',
                'children': [*('worker_status_2', 'worker_endpoint_2', 'worker_role_2', 'worker_delete_2')],
            },
            {
                'id': 'worker_status_2',
                'parent': 'worker_card_2',
                'rect': [*(2, 17, 2, 1)],
                'name': 'worker',
                'alias': 'status',
            },
            {
                'id': 'worker_endpoint_2',
                'parent': 'worker_card_2',
                'rect': [*(5, 17, 20, 1)],
                'name': 'worker',
                'alias': 'endpoint',
            },
            {
                'id': 'worker_role_2',
                'parent': 'worker_card_2',
                'rect': [*(5, 19, 12, 2)],
                'name': 'worker',
                'alias': 'role_input',
                'meta': {'editable': True, 'ui_hint': 'input'},
            },
            {
                'id': 'worker_delete_2',
                'parent': 'worker_card_2',
                'rect': [*(25, 17, 2, 1)],
                'name': 'worker',
                'alias': 'delete_button',
                'meta': {'ui_hint': 'button'},
            },
        ],
        'layers': {
            'base': base,
        },
        'events_dsl': events,
    }


# ── line 204 ──
def load_project(project_root: str | Path) -> dict[str, Any]:
    root = Path(project_root)
    ensure_project(root)
    aabb_path = root / 'aabb.yaml'
    with aabb_path.open('r', encoding='utf-8') as handle:
        data = yaml.safe_load(handle) or {}
    if not isinstance(data, dict):
        raise ReactiveUiError('aabb.yaml must be a mapping')
    project = {
        'screen': dict(data.get('screen') or {}),
        'nodes': list(data.get('nodes') or []),
        'layers': {
            'base': _read_text(root / 'text' / 'base.txt'),
        },
        'events_dsl': _read_text(root / 'events.dsl'),
    }
    normalize_project(project)
    validate_project(project)
    return project


# ── line 225 ──
def save_project(project_root: str | Path, project: dict[str, Any]) -> None:
    root = Path(project_root)
    root.mkdir(parents=True, exist_ok=True)
    (root / 'text').mkdir(parents=True, exist_ok=True)
    normalize_project(project)
    validate_project(project)
    aabb_payload = {
        'screen': project['screen'],
        'nodes': project['nodes'],
    }
    with (root / 'aabb.yaml').open('w', encoding='utf-8', newline='\n') as handle:
        yaml.safe_dump(aabb_payload, handle, sort_keys=False, allow_unicode=True)
    (root / 'text' / 'base.txt').write_text(
        str(project['layers'].get('base') or ''), encoding='utf-8'
    )
    with (root / 'base.json').open('w', encoding='utf-8', newline='\n') as handle:
        json.dump(build_base_json(project), handle, ensure_ascii=False, indent=2)
        handle.write('\n')
    (root / 'events.dsl').write_text(
        str(project.get('events_dsl') or ''), encoding='utf-8'
    )


# ── line 241 ──
def normalize_project(project: dict[str, Any]) -> None:
    nodes = project.get('nodes') or []
    by_id = {str(node.get('id')): node for node in nodes if node.get('id')}
    for node in nodes:
        node['id'] = str(node.get('id') or '')
        node['name'] = str(node.get('name') or '')
        node['alias'] = str(node.get('alias') or '')
        node['meta'] = dict(node.get('meta') or {})
        node['children'] = []
    for node in nodes:
        parent_id = node.get('parent')
        if not parent_id:
            continue
        if parent_id not in by_id:
            continue
        by_id[parent_id]['children'].append(node['id'])


# ── line 256 ──
def validate_project(project: dict[str, Any]) -> None:
    screen = project.get('screen') or {}
    cols = int(screen.get('cols') or 0)
    rows = int(screen.get('rows') or 0)
    root_id = str(screen.get('root') or '')
    if cols <= 0 or rows <= 0:
        raise ReactiveUiError('screen cols/rows must be positive')
    nodes = project.get('nodes') or []
    by_id = {node['id']: node for node in nodes}
    if root_id not in by_id:
        raise ReactiveUiError(f"root node '{root_id}' not found")
    for node in nodes:
        rect = node.get('rect')
        if not (isinstance(rect, list) and len(rect) == 4 and all(isinstance(v, int) for v in rect)):
            raise ReactiveUiError(f"node '{node['id']}' rect must be [x, y, w, h]")
        x, y, w, h = rect
        if w <= 0 or h <= 0:
            raise ReactiveUiError(f"node '{node['id']}' rect must have positive size")
        if x < 0 or y < 0 or x + w > cols or y + h > rows:
            raise ReactiveUiError(f"node '{node['id']}' exceeds screen bounds")
        parent_id = node.get('parent')
        if not parent_id:
            continue
        if parent_id not in by_id:
            raise ReactiveUiError(f"node '{node['id']}' has missing parent '{parent_id}'")
        px, py, pw, ph = by_id[parent_id]['rect']
        if not (px <= x and py <= y and x + w <= px + pw and y + h <= py + ph):
            raise ReactiveUiError(f"node '{node['id']}' is not inside parent '{parent_id}'")


# ── line 285 ──
def project_tree(project: dict[str, Any], focus_id: str) -> list[dict[str, Any]]:
    by_id = {node['id']: node for node in project['nodes']}
    focus = by_id[focus_id]
    fx, fy, _, _ = focus['rect']
    ordered = []

    def visit(node_id: str, depth: int) -> None:
        node = by_id[node_id]
        x, y, w, h = node['rect']
        ordered.append({
            'id': node['id'],
            'name': node.get('name') or '',
            'alias': node.get('alias') or '',
            'rect': [x - fx, y - fy, w, h],
            'depth': depth,
            'children': list(node.get('children') or []),
        })
        for child_id in (node.get('children') or []):
            if child_id in by_id:
                visit(child_id, depth + 1)

    visit(focus_id, 0)
    return ordered


# ── line 312 ──
def resolve_focus(project: dict[str, Any], focus_id: str | None) -> str:
    by_id = {node['id']: node for node in project['nodes']}
    if focus_id and focus_id in by_id:
        return focus_id
    return project['screen']['root']


# ── line 319 ──
def is_descendant(project: dict[str, Any], node_id: str, ancestor_id: str) -> bool:
    by_id = {node['id']: node for node in project['nodes']}
    current = by_id.get(node_id)
    while current is not None:
        if current['id'] == ancestor_id:
            return True
        parent_id = current.get('parent')
        current = by_id.get(parent_id) if parent_id else None
    return False


# ── line 330 ──
def local_rect(project: dict[str, Any], rect: list[int], focus_id: str) -> list[int]:
    by_id = {node['id']: node for node in project['nodes']}
    fx, fy, _, _ = by_id[focus_id]['rect']
    return [rect[0] - fx, rect[1] - fy, rect[2], rect[3]]


# ── line 336 ──
def global_rect(project: dict[str, Any], rect: list[int], focus_id: str) -> list[int]:
    by_id = {node['id']: node for node in project['nodes']}
    fx, fy, _, _ = by_id[focus_id]['rect']
    return [rect[0] + fx, rect[1] + fy, rect[2], rect[3]]


# ── line 342 ──
def pick_node(project: dict[str, Any], x: int, y: int, focus_id: str) -> str | None:
    by_id = {node['id']: node for node in project['nodes']}
    fx, fy, _, _ = by_id[focus_id]['rect']
    gx = fx + x
    gy = fy + y
    hits = []
    for node in project['nodes']:
        if not is_descendant(project, node['id'], focus_id):
            continue
        nx, ny, nw, nh = node['rect']
        if not (nx <= gx < nx + nw):
            continue
        if not (ny <= gy < ny + nh):
            continue
        area = nw * nh
        depth = project_tree(project, focus_id)
        depth_value = next((item['depth'] for item in depth if item['id'] == node['id']), 0)
        hits.append((area, -depth_value, node['id']))
    if not hits:
        return None
    hits.sort()
    return hits[0][2]


# ── line 363 ──
def compose_layers(project: dict[str, Any], focus_id: str) -> list[str]:
    by_id = {node['id']: node for node in project['nodes']}
    cols = by_id[focus_id]['rect'][2]
    rows = by_id[focus_id]['rect'][3]
    layers = [_normalize_layer(project['layers'].get('base') or '', cols, rows)]
    grid = [[' ' for _ in range(cols)] for _ in range(rows)]
    for layer in layers:
        for y in range(rows):
            for x in range(cols):
                ch = layer[y][x]
                if ch != ' ':
                    grid[y][x] = ch
    return [''.join(row) for row in grid]


# ── line 378 ──
def selected_node_yaml(project: dict[str, Any], node_id: str) -> str:
    node = next(node for node in project['nodes'] if node['id'] == node_id)
    return yaml.safe_dump(node, sort_keys=False, allow_unicode=True)


# ── line 383 ──
def selected_node_json(project: dict[str, Any], node_id: str) -> dict[str, Any]:
    node = next(node for node in project['nodes'] if node['id'] == node_id)
    return json.loads(json.dumps(node))


# ── line 388 ──
def replace_node_from_yaml(project: dict[str, Any], node_id: str, yaml_text: str) -> None:
    try:
        data = yaml.safe_load(yaml_text) or {}
    except yaml.YAMLError as exc:
        raise ReactiveUiError(f'invalid YAML: {exc}') from exc

    if not isinstance(data, dict):
        raise ReactiveUiError('node YAML must be a mapping')
    if str(data.get('id') or node_id) != node_id:
        raise ReactiveUiError('node id cannot be changed in-place')
    for node in project['nodes']:
        if node['id'] == node_id:
            parent_id = node.get('parent')
            children = list(node.get('children') or [])
            node.clear()
            node.update(data)
            node['id'] = node_id
            if 'parent' not in node and parent_id is not None:
                node['parent'] = parent_id
            if 'children' not in node and children:
                node['children'] = children
            break
    normalize_project(project)
    validate_project(project)


# ── line 413 ──
def next_id(project: dict[str, Any], base: str) -> str:
    existing = {node['id'] for node in project['nodes']}
    candidate = base
    if candidate not in existing:
        return candidate
    index = 1
    while f'{base}_{index}' in existing:
        index += 1
    return f'{base}_{index}'


# ── line 424 ──
def add_node(project: dict[str, Any], parent_id: str, node_id: str, rect: list[int], *, kind: str = 'panel') -> None:
    if any(node['id'] == node_id for node in project['nodes']):
        raise ReactiveUiError(f"node '{node_id}' already exists")
    project['nodes'].append({
        'id': node_id,
        'parent': parent_id,
        'rect': list(rect),
        'name': node_id,
        'alias': kind,
        'meta': {'kind': kind},
    })
    normalize_project(project)
    validate_project(project)


# ── line 441 ──
def move_node(project: dict[str, Any], node_id: str, rect: list[int]) -> None:
    by_id = {node['id']: node for node in project['nodes']}
    node = by_id[node_id]
    old_rect = list(node['rect'])
    dx = rect[0] - node['rect'][0]
    dy = rect[1] - node['rect'][1]
    if dx != 0 or dy != 0:
        project['layers']['base'] = shift_text_block(
            project['layers'].get('base') or '',
            project['screen']['cols'],
            project['screen']['rows'],
            old_rect,
            dx,
            dy,
        )
    for current_id in collect_subtree_ids(project, node_id):
        current = by_id[current_id]
        x, y, w, h = current['rect']
        current['rect'] = [x + dx, y + dy, w, h]
    validate_project(project)


# ── line 463 ──
def resize_node(project: dict[str, Any], node_id: str, rect: list[int]) -> None:
    by_id = {node['id']: node for node in project['nodes']}
    by_id[node_id]['rect'] = list(rect)
    validate_project(project)


# ── line 469 ──
def delete_node(project: dict[str, Any], node_id: str, delete_subtree: bool = False) -> None:
    by_id = {node['id']: node for node in project['nodes']}
    node = by_id.get(node_id)
    if node is None:
        raise ReactiveUiError(f"unknown node '{node_id}'")
    if node_id == project['screen']['root']:
        raise ReactiveUiError('cannot delete root')
    if delete_subtree:
        ids_to_delete = collect_subtree_ids(project, node_id)
    else:
        ids_to_delete = [node_id]
    if not delete_subtree and node.get('children'):
        raise ReactiveUiError('node has children; use subtree delete')
    project['nodes'] = [item for item in project['nodes'] if item['id'] not in ids_to_delete]
    normalize_project(project)
    validate_project(project)


# ── line 484 ──
def collect_subtree_ids(project: dict[str, Any], root_id: str) -> list[str]:
    by_id = {node['id']: node for node in project['nodes']}
    ids = []
    stack = [root_id]
    while stack:
        current_id = stack.pop()
        ids.append(current_id)
        stack.extend(by_id[current_id].get('children') or [])
    return ids


# ── line 495 ──
def save_layers(project: dict[str, Any], base: str, events_dsl: str) -> None:
    project['layers']['base'] = base
    project['events_dsl'] = events_dsl


# ── line 500 ──
def build_base_json(project: dict[str, Any]) -> dict[str, Any]:
    base = project['layers'].get('base') or ''
    cols = project['screen']['cols']
    rows = project['screen']['rows']
    grid = _normalize_layer(base, cols, rows)
    items = []
    for node in project['nodes']:
        x, y, w, h = node['rect']
        lines = [''.join(grid[row][x:x + w]).rstrip() for row in range(y, min(y + h, rows))]
        items.append({
            'id': node['id'],
            'name': node.get('name') or '',
            'alias': node.get('alias') or '',
            'rect': list(node['rect']),
            'text_lines': lines,
            'text': '\n'.join(line for line in lines if line).strip(),
        })
    return {
        'screen': dict(project['screen']),
        'items': items,
    }


# ── line 525 ──
def shift_text_block(text: str, cols: int, rows: int, rect: list[int], dx: int, dy: int) -> str:
    grid = _normalize_layer(text, cols, rows)
    x, y, w, h = rect
    block = [row[x:x + w] for row in grid[y:y + h]]
    for row in range(y, min(y + h, rows)):
        for col in range(x, min(x + w, cols)):
            grid[row][col] = ' '
    for row_offset, block_row in enumerate(block):
        for col_offset, ch in enumerate(block_row):
            target_x = x + dx + col_offset
            target_y = y + dy + row_offset
            if not (0 <= target_x < cols):
                continue
            if not (0 <= target_y < rows):
                continue
            if ch != ' ':
                grid[target_y][target_x] = ch
    return '\n'.join(''.join(row) for row in grid)


# ── line 541 ──
def _read_text(path: Path) -> str:
    if not path.exists():
        return ''
    return path.read_text(encoding='utf-8')


# ── line 547 ──
def _normalize_layer(text: str, cols: int, rows: int) -> list[list[str]]:
    lines = str(text or '').splitlines()
    while len(lines) < rows:
        lines.append('')
    normalized = []
    for line in lines[:rows]:
        row = list(line[:cols].ljust(cols))
        normalized.append(row)
    return normalized
