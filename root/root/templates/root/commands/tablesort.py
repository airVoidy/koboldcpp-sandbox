"""tablesort - sugar for sorting table rows by a projection field.

Usage:
  /tablesort <table_container_id> <field> [asc|desc]
"""


def execute(args, user, scope, ws):
    if len(args) < 2:
        return {"error": "usage: /tablesort <table_container_id> <field> [asc|desc]"}
    table_id = args[0]
    field = args[1]
    order = args[2] if len(args) > 2 else "asc"
    return ws.container_add_table_op(table_id, {
        "op": "sort_rows",
        "field": field,
        "order": order,
    }, user)
