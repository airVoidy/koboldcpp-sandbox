from __future__ import annotations

from pathlib import Path
from typing import Any
import json
import yaml


# ---- Line 10 ----
class PanelProtoError(ValueError):
    pass


# ---- Line 14 ----
def ensure_project(project_root: str | Path) -> None:
    root = Path(project_root)
    if (root / 'panels.yaml').exists():
        return
    root.mkdir(parents=True, exist_ok=True)
    (root / 'panel_text').mkdir(parents=True, exist_ok=True)
    project = default_project()
    save_project(root, project)


# ---- Line 24 ----
def default_project() -> dict[str, Any]:
    return {
        'root': 'screen',
        'panels': {
            'screen': {
                'size': [120, 40],
                'border': False,
                'label': 'screen',
                'children': [
                    {'panel': 'workers', 'at': [1, 1], 'size': [34, 20]},
                    {'panel': 'chat', 'at': [37, 1], 'size': [50, 20]},
                ],
            },
            'workers': {
                'size': [34, 20],
                'border': True,
                'label': 'workers',
            },
            'chat': {
                'size': [50, 20],
                'border': True,
                'label': 'chat',
            },
        },
        'panel_text': {
            'workers': '\n'.join([
                ' WORKERS',
                '',
                ' http://127.0.0.1:5001        +',
                '',
                ' \u25cf http://localhost:5001      x',
                '   generator',
                '',
                ' \u25cf http://192.168.1.15:5050   x',
                '   analyzer',
            ]),
            'chat': '\n'.join([
                ' Chat',
                '',
                ' assistant: ...',
                '',
                ' >',
            ]),
        },
        'zones': {
            'workers': [
                {'id': 'url_input', 'rect': [1, 2, 23, 1], 'type': 'input', 'action': 'workers_add'},
                {'id': 'add_btn', 'rect': [28, 2, 3, 1], 'type': 'button', 'action': 'workers_add'},
                {'id': 'probe_btn_0', 'rect': [1, 4, 1, 1], 'type': 'button', 'action': 'workers_probe', 'data': 0},
                {'id': 'del_btn_0', 'rect': [29, 4, 1, 1], 'type': 'button', 'action': 'workers_delete', 'data': 0},
                {'id': 'role_0', 'rect': [3, 5, 9, 1], 'type': 'input', 'action': 'workers_role', 'data': 0},
                {'id': 'probe_btn_1', 'rect': [1, 7, 1, 1], 'type': 'button', 'action': 'workers_probe', 'data': 1},
                {'id': 'del_btn_1', 'rect': [29, 7, 1, 1], 'type': 'button', 'action': 'workers_delete', 'data': 1},
                {'id': 'role_1', 'rect': [3, 8, 8, 1], 'type': 'input', 'action': 'workers_role', 'data': 1},
            ],
            'chat': [
                {'id': 'input', 'rect': [3, 4, 45, 1], 'type': 'input', 'action': 'chat_send'},
            ],
        },
        'assembly_dsl': '\n'.join([
            'action workers_add',
            '  # placeholder',
            '',
            'action workers_probe',
            '  # placeholder',
            '',
            'action workers_delete',
            '  # placeholder',
            '',
            'action chat_send',
            '  # placeholder',
        ]),
    }


# ---- Line 105 ----
def load_project(project_root: str | Path) -> dict[str, Any]:
    root = Path(project_root)
    ensure_project(root)
    with (root / 'panels.yaml').open('r', encoding='utf-8') as handle:
        panels_doc = yaml.safe_load(handle) or {}
    with (root / 'zones.yaml').open('r', encoding='utf-8') as handle:
        zones_doc = yaml.safe_load(handle) or {}
    project = {
        'root': str(panels_doc.get('root') or ''),
        'panels': dict(panels_doc.get('panels') or {}),
        'panel_text': {},
        'zones': dict(zones_doc.get('zones') or {}),
        'assembly_dsl': _read_text(root / 'assembly.dsl'),
    }
    for panel_id in project['panels'].keys():
        project['panel_text'][panel_id] = _read_text(root / 'panel_text' / f'{panel_id}.txt')
    validate_project(project)
    return project


