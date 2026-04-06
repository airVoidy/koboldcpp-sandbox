"""cat — read node content (meta + data).

Usage: /cat          — current node
       /cat <name>   — child node
"""


def execute(args, user, scope, ws):
    if not args:
        meta = ws._read_meta(scope.cwd)
        data = ws._read_data(scope.cwd)
        return {"path": ws._rel_path(scope.cwd), "meta": meta, "data": data}
    name = args[0]
    target = scope.cwd / name
    if not target.is_dir():
        return {"error": f"not found: {name}"}
    meta = ws._read_meta(target)
    data = ws._read_data(target)
    return {"path": ws._rel_path(target), "meta": meta, "data": data}
