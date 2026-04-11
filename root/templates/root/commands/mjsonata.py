"""mjsonata - evaluate JSONata against a message projection.

Usage:
  /mjsonata <msg_id> <expr> [--view=all|_meta|_data] [--input=view|projection|flat_store]
  /mjsonata <expr> [--view=all|_meta|_data] [--input=view|projection|flat_store]
"""


def execute(args, user, scope, ws):
    return ws.cmd_mjsonata(args, user, scope)
