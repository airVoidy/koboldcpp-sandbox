def execute(op_spec, meta, ws):
    table = meta.get("table", {}) if isinstance(meta.get("table"), dict) else {}
    source_path = str(op_spec.get("source_path") or "").strip()
    projection_root = str(op_spec.get("projection_root") or "item").strip()
    fields = op_spec.get("fields") or []
    row_key_from = str(op_spec.get("row_key_from") or "id").strip().lower()
    replace = bool(op_spec.get("replace", True))
    from_end = bool(op_spec.get("from_end", True))
    visible_only = bool(op_spec.get("visible_only", True))
    before_ref = str(op_spec.get("before_ref") or "").strip()
    after_ref = str(op_spec.get("after_ref") or "").strip()

    offset = op_spec.get("offset", 0)
    limit = op_spec.get("limit")
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

    if not source_path:
        return {"error": "source_path is required"}
    if not isinstance(fields, list) or not fields:
        return {"error": "fields must be a non-empty list"}

    source_dir = ws.root / source_path
    if not source_dir.is_dir():
        return {"error": f"not found: {source_path}"}

    if replace:
        rows = []
    else:
        rows = table.get("rows") or []
        if not isinstance(rows, list):
            rows = []

    entries = ws._read_child_log(source_dir)
    ordered_entries = list(reversed(entries)) if from_end else list(entries)
    if before_ref:
        before_idx = next((idx for idx, entry in enumerate(ordered_entries) if str(entry.get("ref") or "").strip() == before_ref), None)
        if before_idx is not None:
            ordered_entries = ordered_entries[before_idx + 1:]
        else:
            ordered_entries = []
    elif after_ref:
        after_idx = next((idx for idx, entry in enumerate(ordered_entries) if str(entry.get("ref") or "").strip() == after_ref), None)
        if after_idx is not None:
            ordered_entries = ordered_entries[:after_idx]
        else:
            ordered_entries = []
    if offset:
        ordered_entries = ordered_entries[offset:]

    collected = []
    for entry in ordered_entries:
        if limit is not None and len(collected) >= limit:
            break
        if not isinstance(entry, dict):
            continue
        child_path = str(entry.get("ref") or "").strip()
        if not child_path:
            continue
        child_dir = ws.root / child_path
        if visible_only and not child_dir.is_dir():
            continue

        child_id = child_dir.name if child_dir.name else child_path.rsplit("/", 1)[-1]
        canonical_fields = []
        for field in fields:
            field_str = str(field).strip()
            if not field_str:
                continue
            canonical_fields.append(f"{child_path}.{field_str}")
        if not canonical_fields:
            continue

        projection_id = f"{meta.get('id', 'table')}__{child_id}"
        result = ws.container_create_projection(
            projection_id,
            child_path,
            projection_root,
            canonical_fields,
            user="system",
        )
        if result.get("error"):
            return result

        meta_name = entry.get("meta", {}).get("name") if isinstance(entry.get("meta"), dict) else None
        if row_key_from == "name" and meta_name:
            row_key = str(meta_name)
        elif row_key_from == "ref":
            row_key = child_path
        else:
            row_key = child_id

        collected.append({
            "projection": projection_id,
            "row_key": row_key,
            "ref": child_path,
        })

    table["rows"] = rows + collected
    meta["table"] = table
    return {"meta": meta}
