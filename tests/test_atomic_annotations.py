from kobold_sandbox.atomic_annotations import (
    build_annotation_table_rows,
    build_unique_wikilike_message,
    collect_unique_annotation_values,
    merge_unique_wikilike_message,
    patch_annotation_row,
    update_annotation_from_row,
)


def test_build_annotation_table_rows_extracts_span_text_and_metadata() -> None:
    message = {
        "message_id": "msg_demoness_001",
        "containers": [
            {
                "kind": "text",
                "name": "main_text",
                "data": {
                    "text": "Anime demoness with obsidian horns, glowing amber eyes, and a proud side-facing pose."
                },
            }
        ],
        "annotations": [
            {
                "kind": "annotation",
                "source": {
                    "message_ref": "msg_demoness_001",
                    "container_ref": "main_text",
                    "char_start": 0,
                    "char_end": 14,
                    "char_len": 14,
                },
                "tags": ["style", "anime"],
                "meta": {"label": "style_phrase"},
            },
            {
                "kind": "annotation",
                "source": {
                    "message_ref": "msg_demoness_001",
                    "container_ref": "main_text",
                    "char_start": 36,
                    "char_end": 54,
                    "char_len": 18,
                },
                "tags": ["appearance_trait", "eyes"],
                "meta": {"label": "eye_phrase"},
            },
        ],
    }

    rows = build_annotation_table_rows(message)

    assert len(rows) == 2
    assert rows[0]["field"] == "style_phrase"
    assert rows[0]["value"] == "Anime demoness"
    assert rows[0]["meta"]["tags"] == ["style", "anime"]
    assert rows[1]["field"] == "eye_phrase"
    assert rows[1]["value"] == "glowing amber eyes"
    assert rows[1]["meta"]["char_start"] == 36
    assert rows[1]["meta"]["char_end"] == 54
    assert rows[1]["meta"]["char_len"] == 18


def test_update_annotation_from_row_updates_label_tags_and_span_meta_only() -> None:
    message = {
        "message_id": "msg_demoness_001",
        "containers": [
            {
                "kind": "text",
                "name": "main_text",
                "data": {
                    "text": "Anime demoness with obsidian horns, glowing amber eyes, and a proud side-facing pose."
                },
            }
        ],
        "annotations": [
            {
                "kind": "annotation",
                "source": {
                    "message_ref": "msg_demoness_001",
                    "container_ref": "main_text",
                    "char_start": 36,
                    "char_end": 54,
                    "char_len": 18,
                },
                "tags": ["appearance_trait", "eyes"],
                "meta": {"label": "eye_phrase"},
            }
        ],
    }

    row = {
        "field": "eye_phrase_primary",
        "path": "msg_demoness_001.annotations[0]",
        "meta": {
            "message_ref": "msg_demoness_001",
            "container_ref": "main_text",
            "char_start": 36,
            "char_end": 61,
            "char_len": 25,
            "tags": ["appearance_trait", "eyes", "primary"],
        },
    }

    updated = update_annotation_from_row(message, row)

    assert updated["meta"]["label"] == "eye_phrase_primary"
    assert updated["tags"] == ["appearance_trait", "eyes", "primary"]
    assert updated["source"]["char_start"] == 36
    assert updated["source"]["char_end"] == 61
    assert updated["source"]["char_len"] == 25
    assert message["annotations"][0]["meta"]["label"] == "eye_phrase_primary"
    assert message["containers"][0]["data"]["text"].startswith("Anime demoness")


def test_patch_annotation_row_runs_full_message_rows_patch_cycle() -> None:
    message = {
        "message_id": "msg_demoness_001",
        "containers": [
            {
                "kind": "text",
                "name": "main_text",
                "data": {
                    "text": "Anime demoness with obsidian horns, glowing amber eyes, and a proud side-facing pose."
                },
            }
        ],
        "annotations": [
            {
                "kind": "annotation",
                "source": {
                    "message_ref": "msg_demoness_001",
                    "container_ref": "main_text",
                    "char_start": 36,
                    "char_end": 54,
                    "char_len": 18,
                },
                "tags": ["appearance_trait", "eyes"],
                "meta": {"label": "eye_phrase"},
            }
        ],
    }

    patched_row, rows_after = patch_annotation_row(
        message,
        "msg_demoness_001.annotations[0]",
        {
            "field": "eye_phrase_checked",
            "meta": {
                "char_start": 36,
                "char_end": 61,
                "char_len": 25,
                "tags": ["appearance_trait", "eyes", "checked"],
            },
        },
    )

    assert patched_row["field"] == "eye_phrase_checked"
    assert message["annotations"][0]["meta"]["label"] == "eye_phrase_checked"
    assert message["annotations"][0]["source"]["char_end"] == 61
    assert message["annotations"][0]["tags"] == ["appearance_trait", "eyes", "checked"]
    assert rows_after[0]["field"] == "eye_phrase_checked"
    assert rows_after[0]["meta"]["char_end"] == 61


