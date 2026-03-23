from fastapi.testclient import TestClient

from kobold_sandbox.server import create_app


class _FakeResponse:
    def __init__(self, content: str, *, finish_reason: str = "stop") -> None:
        self._content = content
        self._finish_reason = finish_reason

    def raise_for_status(self) -> None:
        return None

    def json(self) -> dict:
        return {
            "choices": [
                {
                    "message": {"content": self._content},
                    "finish_reason": self._finish_reason,
                }
            ]
        }


class _PassHttpClient:
    def __init__(self, *args, **kwargs) -> None:
        self.calls: list[dict] = []

    def post(self, _url: str, json: dict) -> _FakeResponse:
        self.calls.append(json)
        return _FakeResponse("PASS")

    def close(self) -> None:
        return None


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


def test_workflow_trigger_uses_full_builtin_set(tmp_path, monkeypatch) -> None:
    import kobold_sandbox.workflow_dsl as workflow_dsl

    monkeypatch.setattr(workflow_dsl.httpx, "Client", _PassHttpClient)

    client = TestClient(create_app(str(tmp_path)))
    yaml_text = """
dsl: workflow/v2
let: {}
flow: []
triggers:
  generate:
    - "for $entity in $entity_nodes":
        - generator -> $reaction:
            prompt: "check"
        - set:
            "$entity.reaction": $reaction
            "$entity.reactionStatus": check_status($reaction)
"""

    response = client.post(
        "/api/workflow/trigger",
        json={
            "yaml": yaml_text,
            "trigger": "generate",
            "workers": {"generator": "http://fake-worker"},
            "settings": {},
            "vars": {
                "$entity_nodes": [{"_title": "entity-1", "answer": "text"}],
            },
        },
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["status"] == "done"
    assert payload["vars"]["entity_nodes"][0]["reaction"] == "PASS"
    assert payload["vars"]["entity_nodes"][0]["reactionStatus"] == "pass"
