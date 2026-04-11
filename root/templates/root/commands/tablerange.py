"""tablerange - slice rows in a virtual table.

Usage:
  /tablerange <table_container_id> [limit] [offset]
  /tablerange <table_container_id> --last=<n> [--offset=<n>]
"""


def execute(args, user, scope, ws):
    if not args:
        return {"error": "usage: /tablerange <table_container_id> [limit] [offset] | --last=<n> [--offset=<n>]"}
    table_id = args[0]
    op = {"op": "slice_rows"}

    positional = []
    for arg in args[1:]:
        if arg.startswith("--last="):
            op["from_end"] = True
            op["limit"] = arg.split("=", 1)[1]
        elif arg.startswith("--offset="):
            op["offset"] = arg.split("=", 1)[1]
        else:
            positional.append(arg)

    if "limit" not in op and positional:
        op["limit"] = positional[0]
    if "offset" not in op and len(positional) > 1:
        op["offset"] = positional[1]

    return ws.container_add_table_op(table_id, op, user)