def test_collect_unique_annotation_values_and_build_wikilike_message() -> None:
    messages = [
        {
            "message_id": "msg_001",
            "containers": [
                {
                    "kind": "text",
                    "name": "main_text",
                    "data": {
                        "text": "She has glowing amber eyes and long black hair."
                    },
                }
            ],
            "annotations": [
                {
                    "kind": "annotation",
                    "source": {
                        "message_ref": "msg_001",
                        "container_ref": "main_text",
                        "char_start": 17,
                        "char_end": 28,
                        "char_len": 11,
                    },
                    "tags": ["eyes", "color"],
                    "meta": {"label": "eyes_color", "normalized_value": "amber"},
                },
                {
                    "kind": "annotation",
                    "source": {
                        "message_ref": "msg_001",
                        "container_ref": "main_text",
                        "char_start": 38,
                        "char_end": 43,
                        "char_len": 5,
                    },
                    "tags": ["hair", "color"],
                    "meta": {"label": "hair_color", "normalized_value": "black"},
                },
            ],
        },
        {
            "message_id": "msg_002",
            "containers": [
                {
                    "kind": "text",
                    "name": "main_text",
                    "data": {
                        "text": "Another demoness has vivid green eyes and silver hair."
                    },
                }
            ],
            "annotations": [
                {
                    "kind": "annotation",
                    "source": {
                        "message_ref": "msg_002",
                        "container_ref": "main_text",
                        "char_start": 28,
                        "char_end": 39,
                        "char_len": 11,
                    },
                    "tags": ["eyes", "color"],
                    "meta": {"label": "eyes_color", "normalized_value": "green"},
                },
                {
                    "kind": "annotation",
                    "source": {
                        "message_ref": "msg_002",
                        "container_ref": "main_text",
                        "char_start": 44,
                        "char_end": 50,
                        "char_len": 6,
                    },
                    "tags": ["hair", "color"],
                    "meta": {"label": "hair_color", "normalized_value": "silver"},
                },
                {
                    "kind": "annotation",
                    "source": {
                        "message_ref": "msg_002",
                        "container_ref": "main_text",
                        "char_start": 28,
                        "char_end": 39,
                        "char_len": 11,
                    },
                    "tags": ["eyes", "color"],
                    "meta": {"label": "eyes_color_dup", "normalized_value": "green"},
                },
            ],
        },
    ]

    grouped = collect_unique_annotation_values(messages, {"eyes": ["eyes", "color"], "hair": ["hair", "color"]})
    assert [item["value"] for item in grouped["eyes"]] == ["amber", "green"]
    assert [item["value"] for item in grouped["hair"]] == ["black", "silver"]
    assert len(grouped["eyes"][1]["source_refs"]) == 1

    wiki_message = build_unique_wikilike_message(
        messages,
        {"eyes": ["eyes", "color"], "hair": ["hair", "color"]},
        message_id="wiki_colors_001",
        title="Unique Demoness Colors",
    )

    assert wiki_message["message_id"] == "wiki_colors_001"
    assert wiki_message["meta"]["kind"] == "wiki_like_summary"
    assert wiki_message["meta"]["source_message_refs"] == ["msg_001", "msg_002"]
    table_container = next(container for container in wiki_message["containers"] if container["name"] == "unique_values")
    rows = table_container["data"]["rows"]
    assert ["eyes", "amber", "msg_001[17:28]"] in rows
    assert ["eyes", "green", "msg_002[28:39]"] in rows
    assert ["hair", "black", "msg_001[38:43]"] in rows
    assert ["hair", "silver", "msg_002[44:50]"] in rows


def test_merge_unique_wikilike_message_appends_new_unique_values_and_sources() -> None:
    existing = {
        "message_id": "wiki_colors_001",
        "containers": [
            {
                "kind": "wiki_summary",
                "name": "summary_text",
                "data": {"text": "Unique Demoness Colors\neyes: amber\nhair: black"},
            },
            {
                "kind": "table",
                "name": "unique_values",
                "data": {
                    "headers": ["category", "value", "sources"],
                    "rows": [
                        ["eyes", "amber", "msg_001[17:28]"],
                        ["hair", "black", "msg_001[38:43]"],
                    ],
                },
            },
        ],
        "meta": {
            "kind": "wiki_like_summary",
            "title": "Unique Demoness Colors",
            "source_message_refs": ["msg_001"],
            "tag_groups": {"eyes": ["eyes", "color"], "hair": ["hair", "color"]},
        },
    }
    new_messages = [
        {
            "message_id": "msg_002",
            "containers": [
                {
                    "kind": "text",
                    "name": "main_text",
                    "data": {
                        "text": "Another demoness has vivid green eyes and silver hair."
                    },
                }
            ],
            "annotations": [
                {
                    "kind": "annotation",
                    "source": {
                        "message_ref": "msg_002",
                        "container_ref": "main_text",
                        "char_start": 28,
                        "char_end": 39,
                        "char_len": 11,
                    },
                    "tags": ["eyes", "color"],
                    "meta": {"label": "eyes_color", "normalized_value": "green"},
                },
                {
                    "kind": "annotation",
                    "source": {
                        "message_ref": "msg_002",
                        "container_ref": "main_text",
                        "char_start": 44,
                        "char_end": 50,
                        "char_len": 6,
                    },
                    "tags": ["hair", "color"],
                    "meta": {"label": "hair_color", "normalized_value": "silver"},
                },
            ],
        }
    ]

    merged = merge_unique_wikilike_message(
        existing,
        new_messages,
        {"eyes": ["eyes", "color"], "hair": ["hair", "color"]},
    )

    table_container = next(container for container in merged["containers"] if container["name"] == "unique_values")
    rows = table_container["data"]["rows"]

    assert ["eyes", "amber", "msg_001[17:28]"] in rows
    assert ["eyes", "green", "msg_002[28:39]"] in rows
    assert ["hair", "black", "msg_001[38:43]"] in rows
    assert ["hair", "silver", "msg_002[44:50]"] in rows
    assert merged["meta"]["source_message_refs"] == ["msg_001", "msg_002"]
