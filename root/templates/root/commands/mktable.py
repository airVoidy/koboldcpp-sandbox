"""mktable - create a local runtime virtual table container.

Usage:
  /mktable <container_id> <local_root> <col1> [col2 ...]
"""


def execute(args, user, scope, ws):
    if len(args) < 2:
        return {"error": "usage: /mktable <container_id> <local_root> <col1> [col2 ...]"}
    container_id = args[0]
    local_root = args[1]
    columns = args[2:]
    return ws.container_create_table(container_id, local_root, columns, user)
