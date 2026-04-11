def execute(op_spec, meta, ws):
    table = meta.get("table", {}) if isinstance(meta.get("table"), dict) else {}
    rows = table.get("rows") or []
    if not isinstance(rows, list):
        rows = []

    offset = op_spec.get("offset", 0)
    limit = op_spec.get("limit")
    from_end = bool(op_spec.get("from_end"))

    try:
        offset = int(offset)
    except Exception:
        return {"error": "offset must be an integer"}
    if offset < 0:
        offset = 0

    if limit is not None:
        try:
            limit = int(limit)
        except Exception:
            return {"error": "limit must be an integer"}
        if limit < 0:
            limit = 0

    if from_end:
        if limit is None:
            sliced = rows[:]
        else:
            end = len(rows) - offset
            start = max(0, end - limit)
            sliced = rows[start:end]
    else:
        if limit is None:
            sliced = rows[offset:]
        else:
            sliced = rows[offset:offset + limit]

    table["rows"] = sliced
    meta["table"] = table
    return {"meta": meta}
