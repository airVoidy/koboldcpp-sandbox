"""cmkchannel - create and select a channel via runtime container state.

Usage: /cmkchannel <name>
"""


def execute(args, user, scope, ws):
    if not args:
        return {"error": "usage: /cmkchannel <name>"}
    return ws.container_create_channel(args[0], user, scope)
