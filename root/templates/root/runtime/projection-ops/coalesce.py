def execute(rule, local_root, value_map, ws):
    args = rule.get("args") or []
    for arg in args:
        arg_key = ws._projection_local_key(local_root, str(arg))
        arg_value = value_map.get(arg_key)
        if arg_value not in (None, ""):
            return {"value": arg_value}
    return {"value": None}
