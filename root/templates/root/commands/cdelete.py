"""cdelete - soft-delete a message in the selected channel.

Usage: /cdelete <msg_id>
"""


def execute(args, user, scope, ws):
    if not args:
        return {"error": "usage: /cdelete <msg_id> [--hard]"}
    msg_id = args[0]
    hard = "--hard" in args
    if hard:
        return ws.cmd_rm([msg_id], user, scope)
    return ws.cmd_cpatch([f"{msg_id}._deleted", "true"], user, scope)
