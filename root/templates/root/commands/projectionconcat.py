"""projectionconcat - add a concat rule to a projection container.

Usage:
  /projectionconcat <container_id> <field_path> <source1> [source2 ...] [--sep=...]
"""


def execute(args, user, scope, ws):
    if len(args) < 3:
        return {"error": "usage: /projectionconcat <container_id> <field_path> <source1> [source2 ...] [--sep=...]"}
    container_id = args[0]
    field_path = args[1]
    sep = ""
    sources = []
    for arg in args[2:]:
        if arg.startswith("--sep="):
            sep = arg.split("=", 1)[1]
            continue
        sources.append(arg)
    return ws.container_add_projection_concat_rule(container_id, field_path, sources, sep, user)
