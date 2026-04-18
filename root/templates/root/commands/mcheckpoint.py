"""mcheckpoint - create projection checkpoint for a message slot.

Usage:
  /mcheckpoint           (inside message node)
  /mcheckpoint <msg_id>  (inside channel)
"""


def execute(args, user, scope, ws):
    return ws.cmd_mcheckpoint(args, user, scope)
