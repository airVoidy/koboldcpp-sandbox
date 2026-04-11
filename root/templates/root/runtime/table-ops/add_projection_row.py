def execute(op_spec, meta, ws):
    table = meta.get("table", {}) if isinstance(meta.get("table"), dict) else {}
    rows = table.get("rows") or []
    if not isinstance(rows, list):
        rows = []

    projection_id = str(op_spec.get("projection") or "").strip()
    if not projection_id:
        return {"error": "projection is required"}
    projection_meta = ws._read_container_meta(projection_id)
    if not projection_meta:
        return {"error": f"unknown projection container: {projection_id}"}
    if projection_meta.get("kind") != "projection":
        return {"error": f"container is not a projection: {projection_id}"}

    row_key = str(op_spec.get("row_key") or projection_id).strip()
    rows.append({
        "projection": projection_id,
        "row_key": row_key,
    })
    table["rows"] = rows
    meta["table"] = table
    return {"meta": meta}
