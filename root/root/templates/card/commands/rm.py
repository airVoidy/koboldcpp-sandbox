"""rm — delete a child node.

Usage: /rm <name>
"""
import shutil as _shutil


def execute(args, user, scope, ws):
    if not args:
        return {"error": "usage: /rm <name>"}
    name = args[0]
    target = scope.cwd / name
    if not target.is_dir():
        return {"error": f"not found: {name}"}
    _shutil.rmtree(target)
    return {"ok": True, "removed": name}
