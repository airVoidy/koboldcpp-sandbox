"""cpatch - patch selected channel or direct child by dot-path.

Usage: /cpatch <path> <value>
"""
import json as _json


def execute(args, user, scope, ws):
    if len(args) < 2:
        return {"error": "usage: /cpatch <path> <value>"}
    raw_path = args[0]
    raw_value = " ".join(args[1:])
    try:
        value = _json.loads(raw_value)
    except Exception:
        value = raw_value
    return ws.container_patch_selected(raw_path, value, user)
