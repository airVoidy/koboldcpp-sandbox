"""creact - toggle a reaction on a message in the selected channel.

Usage: /creact <msg_id> <emoji>
"""


def execute(args, user, scope, ws):
    if len(args) < 2:
        return {"error": "usage: /creact <msg_id> <emoji>"}
    return ws.cmd_creact(args[:2], user, scope)
