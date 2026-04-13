"""post — create a message-like child in current container.
Auto-numbers: msg_1, msg_2, etc.

Usage: /post <text>
"""
from kobold_sandbox.data_store.schema import utc_now


def execute(args, user, scope, ws):
    text = " ".join(args) if args else ""
    slot_name = ws._next_slot_id(scope.cwd, "msg")
    slot_dir = scope.cwd / slot_name
    slot_dir.mkdir()
    meta = {"type": "message", "user": user, "ts": utc_now()}
    ws._write_meta(slot_dir, meta)
    ws._write_data(slot_dir, {"content": text})
    return {"ok": True, "path": ws._rel_path(slot_dir), "meta": meta, "data": {"content": text}}
