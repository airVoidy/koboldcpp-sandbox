"""put — write a field value on current node via dot-path.

Usage: /put <path> <value>
       /put content "hello world"
       /put meta.tags ["a","b"]
"""
import json as _json


def execute(args, user, scope, ws):
    if len(args) < 2:
        return {"error": "usage: /put <path> <value>"}
    path = args[0]
    raw_value = " ".join(args[1:])

    # Try parse as JSON, fallback to string
    try:
        value = _json.loads(raw_value)
    except (ValueError, _json.JSONDecodeError):
        value = raw_value

    # Resolve: first segment may be a child name, rest = field path
    parts = path.split(".")
    target_dir = scope.cwd

    # Check if first part is a child node
    candidate = scope.cwd / parts[0]
    if candidate.is_dir() and len(parts) > 1:
        target_dir = candidate
        parts = parts[1:]

    # Read current data
    data = ws._read_data(target_dir) or {}

    # Set nested field
    obj = data
    for part in parts[:-1]:
        if part not in obj or not isinstance(obj[part], dict):
            obj[part] = {}
        obj = obj[part]
    obj[parts[-1]] = value

    ws._write_data(target_dir, data)
    return {"ok": True, "path": ws._rel_path(target_dir), "field": path, "value": value}