# ---- Line 125 ----
def save_project(project_root: str | Path, project: dict[str, Any]) -> None:
    root = Path(project_root)
    root.mkdir(parents=True, exist_ok=True)
    (root / 'panel_text').mkdir(parents=True, exist_ok=True)
    validate_project(project)
    with (root / 'panels.yaml').open('w', encoding='utf-8', newline='\n') as handle:
        yaml.safe_dump({'root': project['root'], 'panels': project['panels']}, handle, sort_keys=False, allow_unicode=True)
    with (root / 'zones.yaml').open('w', encoding='utf-8', newline='\n') as handle:
        yaml.safe_dump({'zones': project['zones']}, handle, sort_keys=False, allow_unicode=True)
    for panel_id, text in project['panel_text'].items():
        (root / 'panel_text' / f'{panel_id}.txt').write_text(str(text or ''), encoding='utf-8')
    with (root / 'assembly.dsl').open('w', encoding='utf-8', newline='\n') as handle:
        handle.write(str(project.get('assembly_dsl') or ''))


# ---- Line 140 ----
def validate_project(project: dict[str, Any]) -> None:
    root = str(project.get('root') or '')
    panels = project.get('panels') or {}
    if root not in panels:
        raise PanelProtoError(f"root panel '{root}' not found")
    for panel_id, panel in panels.items():
        size = panel.get('size')
        if not (isinstance(size, list) and len(size) == 2 and all(isinstance(v, int) and v > 0 for v in size)):
            raise PanelProtoError(f"panel '{panel_id}' size must be [w, h]")
        for child in panel.get('children') or []:
            child_id = child.get('panel')
            if child_id not in panels:
                raise PanelProtoError(f"panel '{panel_id}' references missing child panel '{child_id}'")
            at = child.get('at')
            if not (isinstance(at, list) and len(at) == 2 and all(isinstance(v, int) and v >= 0 for v in at)):
                raise PanelProtoError(f"panel '{panel_id}' child placement must have at=[x,y]")


# ---- Line 158 ----
def panel_tree(project: dict[str, Any], focus_panel: str) -> list[dict[str, Any]]:
    panels = project['panels']
    ordered: list[dict[str, Any]] = []

    def visit(panel_id: str, depth: int) -> None:
        panel = panels[panel_id]
        ordered.append({
            'type': 'panel',
            'id': panel_id,
            'depth': depth,
            'size': list(panel['size']),
            'label': str(panel.get('label') or panel_id),
            'name': str(panel.get('name') or ''),
            'alias': str(panel.get('alias') or ''),
            'template': str(panel.get('template') or ''),
        })
        for index, zone in enumerate(project['zones'].get(panel_id) or []):
            ordered.append({
                'type': 'zone',
                'id': f"{panel_id}:{zone['id']}",
                'panel': panel_id,
                'zone_id': zone['id'],
                'depth': depth + 1,
                'rect': list(zone['rect']),
                'zone_type': zone.get('type') or '',
                'action': zone.get('action') or '',
                'name': str(zone.get('name') or ''),
                'alias': str(zone.get('alias') or ''),
                'template': str(zone.get('template') or ''),
            })
        for child in panel.get('children') or []:
            visit(child['panel'], depth + 1)

    visit(focus_panel, 0)
    return ordered


# ---- Line 199 ----
def compose_render(project: dict[str, Any], focus_panel: str) -> dict[str, Any]:
    panels = project['panels']
    focus = panels[focus_panel]
    fw, fh = focus['size']
    grid = [[' ' for _ in range(fw)] for _ in range(fh)]
    panel_boxes: list[dict[str, Any]] = []
    zone_boxes: list[dict[str, Any]] = []

    def draw_panel(panel_id: str, x0: int, y0: int) -> None:
        panel = panels[panel_id]
        pw, ph = panel['size']
        text = project['panel_text'].get(panel_id) or ''
        for row_index, raw_line in enumerate(text.splitlines()):
            if row_index >= ph:
                break
            for col_index, ch in enumerate(raw_line[:pw]):
                dx = x0 + col_index
                dy = y0 + row_index
                if 0 <= dx < fw and 0 <= dy < fh:
                    grid[dy][dx] = ch
        panel_boxes.append({
            'id': panel_id,
            'x': x0,
            'y': y0,
            'w': pw,
            'h': ph,
            'label': str(panel.get('label') or panel_id),
        })
        for zone in project['zones'].get(panel_id) or []:
            zx, zy, zw, zh = zone['rect']
            zone_boxes.append({
                'id': f"{panel_id}:{zone['id']}",
                'panel': panel_id,
                'zone_id': zone['id'],
                'x': x0 + zx,
                'y': y0 + zy,
                'w': zw,
                'h': zh,
                'type': zone.get('type') or '',
                'action': zone.get('action') or '',
            })
        for child in panel.get('children') or []:
            cx, cy = child['at']
            draw_panel(child['panel'], x0 + cx, y0 + cy)

    draw_panel(focus_panel, 0, 0)
    return {
        'lines': [''.join(row) for row in grid],
        'panel_boxes': panel_boxes,
        'zone_boxes': zone_boxes,
        'size': [fw, fh],
    }


