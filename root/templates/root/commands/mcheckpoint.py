"""mcheckpoint - create a child checkpoint node for a message.

Usage:
  /mcheckpoint <msg_id>
"""


def execute(args, user, scope, ws):
    return ws.cmd_mcheckpoint(args, user, scope)
