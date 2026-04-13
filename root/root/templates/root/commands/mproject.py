"""mproject - aggregate projection of all instances of a template type.

Usage:
  /mproject <type>                    (in current scope)
  /mproject msg                       (all msg_* instances)
  /mproject msg --scope=channels/general  (scoped)

Returns aggregated flat_store and views across all matching instances.
"""


def execute(args, user, scope, ws):
    if not args:
        return {"error": "usage: /mproject <type> [--scope=<path>]"}

    template_type = args[0]
    scope_dir = scope.cwd

    # Parse optional --scope
    for arg in args[1:]:
        if arg.startswith("--scope="):
            rel = arg.split("=", 1)[1]
            candidate = ws.root / rel
            if candidate.is_dir():
                scope_dir = candidate

    return ws._build_template_aggregation(template_type, scope_dir)
