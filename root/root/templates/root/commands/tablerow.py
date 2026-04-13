"""tablerow - sugar to add a projection container as a row in a virtual table.

Usage:
  /tablerow <table_container_id> <projection_container_id> [row_key]
"""


def execute(args, user, scope, ws):
    if len(args) < 2:
        return {"error": "usage: /tablerow <table_container_id> <projection_container_id> [row_key]"}
    table_id = args[0]
    projection_id = args[1]
    row_key = args[2] if len(args) > 2 else projection_id
    return ws.container_add_table_op(table_id, {
        "op": "add_projection_row",
        "projection": projection_id,
        "row_key": row_key,
    }, user)
