"""cmkchannel - create and select a channel via runtime container state.

Usage: /cmkchannel <name>
"""


def execute(args, user, scope, ws):
    if not args:
        return {"error": "usage: /cmkchannel <name>"}
    result = ws.cmd_mkchannel(args[:1], user, scope)
    if result.get("ok") and isinstance(result.get("path"), str):
        target = ws.root / result["path"]
        if target.is_dir():
            scope.cwd = target
    return result
