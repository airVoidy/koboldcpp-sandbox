"""projectionexec - append a generic rule object to a projection container.

Usage:
  /projectionexec <container_id> <rule-object>

Example:
  /projectionexec msg_proj {"path":"display","op":"concat","args":["_meta.user","_data.content"],"sep":": "}
  /projectionexec msg_proj {path: display, op: concat, args: [_meta.user, _data.content], sep: ": "}
"""

import json
import yaml


def execute(args, user, scope, ws):
    if len(args) < 2:
        return {"error": "usage: /projectionexec <container_id> <json-rule>"}
    container_id = args[0]
    raw_rule = " ".join(args[1:]).strip()
    if not raw_rule:
        return {"error": "rule-object is required"}
    try:
        rule = json.loads(raw_rule)
    except Exception:
        try:
            rule = yaml.safe_load(raw_rule)
        except Exception as exc:
            return {"error": f"invalid projection rule object: {exc}"}
    return ws.container_add_projection_rule(container_id, rule, user)
