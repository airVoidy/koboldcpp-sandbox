def execute(op_spec, meta, ws):
    table = meta.get("table", {}) if isinstance(meta.get("table"), dict) else {}
    source_path = str(op_spec.get("source_path") or "").strip()
    projection_root = str(op_spec.get("projection_root") or "item").strip()
    fields = op_spec.get("fields") or []
    row_key_from = str(op_spec.get("row_key_from") or "id").strip().lower()
    replace = bool(op_spec.get("replace", True))

    if not source_path:
        return {"error": "source_path is required"}
    if not isinstance(fields, list) or not fields:
        return {"error": "fields must be a non-empty list"}

    node = ws._read_node_object(source_path, include_children="direct")
    if node.get("error"):
        return node

    if replace:
        rows = []
    else:
        rows = table.get("rows") or []
        if not isinstance(rows, list):
            rows = []

    for child in node.get("children", []):
        child_path = child.get("path")
        child_id = child.get("id")
        if not child_path or not child_id:
            continue
        projection_id = f"{meta.get('id', 'table')}__{child_id}"
        canonical_fields = []
        for field in fields:
            field_str = str(field).strip()
            if not field_str:
                continue
            canonical_fields.append(f"{child_path}.{field_str}")

        result = ws.container_create_projection(
            projection_id,
            child_path,
            projection_root,
            canonical_fields,
            user="system",
        )
        if result.get("error"):
            return result

        row_key = child.get("meta", {}).get("name") if row_key_from == "name" else child_id
        rows.append({
            "projection": projection_id,
            "row_key": row_key,
        })

    table["rows"] = rows
    meta["table"] = table
    return {"meta": meta}
