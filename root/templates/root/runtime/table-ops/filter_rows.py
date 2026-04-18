def _projection_value(ws, projection_id, field_name):
    projection = ws.materialize_container(projection_id, persist=False)
    proj = projection.get("resolved", {}).get("projection", {})
    fields = proj.get("fields", []) if isinstance(proj, dict) else []
    for field in fields:
        if not isinstance(field, dict):
            continue
        if field.get("local_name") == field_name:
            return field.get("value")
    return None


def execute(op_spec, meta, ws):
    table = meta.get("table", {}) if isinstance(meta.get("table"), dict) else {}
    rows = table.get("rows") or []
    if not isinstance(rows, list):
        rows = []

    field_name = str(op_spec.get("field") or "").strip()
    if not field_name:
        return {"error": "field is required"}
    has_equals = "equals" in op_spec
    equals_value = op_spec.get("equals")
    nonempty = bool(op_spec.get("nonempty"))

    filtered = []
    for row in rows:
        if not isinstance(row, dict):
            continue
        projection_id = str(row.get("projection") or "").strip()
        value = _projection_value(ws, projection_id, field_name) if projection_id else None
        keep = True
        if has_equals:
            keep = value == equals_value
        elif nonempty:
            keep = value not in (None, "")
        if keep:
            filtered.append(row)

    table["rows"] = filtered
    meta["table"] = table
    return {"meta": meta}
