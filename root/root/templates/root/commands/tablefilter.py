"""tablefilter - sugar for filtering table rows by a projection field.

Usage:
  /tablefilter <table_container_id> <field> [--equals=value] [--nonempty]
"""


def execute(args, user, scope, ws):
    if len(args) < 2:
        return {"error": "usage: /tablefilter <table_container_id> <field> [--equals=value] [--nonempty]"}
    table_id = args[0]
    field = args[1]
    op = {
        "op": "filter_rows",
        "field": field,
    }
    for arg in args[2:]:
        if arg == "--nonempty":
            op["nonempty"] = True
        elif arg.startswith("--equals="):
            op["equals"] = arg.split("=", 1)[1]
    return ws.container_add_table_op(table_id, op, user)
