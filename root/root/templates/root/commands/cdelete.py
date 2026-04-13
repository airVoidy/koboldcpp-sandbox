"""cdelete - soft-delete a message in the selected channel.

Usage: /cdelete <msg_id>
"""


def execute(args, user, scope, ws):
    if not args:
        return {"error": "usage: /cdelete <msg_id>"}
    return ws.container_patch_selected(f"{args[0]}._deleted", True, user)
