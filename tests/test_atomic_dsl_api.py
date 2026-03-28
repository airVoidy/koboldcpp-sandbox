from fastapi.testclient import TestClient

from kobold_sandbox.server import create_app


def test_atomic_dsl_ingest_includes_row_metadata(tmp_path) -> None:
    client = TestClient(create_app(str(tmp_path)))

    response = client.post(
        "/api/dsl/ingest",
        json={
            "name": "generate.request",
            "json_data": {
                "prompt": "Write 4 demoness descriptions.",
                "temperature": 0.35,
                "settings": {"mode": "draft"},
            },
        },
    )

    assert response.status_code == 200
    payload = response.json()
    table_node = next(child for child in payload["children"] if child["node"] == "table")
    rows = table_node["value"]["rows"]
    prompt_row = next(row for row in rows if row["path"] == "generate.request.prompt")
    mode_row = next(row for row in rows if row["path"] == "generate.request.settings.mode")
    meta_node = next(child for child in payload["children"] if child["node"] == "meta")

    assert prompt_row["group"] == "root"
    assert prompt_row["aliases"] == ["generate.request.prompt", "prompt"]
    assert prompt_row["meta"]["cell_kind"] == "plain"
    assert mode_row["group"] == "settings"
    assert meta_node["value"]["object_path"] == "generate.request"


def test_atomic_dsl_resolve_returns_original_payload_shape_without_object_wrapper(tmp_path) -> None:
    client = TestClient(create_app(str(tmp_path)))

    ingest_response = client.post(
        "/api/dsl/ingest",
        json={
            "name": "generate.request",
            "json_data": {
                "prompt": "Write 4 demoness descriptions.",
                "temperature": 0.35,
                "settings": {"mode": "draft"},
            },
        },
    )
    rows = next(child for child in ingest_response.json()["children"] if child["node"] == "table")["value"]["rows"]

    patch_response = client.post(
        "/api/dsl/patch",
        json={
            "rows": rows,
            "patch": {"target": "generate.request.temperature", "value": 0.5, "reason": "user_edit"},
        },
    )
    patched_rows = patch_response.json()["rows"]

    resolve_response = client.post(
        "/api/dsl/resolve",
        json={"rows": patched_rows, "object_name": "generate.request"},
    )

    assert resolve_response.status_code == 200
    assert resolve_response.json()["value"] == {
        "prompt": "Write 4 demoness descriptions.",
        "temperature": 0.5,
        "settings": {"mode": "draft"},
    }


