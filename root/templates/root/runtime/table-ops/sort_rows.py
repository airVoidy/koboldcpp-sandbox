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
    order = str(op_spec.get("order") or "asc").strip().lower()
    reverse = order == "desc"

    enriched = []
    for row in rows:
        if not isinstance(row, dict):
            continue
        projection_id = str(row.get("projection") or "").strip()
        value = _projection_value(ws, projection_id, field_name) if projection_id else None
        enriched.append((value is None, str(value) if value is not None else "", row))

    enriched.sort(key=lambda item: item[:2], reverse=reverse)
    table["rows"] = [row for _, _, row in enriched]
    meta["table"] = table
    return {"meta": meta}
