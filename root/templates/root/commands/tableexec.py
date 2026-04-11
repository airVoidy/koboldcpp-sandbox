"""tableexec - append a generic op object to a table container.

Usage:
  /tableexec <container_id> <op-object>
"""

import json
import yaml


def execute(args, user, scope, ws):
    if len(args) < 2:
        return {"error": "usage: /tableexec <container_id> <op-object>"}
    container_id = args[0]
    raw_op = " ".join(args[1:]).strip()
    if not raw_op:
        return {"error": "op-object is required"}
    try:
        op_spec = json.loads(raw_op)
    except Exception:
        try:
            op_spec = yaml.safe_load(raw_op)
        except Exception as exc:
            return {"error": f"invalid table op object: {exc}"}
    return ws.container_add_table_op(container_id, op_spec, user)
