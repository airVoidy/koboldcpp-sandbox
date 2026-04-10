"""materialize - build a runtime container sandbox.

Usage: /materialize <container_id>
"""


def execute(args, user, scope, ws):
    if not args:
        return {"error": "usage: /materialize <container_id>"}
    container_id = args[0]
    ws._append_container_log(container_id, {
        "cmd": "materialize",
        "args": [container_id],
        "user": user,
        "ts": __import__("time").time(),
    })
    return ws.materialize_container(container_id)
