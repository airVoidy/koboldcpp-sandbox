from __future__ import annotations

from typing import Any


def build_annotation_table_rows(message: dict[str, Any]) -> list[dict[str, Any]]:
    message_id = str(message.get("message_id") or "")
    containers = _container_text_map(message)
    rows: list[dict[str, Any]] = []

    for index, annotation in enumerate(message.get("annotations") or []):
        if not isinstance(annotation, dict):
            continue
        source = annotation.get("source") or {}
        if not isinstance(source, dict):
            source = {}

        container_ref = str(source.get("container_ref") or "")
        container_text = containers.get(container_ref, "")
        char_start = _as_int(source.get("char_start"), 0)
        char_end = _as_int(source.get("char_end"), char_start)
        char_len = _as_int(source.get("char_len"), max(0, char_end - char_start))
        label = str((annotation.get("meta") or {}).get("label") or f"annotation_{index + 1}")
        tags = list(annotation.get("tags") or [])
        span_text = _slice_text(container_text, char_start, char_end)

        rows.append(
            {
                "field": label,
                "type": "annotation",
                "value": span_text,
                "path": f"{message_id}.annotations[{index}]",
                "group": container_ref or "annotations",
                "aliases": [label, f"{message_id}:{label}"] if message_id else [label],
                "meta": {
                    "annotation_kind": str(annotation.get("kind") or "annotation"),
                    "message_ref": str(source.get("message_ref") or message_id),
                    "container_ref": container_ref,
                    "char_start": char_start,
                    "char_end": char_end,
                    "char_len": char_len,
                    "tags": tags,
                },
            }
        )

    return rows


def update_annotation_from_row(message: dict[str, Any], row: dict[str, Any]) -> dict[str, Any]:
    path = str(row.get("path") or "")
    index = _annotation_index_from_path(path)
    annotations = message.get("annotations") or []
    if not isinstance(annotations, list):
        raise ValueError("message.annotations must be a list")
    if index < 0 or index >= len(annotations):
        raise ValueError(f"Cannot resolve annotation index from path: {path!r}")

    annotation = annotations[index]
    if not isinstance(annotation, dict):
        raise ValueError(f"Annotation at index {index} is not an object")

    updated = dict(annotation)
    updated["kind"] = str(updated.get("kind") or "annotation")

    source = dict(updated.get("source") or {})
    meta = dict(updated.get("meta") or {})
    row_meta = row.get("meta") or {}
    if not isinstance(row_meta, dict):
        row_meta = {}

    if row.get("field") is not None:
        meta["label"] = str(row.get("field"))
    if "tags" in row_meta:
        meta_tags = row_meta.get("tags") or []
        updated["tags"] = list(meta_tags) if isinstance(meta_tags, list) else [str(meta_tags)]

    for key in ("message_ref", "container_ref", "block_ref", "char_start", "char_end", "char_len"):
        if key in row_meta:
            source[key] = row_meta[key]

    updated["source"] = source
    updated["meta"] = meta
    annotations[index] = updated
    message["annotations"] = annotations
    return updated


def patch_annotation_row(message: dict[str, Any], row_path: str, patch: dict[str, Any]) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    rows = build_annotation_table_rows(message)
    for row in rows:
        if str(row.get("path") or "") != row_path:
            continue
        patched_row = dict(row)
        row_meta = dict(patched_row.get("meta") or {})
        patch_meta = patch.get("meta") or {}
        if not isinstance(patch_meta, dict):
            patch_meta = {}

        if "field" in patch:
            patched_row["field"] = patch["field"]
        if "value" in patch:
            patched_row["value"] = patch["value"]
        if "group" in patch:
            patched_row["group"] = patch["group"]
        if "aliases" in patch:
            aliases = patch.get("aliases") or []
            patched_row["aliases"] = list(aliases) if isinstance(aliases, list) else [str(aliases)]

        row_meta.update(patch_meta)
        patched_row["meta"] = row_meta
        update_annotation_from_row(message, patched_row)
        refreshed_rows = build_annotation_table_rows(message)
        return patched_row, refreshed_rows

    raise ValueError(f"Annotation row not found: {row_path!r}")


def _container_text_map(message: dict[str, Any]) -> dict[str, str]:
    mapping: dict[str, str] = {}
    for container in message.get("containers") or []:
        if not isinstance(container, dict):
            continue
        name = str(container.get("name") or "")
        data = container.get("data") or {}
        if not isinstance(data, dict):
            continue
        text = data.get("text")
        if name and isinstance(text, str):
            mapping[name] = text
    return mapping


def _slice_text(text: str, char_start: int, char_end: int) -> str:
    if char_start < 0:
        char_start = 0
    if char_end < char_start:
        char_end = char_start
    return text[char_start:char_end]


def _as_int(value: Any, default: int) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def _annotation_index_from_path(path: str) -> int:
    marker = ".annotations["
    start = path.find(marker)
    if start < 0:
        return -1
    start += len(marker)
    end = path.find("]", start)
    if end < 0:
        return -1
    try:
        return int(path[start:end])
    except ValueError:
        return -1
