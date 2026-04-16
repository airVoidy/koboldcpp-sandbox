"""mkprojection - create a local runtime projection container.

Usage:
  /mkprojection <container_id> <source_path> <local_root> <field1> [field2 ...]
"""


def execute(args, user, scope, ws):
    if len(args) < 4:
        return {"error": "usage: /mkprojection <container_id> <source_path> <local_root> <field1> [field2 ...]"}
    container_id = args[0]
    source_path = args[1]
    local_root = args[2]
    fields = args[3:]
    return ws.container_create_projection(container_id, source_path, local_root, fields, user)