def test_atomic_dsl_event_compile_returns_assembly_for_generate_miniflow(tmp_path) -> None:
    client = TestClient(create_app(str(tmp_path)))

    response = client.post(
        "/api/dsl/event/compile",
        json={
            "dsl": """
emit("task.input", {
  data: {
    text: "hello"
  }
})

emit("generate.request", {
  schema: "native_generate_request",
  defaults: "native_generate_defaults",
  data: {
    prompt: @task.input.text,
    model: "local-model",
    max_length: 256
  },
  checks: ["complete"]
})

on("generate.request", "response", {
  bind: "generate.response",
  schema: "native_generate_response",
  checks: ["complete"]
})
""".strip()
        },
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["statement_count"] == 3
    assert payload["error"] is None
    assert 'MOV  @task.input.text, "hello"' in payload["assembly"]
    assert "GEN  @generate.call.raw, @task.input.text, worker:generator, temp:0.2, max:256" in payload["assembly"]


def test_atomic_dsl_asm_supports_gen_mock_mode_without_worker(tmp_path) -> None:
    client = TestClient(create_app(str(tmp_path)))

    response = client.post(
        "/api/dsl/asm",
        json={
            "code": 'GEN  @out, "hello", worker:generator, temp:0.2, max:8',
            "config": {
                "gen_mode": "mock",
                "gen_mock_response": "mocked-from-config",
            },
        },
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["error"] is None
    assert payload["state"]["out"] == "mocked-from-config"


def test_atomic_dsl_asm_supports_gen_fixture_mode_without_worker(tmp_path) -> None:
    client = TestClient(create_app(str(tmp_path)))

    response = client.post(
        "/api/dsl/asm",
        json={
            "code": 'GEN  @out, "fixture prompt", worker:generator, temp:0.2, max:8',
            "config": {
                "gen_mode": "fixture",
                "gen_fixtures": {
                    "fixture prompt": "fixture result",
                },
            },
        },
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["error"] is None
    assert payload["state"]["out"] == "fixture result"


def test_atomic_dsl_asm_supports_gen_replay_mode_without_worker(tmp_path) -> None:
    client = TestClient(create_app(str(tmp_path)))

    response = client.post(
        "/api/dsl/asm",
        json={
            "code": 'GEN  @out, "replay prompt", worker:generator, temp:0.2, max:8',
            "config": {
                "gen_mode": "replay",
                "gen_replays": {
                    "replay prompt": {
                        "results": [{"text": "replayed result"}],
                    },
                },
            },
        },
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["error"] is None
    assert payload["state"]["out"] == "replayed result"


def test_atomic_dsl_annotations_wiki_build_creates_summary_message(tmp_path) -> None:
    client = TestClient(create_app(str(tmp_path)))

    response = client.post(
        "/api/dsl/annotations/wiki/build",
        json={
            "messages": [
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
                }
            ],
            "tag_groups": {"eyes": ["eyes", "color"], "hair": ["hair", "color"]},
            "message_id": "wiki_colors_001",
            "title": "Unique Demoness Colors",
        },
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["error"] is None
    assert payload["message"]["message_id"] == "wiki_colors_001"
    assert payload["message"]["meta"]["source_message_refs"] == ["msg_001"]
    table_container = next(container for container in payload["message"]["containers"] if container["name"] == "unique_values")
    assert ["eyes", "amber", "msg_001[17:28]"] in table_container["data"]["rows"]
    assert ["hair", "black", "msg_001[38:43]"] in table_container["data"]["rows"]


def test_atomic_dsl_annotations_wiki_merge_updates_existing_summary_message(tmp_path) -> None:
    client = TestClient(create_app(str(tmp_path)))

    response = client.post(
        "/api/dsl/annotations/wiki/merge",
        json={
            "existing_message": {
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
            },
            "messages": [
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
            ],
            "tag_groups": {"eyes": ["eyes", "color"], "hair": ["hair", "color"]},
        },
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["error"] is None
    assert payload["message"]["meta"]["source_message_refs"] == ["msg_001", "msg_002"]
    table_container = next(container for container in payload["message"]["containers"] if container["name"] == "unique_values")
    rows = table_container["data"]["rows"]
    assert ["eyes", "amber", "msg_001[17:28]"] in rows
    assert ["eyes", "green", "msg_002[28:39]"] in rows
    assert ["hair", "black", "msg_001[38:43]"] in rows
    assert ["hair", "silver", "msg_002[44:50]"] in rows


def test_atomic_data_text_artifact_upsert_and_get(tmp_path) -> None:
    client = TestClient(create_app(str(tmp_path)))

    upsert_response = client.put(
        "/api/atomic-data/text/data.local.wiki.task.input",
        json={
            "scope": "local",
            "artifact_kind": "wiki",
            "title": "Task Input",
            "text": "написать 4 описания демониц",
            "format": "wikilike",
            "tags": ["task", "input"],
            "source_refs": ["msg_task_a_001"],
        },
    )

    assert upsert_response.status_code == 200
    payload = upsert_response.json()
    assert payload["artifact"]["data_ref"] == "data.local.wiki.task.input"
    assert payload["artifact"]["message"]["text"] == "написать 4 описания демониц"

    get_response = client.get("/api/atomic-data/text/data.local.wiki.task.input")
    assert get_response.status_code == 200
    assert get_response.json()["title"] == "Task Input"
    assert get_response.json()["source_refs"] == ["msg_task_a_001"]


def test_atomic_data_revision_commit_tracks_text_refs_and_object_hashes(tmp_path) -> None:
    client = TestClient(create_app(str(tmp_path)))

    client.put(
        "/api/atomic-data/text/data.local.wiki.task.input",
        json={
            "scope": "local",
            "artifact_kind": "wiki",
            "title": "Task Input",
            "text": "написать 4 описания демониц",
            "format": "wikilike",
        },
    )

    commit_response = client.post(
        "/api/atomic-data/revision/commit",
        json={
            "message": "Checkpoint task input",
            "text_refs": ["data.local.wiki.task.input"],
            "objects": {
                "data.local.object.generate.request": {
                    "prompt": "написать 4 описания демониц",
                    "max_length": 512,
                }
            },
            "metadata": {"scope": "local", "kind": "checkpoint"},
        },
    )

    assert commit_response.status_code == 200
    payload = commit_response.json()
    assert payload["commit"]
    assert payload["revision"]["text_refs"] == ["data.local.wiki.task.input"]
    assert "data.local.object.generate.request" in payload["revision"]["object_hashes"]

    log_response = client.get("/api/atomic-data/revision/log")
    assert log_response.status_code == 200
    revisions = log_response.json()["revisions"]
    assert revisions
    assert revisions[0]["text_refs"] == ["data.local.wiki.task.input"]
    assert revisions[0]["git_commit_ref"]