# ---- Line 248 ----
def select_hit(project: dict[str, Any], focus_panel: str, x: int, y: int) -> dict[str, Any] | None:
    render = compose_render(project, focus_panel)
    for zone in reversed(render['zone_boxes']):
        if zone['x'] <= x < zone['x'] + zone['w'] and zone['y'] <= y < zone['y'] + zone['h']:
            return {'type': 'zone', 'id': zone['id'], 'panel': zone['panel'], 'zone_id': zone['zone_id']}
    for panel in reversed(render['panel_boxes']):
        if panel['x'] <= x < panel['x'] + panel['w'] and panel['y'] <= y < panel['y'] + panel['h']:
            return {'type': 'panel', 'id': panel['id']}
    return None


# ---- Line 259 ----
def selected_yaml(project: dict[str, Any], selected: dict[str, Any]) -> str:
    if selected['type'] == 'panel':
        payload = project['panels'][selected['id']]
    else:
        payload = next(zone for zone in project['zones'].get(selected['panel']) or [] if zone['id'] == selected['zone_id'])
    return yaml.safe_dump(payload, sort_keys=False, allow_unicode=True)


# ---- Line 267 ----
def selected_json(project: dict[str, Any], selected: dict[str, Any]) -> dict[str, Any]:
    if selected['type'] == 'panel':
        payload = project['panels'][selected['id']]
    else:
        payload = next(zone for zone in project['zones'].get(selected['panel']) or [] if zone['id'] == selected['zone_id'])
    return json.loads(json.dumps(payload))


# ---- Line 275 ----
def replace_panel_yaml(project: dict[str, Any], panel_id: str, yaml_text: str) -> None:
    data = yaml.safe_load(yaml_text) or {}
    if not isinstance(data, dict):
        raise PanelProtoError('panel yaml must be a mapping')
    current = project['panels'][panel_id]
    children = list(current.get('children') or [])
    project['panels'][panel_id] = dict(data)
    if 'children' not in project['panels'][panel_id]:
        project['panels'][panel_id]['children'] = children
    validate_project(project)


# ---- Line 287 ----
def replace_zone_yaml(project: dict[str, Any], panel_id: str, zone_id: str, yaml_text: str) -> None:
    data = yaml.safe_load(yaml_text) or {}
    if not isinstance(data, dict):
        raise PanelProtoError('zone yaml must be a mapping')
    zones = project['zones'].setdefault(panel_id, [])
    for index, zone in enumerate(zones):
        if zone['id'] == zone_id:
            zones[index] = dict(data)
            break
    validate_project(project)


# ---- Line 299 ----
def replace_panel_text(project: dict[str, Any], panel_id: str, text: str) -> None:
    if panel_id not in project['panels']:
        raise PanelProtoError(f"panel '{panel_id}' not found")
    project['panel_text'][panel_id] = str(text or '')


# ---- Line 305 ----
def replace_assembly_dsl(project: dict[str, Any], text: str) -> None:
    project['assembly_dsl'] = str(text or '')


# ---- Line 309 ----
def find_parent_panel(project: dict[str, Any], child_panel_id: str) -> tuple[str | None, dict[str, Any] | None]:
    for panel_id, panel in project['panels'].items():
        for child in panel.get('children') or []:
            if child.get('panel') == child_panel_id:
                return (panel_id, child)
    return (None, None)


# ---- Line 317 ----
def find_parent_panel_with_index(project: dict[str, Any], child_panel_id: str) -> tuple[str | None, int | None, dict[str, Any] | None]:
    for panel_id, panel in project['panels'].items():
        children = panel.get('children') or []
        for index, child in enumerate(children):
            if child.get('panel') == child_panel_id:
                return (panel_id, index, child)
    return (None, None, None)


# ---- Line 326 ----
def move_selected(project: dict[str, Any], selected: dict[str, Any], dx: int, dy: int) -> None:
    if selected['type'] == 'panel':
        parent_id, placement = find_parent_panel(project, selected['id'])
        if parent_id is None or placement is None:
            raise PanelProtoError('root panel cannot be moved')
        placement['at'] = [max(0, int(placement['at'][0]) + dx), max(0, int(placement['at'][1]) + dy)]
        return
    zones = project['zones'].setdefault(selected['panel'], [])
    for zone in zones:
        if zone['id'] == selected['zone_id']:
            x, y, w, h = zone['rect']
            zone['rect'] = [max(0, int(x) + dx), max(0, int(y) + dy), int(w), int(h)]
            return
    raise PanelProtoError(f"zone '{selected['zone_id']}' not found")


