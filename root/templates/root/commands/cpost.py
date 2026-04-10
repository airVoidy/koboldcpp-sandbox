"""cpost - post into the currently selected channel.

Usage: /cpost <text>
"""


def execute(args, user, scope, ws):
    text = " ".join(args).strip()
    if not text:
        return {"error": "usage: /cpost <text>"}
    return ws.container_post_selected(text, user)
