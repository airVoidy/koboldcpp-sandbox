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