# ---- Line 342 ----
def resize_selected(project: dict[str, Any], selected: dict[str, Any], rect: list[int]) -> None:
    if len(rect) != 4:
        raise PanelProtoError('rect must be [x, y, w, h]')
    x, y, w, h = [int(v) for v in rect]
    if w <= 0 or h <= 0:
        raise PanelProtoError('rect size must be positive')
    if selected['type'] == 'panel':
        parent_id, placement = find_parent_panel(project, selected['id'])
        if parent_id is None or placement is None:
            project['panels'][selected['id']]['size'] = [w, h]
        else:
            placement['at'] = [max(0, x), max(0, y)]
            project['panels'][selected['id']]['size'] = [w, h]
        validate_project(project)
        return
    zones = project['zones'].setdefault(selected['panel'], [])
    for zone in zones:
        if zone['id'] == selected['zone_id']:
            zone['rect'] = [max(0, x), max(0, y), w, h]
            return
    raise PanelProtoError(f"zone '{selected['zone_id']}' not found")


# ---- Line 365 ----
def add_panel(
    project: dict[str, Any],
    parent_panel_id: str,
    panel_id: str,
    at: list[int],
    size: list[int],
    *,
    border: bool = True,
    label: str | None = None,
) -> None:
    if parent_panel_id not in project['panels']:
        raise PanelProtoError(f"parent panel '{parent_panel_id}' not found")
    if panel_id in project['panels']:
        raise PanelProtoError(f"panel '{panel_id}' already exists")
    if len(at) != 2 or len(size) != 2:
        raise PanelProtoError('panel add requires at=[x,y] and size=[w,h]')
    if size[0] <= 0 or size[1] <= 0:
        raise PanelProtoError('panel size must be positive')
    project['panels'][panel_id] = {
        'size': [int(size[0]), int(size[1])],
        'border': bool(border),
        'label': str(label or panel_id),
    }
    project['panel_text'][panel_id] = ''
    project['zones'].setdefault(panel_id, [])
    project['panels'][parent_panel_id].setdefault('children', []).append({
        'panel': panel_id,
        'at': [max(0, int(at[0])), max(0, int(at[1]))],
        'size': [int(size[0]), int(size[1])],
    })
    validate_project(project)


# ---- Line 396 ----
def add_zone(
    project: dict[str, Any],
    panel_id: str,
    zone_id: str,
    rect: list[int],
    zone_type: str,
    *,
    action: str = '',
    data: Any = None,
) -> None:
    if panel_id not in project['panels']:
        raise PanelProtoError(f"panel '{panel_id}' not found")
    if len(rect) != 4 or rect[2] <= 0 or rect[3] <= 0:
        raise PanelProtoError('zone rect must be [x, y, w, h] with positive size')
    zones = project['zones'].setdefault(panel_id, [])
    if any(zone.get('id') == zone_id for zone in zones):
        raise PanelProtoError(f"zone '{zone_id}' already exists in panel '{panel_id}'")
    entry = {
        'id': zone_id,
        'rect': [int(rect[0]), int(rect[1]), int(rect[2]), int(rect[3])],
        'type': str(zone_type or 'zone'),
        'action': str(action or ''),
    }
    if data is not None:
        entry['data'] = data
    zones.append(entry)


# ---- Line 424 ----
def delete_selected(project: dict[str, Any], selected: dict[str, Any]) -> None:
    if selected['type'] == 'panel':
        panel_id = selected['id']
        if panel_id == project['root']:
            raise PanelProtoError('root panel cannot be deleted')
        parent_id, placement = find_parent_panel(project, panel_id)
        if parent_id is None or placement is None:
            raise PanelProtoError(f"parent for panel '{panel_id}' not found")
        for child in list(project['panels'][panel_id].get('children') or []):
            delete_selected(project, {'type': 'panel', 'id': child['panel']})
        project['panels'][parent_id]['children'] = [child for child in project['panels'][parent_id].get('children') or [] if child.get('panel') != panel_id]
        project['panels'].pop(panel_id, None)
        project['panel_text'].pop(panel_id, None)
        project['zones'].pop(panel_id, None)
        return
    zones = project['zones'].setdefault(selected['panel'], [])
    project['zones'][selected['panel']] = [zone for zone in zones if zone.get('id') != selected['zone_id']]


