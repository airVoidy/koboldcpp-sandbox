"""cpatch - patch selected channel or direct child by dot-path.

Usage: /cpatch <path> <value>
"""


def execute(args, user, scope, ws):
    if len(args) < 2:
        return {"error": "usage: /cpatch <path> <value>"}
    return ws.cmd_cpatch(args, user, scope)
