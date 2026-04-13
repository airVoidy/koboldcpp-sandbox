"""tablechildlog - populate a virtual table from append-only child-log refs.

Usage:
  /tablechildlog <table_container_id> <source_path> <projection_root> <limit> <field1> [field2 ...] [--offset=N] [--before-ref=PATH] [--after-ref=PATH]
"""


def execute(args, user, scope, ws):
    if len(args) < 5:
        return {"error": "usage: /tablechildlog <table_container_id> <source_path> <projection_root> <limit> <field1> [field2 ...] [--offset=N] [--before-ref=PATH] [--after-ref=PATH]"}
    table_id = args[0]
    source_path = args[1]
    projection_root = args[2]
    limit_raw = args[3]
    fields = []
    offset = 0
    before_ref = ""
    after_ref = ""
    for arg in args[4:]:
        if arg.startswith("--offset="):
            try:
                offset = int(arg.split("=", 1)[1])
            except Exception:
                return {"error": "offset must be an integer"}
        elif arg.startswith("--before-ref="):
            before_ref = arg.split("=", 1)[1].strip()
        elif arg.startswith("--after-ref="):
            after_ref = arg.split("=", 1)[1].strip()
        else:
            fields.append(arg)
    try:
        limit = int(limit_raw)
    except Exception:
        return {"error": "limit must be an integer"}

    return ws.container_add_table_op(table_id, {
        "op": "load_child_log",
        "source_path": source_path,
        "projection_root": projection_root,
        "fields": fields,
        "replace": True,
        "from_end": True,
        "visible_only": True,
        "limit": limit,
        "offset": offset,
        "before_ref": before_ref,
        "after_ref": after_ref,
    }, user)