# ---- Line 445 ----
def tree_move_up(project: dict[str, Any], panel_id: str) -> None:
    parent_id, index, _child = find_parent_panel_with_index(project, panel_id)
    if parent_id is None or index is None:
        raise PanelProtoError('root panel cannot be moved')
    if index <= 0:
        return
    children = project['panels'][parent_id].setdefault('children', [])
    children[index], children[index - 1] = children[index - 1], children[index]


# ---- Line 455 ----
def tree_move_down(project: dict[str, Any], panel_id: str) -> None:
    parent_id, index, _child = find_parent_panel_with_index(project, panel_id)
    if parent_id is None or index is None:
        raise PanelProtoError('root panel cannot be moved')
    children = project['panels'][parent_id].setdefault('children', [])
    if index >= len(children) - 1:
        return
    children[index], children[index + 1] = children[index + 1], children[index]


# ---- Line 465 ----
def tree_indent(project: dict[str, Any], panel_id: str) -> None:
    parent_id, index, child = find_parent_panel_with_index(project, panel_id)
    if parent_id is None or index is None or child is None:
        raise PanelProtoError('root panel cannot be indented')
    children = project['panels'][parent_id].setdefault('children', [])
    if index <= 0:
        raise PanelProtoError('panel has no previous sibling to indent under')
    new_parent_id = children[index - 1]['panel']
    new_parent = project['panels'][new_parent_id]
    moved = children.pop(index)
    moved['at'] = [0, 0]
    new_parent.setdefault('children', []).append(moved)
    validate_project(project)


# ---- Line 480 ----
def tree_outdent(project: dict[str, Any], panel_id: str) -> None:
    parent_id, index, child = find_parent_panel_with_index(project, panel_id)
    if parent_id is None or index is None or child is None:
        raise PanelProtoError('root panel cannot be outdented')
    grand_id, parent_index, _parent_child = find_parent_panel_with_index(project, parent_id)
    if grand_id is None or parent_index is None:
        raise PanelProtoError('panel parent is root; cannot outdent further')
    siblings = project['panels'][parent_id].setdefault('children', [])
    moved = siblings.pop(index)
    moved['at'] = [0, 0]
    grand_children = project['panels'][grand_id].setdefault('children', [])
    grand_children.insert(parent_index + 1, moved)
    validate_project(project)


# ---- Line 495 ----
def next_panel_id(project: dict[str, Any], prefix: str = 'panel') -> str:
    index = 1
    while f'{prefix}_{index}' in project['panels']:
        index += 1
    return f'{prefix}_{index}'


# ---- Line 502 ----
def _text_grid(text: str, width: int, height: int) -> list[list[str]]:
    lines = str(text or '').splitlines()
    grid: list[list[str]] = []
    for row in range(height):
        line = lines[row] if row < len(lines) else ''
        chars = list(line[:width])
        if len(chars) < width:
            chars.extend([' '] * (width - len(chars)))
        grid.append(chars)
    return grid


# ---- Line 514 ----
def _grid_to_text(grid: list[list[str]]) -> str:
    lines = [''.join(row).rstrip() for row in grid]
    while lines and not lines[-1]:
        lines.pop()
    return '\n'.join(lines)


# ---- Line 521 ----
def extract_to_child_panel(
    project: dict[str, Any],
    parent_panel_id: str,
    panel_id: str,
    rect: list[int],
) -> None:
    if parent_panel_id not in project['panels']:
        raise PanelProtoError(f"panel '{parent_panel_id}' not found")
    if len(rect) != 4:
        raise PanelProtoError('extract rect must be [x, y, w, h]')
    x, y, w, h = [int(v) for v in rect]
    if w <= 0 or h <= 0:
        raise PanelProtoError('extract rect must have positive size')
    parent = project['panels'][parent_panel_id]
    pw, ph = parent['size']
    if x < 0 or y < 0 or x + w > pw or y + h > ph:
        raise PanelProtoError('extract rect must stay inside parent panel')
    add_panel(project, parent_panel_id=parent_panel_id, panel_id=panel_id, at=[x, y], size=[w, h], border=True, label=panel_id)
    parent_grid = _text_grid(project['panel_text'].get(parent_panel_id, ''), pw, ph)
    child_grid: list[list[str]] = []
    for row in range(y, y + h):
        child_row: list[str] = []
        for col in range(x, x + w):
            child_row.append(parent_grid[row][col])
            parent_grid[row][col] = ' '
        child_grid.append(child_row)
    project['panel_text'][panel_id] = _grid_to_text(child_grid)
    project['panel_text'][parent_panel_id] = _grid_to_text(parent_grid)


# ---- Line 552 ----
def _read_text(path: Path) -> str:
    if not path.exists():
        return ''
    return path.read_text(encoding='utf-8')
