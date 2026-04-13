"""cd — navigate into a child or up to parent.

Usage: /cd <name>   — go into child
       /cd ..       — go up to parent
       /cd          — show current path
"""


def execute(args, user, scope, ws):
    if not args:
        return {"ok": True, "path": ws._rel_path(scope.cwd)}
    name = args[0]
    if name == "..":
        if scope.cwd == ws.root:
            return {"error": "already at root"}
        scope.cwd = scope.cwd.parent
        return {"ok": True, "path": ws._rel_path(scope.cwd)}
    target = scope.cwd / name
    if not target.is_dir():
        for d in scope.cwd.iterdir():
            if d.is_dir() and not d.name.startswith("_"):
                meta = ws._read_meta(d)
                if meta and meta.get("name") == name:
                    target = d
                    break
        if not target.is_dir():
            return {"error": f"not found: {name}"}
    scope.cwd = target
    meta = ws._read_meta(target) or {}
    return {"ok": True, "path": ws._rel_path(target), "meta": meta}
