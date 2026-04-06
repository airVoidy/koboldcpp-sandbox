"""pick — select an object by name in current scope.
Sets scope.cwd to the target node.

Usage: /pick <name>
"""

def execute(args, user, scope, ws):
    if not args:
        return {"error": "usage: /pick <name>"}
    name = args[0]
    target = scope.cwd / name
    if not target.is_dir():
        # Search by meta.name
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
