def execute(rule, local_root, value_map, ws):
    args = rule.get("args") or []
    sep = str(rule.get("sep", ""))
    parts = []
    for arg in args:
        arg_key = ws._projection_local_key(local_root, str(arg))
        arg_value = value_map.get(arg_key)
        if arg_value is None:
            arg_value = ""
        parts.append(str(arg_value))
    return {"value": sep.join(parts)}
