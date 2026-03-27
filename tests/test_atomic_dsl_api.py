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
