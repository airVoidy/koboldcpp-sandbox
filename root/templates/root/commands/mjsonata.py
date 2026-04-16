"""mjsonata - evaluate JSONata expression against message projection.

Usage:
  /mjsonata <expr>                         (inside message)
  /mjsonata <msg_id> <expr>                (inside channel)
  /mjsonata <msg_id> -- <raw expression>   (raw tail mode)

Options:
  --view=all|_meta|_data     which view to filter (default: all)
  --input=view|projection|flat_store  what to pass to JSONata (default: view)
"""


def execute(args, user, scope, ws):
    return ws.cmd_mjsonata(args, user, scope)
