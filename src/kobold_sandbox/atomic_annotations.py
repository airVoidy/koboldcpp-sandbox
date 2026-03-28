from __future__ import annotations

import re
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
        annotation_meta = dict(annotation.get("meta") or {})
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
                    "annotation_meta": annotation_meta,
                    "normalized_value": annotation_meta.get("normalized_value"),
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


def collect_unique_annotation_values(
    messages: list[dict[str, Any]],
    tag_groups: dict[str, list[str]],
) -> dict[str, list[dict[str, Any]]]:
    grouped: dict[str, dict[str, dict[str, Any]]] = {name: {} for name in tag_groups}
    for message in messages:
        rows = build_annotation_table_rows(message)
        for row in rows:
            row_meta = row.get("meta") or {}
            tags = set(str(tag) for tag in (row_meta.get("tags") or []))
            for group_name, required_tags in tag_groups.items():
                if not set(required_tags).issubset(tags):
                    continue
                value = _normalize_annotation_value(row, row_meta)
                if not value:
                    continue
                bucket = grouped[group_name].setdefault(
                    value,
                    {
                        "value": value,
                        "source_refs": [],
                    },
                )
                source_ref = {
                    "message_ref": row_meta.get("message_ref"),
                    "container_ref": row_meta.get("container_ref"),
                    "char_start": row_meta.get("char_start"),
                    "char_end": row_meta.get("char_end"),
                    "char_len": row_meta.get("char_len"),
                    "path": row.get("path"),
                }
                dedupe_key = (
                    source_ref.get("message_ref"),
                    source_ref.get("container_ref"),
                    source_ref.get("char_start"),
                    source_ref.get("char_end"),
                    source_ref.get("char_len"),
                )
                existing_keys = {
                    (
                        item.get("message_ref"),
                        item.get("container_ref"),
                        item.get("char_start"),
                        item.get("char_end"),
                        item.get("char_len"),
                    )
                    for item in bucket["source_refs"]
                }
                if dedupe_key not in existing_keys:
                    bucket["source_refs"].append(source_ref)
    return {name: list(values.values()) for name, values in grouped.items()}


def build_unique_wikilike_message(
    messages: list[dict[str, Any]],
    tag_groups: dict[str, list[str]],
    *,
    message_id: str = "wiki_unique_annotations_001",
    title: str = "Unique Annotation Summary",
) -> dict[str, Any]:
    grouped = collect_unique_annotation_values(messages, tag_groups)
    rows: list[list[Any]] = []
    blocks: list[dict[str, Any]] = []
    all_sources: list[str] = []

    for group_name, items in grouped.items():
        for item in items:
            source_refs = item["source_refs"]
            source_labels = [
                _format_source_ref(source_ref)
                for source_ref in source_refs
            ]
            rows.append([group_name, item["value"], " | ".join(source_labels)])
            for source_ref in source_refs:
                message_ref = str(source_ref.get("message_ref") or "")
                if message_ref and message_ref not in all_sources:
                    all_sources.append(message_ref)

    summary_lines = [title]
    for group_name, items in grouped.items():
        values = ", ".join(item["value"] for item in items) if items else "none"
        summary_lines.append(f"{group_name}: {values}")

    blocks.append(
        {
            "block_id": f"{message_id}:block:summary",
            "kind": "text",
            "label": "summary",
            "text": "\n".join(summary_lines),
        }
    )
    blocks.append(
        {
            "block_id": f"{message_id}:block:table",
            "kind": "table",
            "label": "unique_values",
            "headers": ["category", "value", "sources"],
            "rows": rows,
        }
    )

    return {
        "message_id": message_id,
        "containers": [
            {
                "kind": "wiki_summary",
                "name": "summary_text",
                "data": {"text": "\n".join(summary_lines)},
            },
            {
                "kind": "table",
                "name": "unique_values",
                "data": {
                    "headers": ["category", "value", "sources"],
                    "rows": rows,
                },
            },
        ],
        "blocks": blocks,
        "meta": {
            "kind": "wiki_like_summary",
            "title": title,
            "source_message_refs": all_sources,
            "tag_groups": tag_groups,
        },
    }


