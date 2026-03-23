from fastapi.testclient import TestClient

from kobold_sandbox.server import create_app


def test_workflow_default_endpoint_returns_encoding_report(tmp_path) -> None:
    client = TestClient(create_app(str(tmp_path)))

    response = client.get("/api/workflow/default")

    assert response.status_code == 200
    payload = response.json()
    assert payload["yaml"].startswith("dsl: workflow/")
    assert "encoding" in payload
    assert payload["encoding"]["suspect_mojibake"] is False
    assert payload["encoding"]["has_cyrillic"] is True


def test_workflow_run_returns_request_encoding_diagnostics(tmp_path) -> None:
    client = TestClient(create_app(str(tmp_path)))

    response = client.post(
        "/api/workflow/run",
        json={
            "yaml": "dsl: workflow/v2\nlet:\n  input: hello\nflow: []\n",
            "input": "тест",
            "workers": {},
            "settings": {},
        },
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["diagnostics"]["yaml"]["suspect_mojibake"] is False
    assert payload["diagnostics"]["input"]["has_cyrillic"] is True
