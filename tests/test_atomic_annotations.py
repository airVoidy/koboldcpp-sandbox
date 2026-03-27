from kobold_sandbox.atomic_annotations import (
    build_annotation_table_rows,
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
