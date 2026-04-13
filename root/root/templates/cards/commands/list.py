"""list — show children of current container.

Usage: /list
"""


def execute(args, user, scope, ws):
    children = []
    for d in sorted(scope.cwd.iterdir(), key=lambda p: p.name):
        if d.is_dir() and not d.name.startswith("_"):
            meta = ws._read_meta(d)
            entry = {"name": d.name, "path": ws._rel_path(d)}
            if meta:
                entry["type"] = meta.get("type", "?")
            children.append(entry)
    return {"children": children, "cwd": ws._rel_path(scope.cwd)}
