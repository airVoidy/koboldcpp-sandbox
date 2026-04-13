"""tablechildren - populate a virtual table from direct FS children.

Usage:
  /tablechildren <table_container_id> <source_path> <projection_root> <field1> [field2 ...]
"""


def execute(args, user, scope, ws):
    if len(args) < 4:
        return {"error": "usage: /tablechildren <table_container_id> <source_path> <projection_root> <field1> [field2 ...]"}
    table_id = args[0]
    source_path = args[1]
    projection_root = args[2]
    fields = args[3:]
    return ws.container_add_table_op(table_id, {
        "op": "load_children",
        "source_path": source_path,
        "projection_root": projection_root,
        "fields": fields,
        "replace": True,
    }, user)
