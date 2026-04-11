def execute(rule, local_root, value_map, ws):
    args = rule.get("args") or []
    if not args:
        return {"error": "pick requires at least one source field"}
    for arg in args:
        arg_key = ws._projection_local_key(local_root, str(arg))
        if arg_key in value_map:
            return {"value": value_map.get(arg_key)}
    return {"value": None}
