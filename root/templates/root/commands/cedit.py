"""cedit - edit message content in the selected channel.

Usage: /cedit <msg_id> <text>
"""


def execute(args, user, scope, ws):
    if len(args) < 2:
        return {"error": "usage: /cedit <msg_id> <text>"}
    msg_id = args[0]
    content = " ".join(args[1:])
    return ws.cmd_cpatch([f"{msg_id}.content", content], user, scope)
