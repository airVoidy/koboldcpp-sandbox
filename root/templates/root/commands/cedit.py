"""cedit - edit message content in the selected channel.

Usage: /cedit <msg_id> <text>
"""


def execute(args, user, scope, ws):
    if len(args) < 2:
        return {"error": "usage: /cedit <msg_id> <text>"}
    return ws.container_patch_selected(f"{args[0]}.content", " ".join(args[1:]), user)
