"""mk — create a new child node of given type.

Usage: /mk <type> <name>
"""
from kobold_sandbox.data_store.schema import utc_now


def execute(args, user, scope, ws):
    if len(args) < 2:
        return {"error": "usage: /mk <type> <name>"}
    node_type, name = args[0], args[1]
    node_dir = scope.cwd / name
    if node_dir.exists():
        meta = ws._read_meta(node_dir) or {}
        return {"ok": True, "path": ws._rel_path(node_dir), "meta": meta, "existed": True}
    node_dir.mkdir(parents=True)
    meta = {"type": node_type, "user": user, "ts": utc_now(), "name": name}
    ws._write_meta(node_dir, meta)
    ws._write_data(node_dir, {})
    return {"ok": True, "path": ws._rel_path(node_dir), "meta": meta}
