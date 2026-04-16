"""cselect - select active channel in the runtime selector container.

Usage: /cselect <channel_name>
"""


def execute(args, user, scope, ws):
    if not args:
        return {"error": "usage: /cselect <channel_name>"}
    return ws.cmd_select(args[:1], user, scope)
