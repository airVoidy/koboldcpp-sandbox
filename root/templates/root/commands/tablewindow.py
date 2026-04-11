"""tablewindow - update pagination state for a table container.

Usage:
  /tablewindow <table_container_id> [--limit=N] [--offset=N] [--before-ref=PATH] [--after-ref=PATH]
"""


def execute(args, user, scope, ws):
    if not args:
        return {"error": "usage: /tablewindow <table_container_id> [--limit=N] [--offset=N] [--before-ref=PATH] [--after-ref=PATH]"}
    table_id = args[0]
    limit = None
    offset = None
    before_ref = ""
    after_ref = ""
    for arg in args[1:]:
        if arg.startswith("--limit="):
            try:
                limit = int(arg.split("=", 1)[1])
            except Exception:
                return {"error": "limit must be an integer"}
        elif arg.startswith("--offset="):
            try:
                offset = int(arg.split("=", 1)[1])
            except Exception:
                return {"error": "offset must be an integer"}
        elif arg.startswith("--before-ref="):
            before_ref = arg.split("=", 1)[1].strip()
        elif arg.startswith("--after-ref="):
            after_ref = arg.split("=", 1)[1].strip()
    return ws.container_set_table_window(
        table_id,
        limit=limit,
        offset=offset,
        before_ref=before_ref,
        after_ref=after_ref,
        user=user,
    )