def merge_unique_wikilike_message(
    existing_message: dict[str, Any],
    messages: list[dict[str, Any]],
    tag_groups: dict[str, list[str]],
) -> dict[str, Any]:
    grouped = collect_unique_annotation_values(messages, tag_groups)
    merged_rows = _existing_unique_rows(existing_message)
    source_refs = list((existing_message.get("meta") or {}).get("source_message_refs") or [])

    for group_name, items in grouped.items():
        for item in items:
            value = item["value"]
            source_labels = [_format_source_ref(source_ref) for source_ref in item["source_refs"]]
            key = (group_name, value)
            existing_sources = merged_rows.get(key, [])
            for source_label in source_labels:
                if source_label not in existing_sources:
                    existing_sources.append(source_label)
            merged_rows[key] = existing_sources
            for source_ref in item["source_refs"]:
                message_ref = str(source_ref.get("message_ref") or "")
                if message_ref and message_ref not in source_refs:
                    source_refs.append(message_ref)

    title = str((existing_message.get("meta") or {}).get("title") or "Unique Annotation Summary")
    rows = [
        [group_name, value, " | ".join(source_labels)]
        for (group_name, value), source_labels in sorted(merged_rows.items(), key=lambda item: (item[0][0], item[0][1]))
    ]
    summary_lines = [title]
    for group_name in tag_groups:
        values = [value for (group, value), _ in merged_rows.items() if group == group_name]
        summary_lines.append(f"{group_name}: {', '.join(values) if values else 'none'}")

    updated = dict(existing_message)
    updated["containers"] = [
        {
            "kind": "wiki_summary",
            "name": "summary_text",
            "data": {"text": "\n".join(summary_lines)},
        },
        {
            "kind": "table",
            "name": "unique_values",
            "data": {
                "headers": ["category", "value", "sources"],
                "rows": rows,
            },
        },
    ]
    updated["blocks"] = [
        {
            "block_id": f"{updated.get('message_id', 'wiki')}:block:summary",
            "kind": "text",
            "label": "summary",
            "text": "\n".join(summary_lines),
        },
        {
            "block_id": f"{updated.get('message_id', 'wiki')}:block:table",
            "kind": "table",
            "label": "unique_values",
            "headers": ["category", "value", "sources"],
            "rows": rows,
        },
    ]
    updated["meta"] = {
        **dict(existing_message.get("meta") or {}),
        "kind": "wiki_like_summary",
        "title": title,
        "source_message_refs": source_refs,
        "tag_groups": tag_groups,
    }
    return updated


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


def _normalize_annotation_value(row: dict[str, Any], row_meta: dict[str, Any]) -> str:
    preferred = row_meta.get("normalized_value")
    if preferred is None:
        annotation_meta = row_meta.get("annotation_meta") or {}
        if isinstance(annotation_meta, dict):
            preferred = annotation_meta.get("normalized_value")
    if preferred is None:
        preferred = row_meta.get("value")
    text = str(preferred if preferred is not None else row.get("value") or "")
    text = text.strip().strip(".,;:!?\"'()[]{}")
    text = re.sub(r"\s+", " ", text).strip().lower()
    return text


def _format_source_ref(source_ref: dict[str, Any]) -> str:
    message_ref = str(source_ref.get("message_ref") or "")
    char_start = source_ref.get("char_start")
    char_end = source_ref.get("char_end")
    return f"{message_ref}[{char_start}:{char_end}]"


def _existing_unique_rows(message: dict[str, Any]) -> dict[tuple[str, str], list[str]]:
    result: dict[tuple[str, str], list[str]] = {}
    for container in message.get("containers") or []:
        if not isinstance(container, dict):
            continue
        if str(container.get("name") or "") != "unique_values":
            continue
        data = container.get("data") or {}
        rows = data.get("rows") or []
        if not isinstance(rows, list):
            continue
        for row in rows:
            if not isinstance(row, list) or len(row) < 3:
                continue
            category = str(row[0])
            value = str(row[1])
            sources = [part.strip() for part in str(row[2]).split("|") if part.strip()]
            result[(category, value)] = sources
    return result
