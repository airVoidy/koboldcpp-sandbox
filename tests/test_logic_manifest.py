from __future__ import annotations

from fastapi.testclient import TestClient

from kobold_sandbox.logic_manifest import linear_schema_to_manifest, parse_linear_logic_schema, parse_logic_manifest, verify_logic
from kobold_sandbox.server import create_app


MANIFEST_TEXT = """
ENTITIES: [Elisey, Diana, Ilya, Sofya, Lera, Anna, Maksim]
AXIOMS:
- pos('Diana') < pos('Ilya')
- pos('Ilya') < pos('Sofya')
- pos('Sofya') + 1 == pos('Lera')
HYPOTHESES:
SofiaAuthor: [author == 'Sofya', pos('Sofya') < pos('Maksim')]
AnnaAuthor: [author == 'Anna', pos('Anna') < pos('Maksim')]
"""


def test_parse_logic_manifest_and_verify() -> None:
    manifest = parse_logic_manifest(MANIFEST_TEXT)

    assert manifest.entities == ["Elisey", "Diana", "Ilya", "Sofya", "Lera", "Anna", "Maksim"]
    assert manifest.axioms == [
        "pos('Diana') < pos('Ilya')",
        "pos('Ilya') < pos('Sofya')",
        "pos('Sofya') + 1 == pos('Lera')",
    ]
    assert manifest.hypotheses["SofiaAuthor"][0] == "author == 'Sofya'"

    verification = verify_logic(manifest)
    assert verification.stable_worlds > 0
    assert {branch.branch for branch in verification.branches} == {"SofiaAuthor", "AnnaAuthor"}


def test_parse_logic_manifest_handles_loose_alias_format() -> None:
    manifest = parse_logic_manifest(
        """
ENTITIES: Elisey, Diana, Ilya, Sofya, Lera, Anna, Maksim
AXIOMS:
- elisey_pos == 1 or 7
- diana_pos < ilya_pos < author_pos
- sofiya_pos + 1 = lera_pos
HYPOTHESES:
Branch 1:
- author = 'Sofya'
- elisey_pos == 1
- maxim_pos == 8 (invalid)
"""
    )

    assert manifest.axioms[0] == "(pos('Elisey') == 0 or pos('Elisey') == 6)"
    assert manifest.axioms[1] == "pos('Diana') < pos('Ilya') < author_pos"
    assert manifest.axioms[2] == "pos('Sofya') + 1 == pos('Lera')"
    assert manifest.hypotheses["Branch 1"][0] == "author == 'Sofya'"
    assert "invalid" not in " ".join(manifest.hypotheses["Branch 1"])


def test_logic_parse_endpoint(monkeypatch, tmp_path) -> None:
    app = create_app(str(tmp_path))
    client = TestClient(app)

    monkeypatch.setattr(
        "kobold_sandbox.kobold_client.KoboldClient.chat",
        lambda self, prompt, model=None, system_prompt=None, config=None: {
            "choices": [{"message": {"content": MANIFEST_TEXT}}]
        },
    )

    response = client.post("/api/logic/parse", json={"analysis_text": "demo reasoning"})

    assert response.status_code == 200
    payload = response.json()
    assert payload["manifest"]["entities"][0] == "Elisey"
    assert payload["verification"]["stable_worlds"] > 0


def test_logic_parse_structured_endpoint(monkeypatch, tmp_path) -> None:
    app = create_app(str(tmp_path))
    client = TestClient(app)

    monkeypatch.setattr(
        "kobold_sandbox.kobold_client.KoboldClient.chat",
        lambda self, prompt, model=None, system_prompt=None, config=None: {
            "choices": [
                {
                    "message": {
                        "content": """
ENTITIES: [Elisey, Diana, Ilya, Sofya, Lera, Anna, Maksim]
RULES:
- before(Diana, Ilya)
- before(Ilya, $author)
BRANCHES:
Sofia:
- author(Sofya)
"""
                    }
                }
            ]
        },
    )

    response = client.post("/api/logic/parse-structured", json={"analysis_text": "demo"})

    assert response.status_code == 200
    payload = response.json()
    assert payload["linear_schema"]["rules"][0] == "before(Diana, Ilya)"
    assert payload["manifest"]["axioms"][0] == "pos('Diana') < pos('Ilya')"
    assert payload["puzzle_schema"] is None
    assert payload["sieve_state"] is None
    assert payload["stage_counts"] is None


def test_chat_page_renders(tmp_path) -> None:
    client = TestClient(create_app(str(tmp_path)))
    response = client.get("/chat")

    assert response.status_code == 200
    assert "Kobold Sandbox" in response.text
    assert "Image Generation" in response.text
    assert "chatTranscript" in response.text
    assert "modalGenerateImage" in response.text
    assert "sessionList" in response.text
    assert "newSession" in response.text
    assert 'data-tab="chatTab"' in response.text
    assert 'data-tab="imageTab"' in response.text


def test_parse_linear_logic_schema_and_bridge() -> None:
    schema = parse_linear_logic_schema(
        """
ENTITIES: [Elisey, Diana, Ilya, Sofya, Lera, Anna, Maksim]
RULES:
- before(Diana, Ilya)
- before(Ilya, $author)
- immediate_after(Lera, Sofya)
- one_of(Elisey, [0, 6])
BRANCHES:
Sofia:
- author(Sofya)
- at(Elisey, 0)
"""
    )

    assert schema.rules[0] == "before(Diana, Ilya)"
    manifest = linear_schema_to_manifest(schema)
    assert manifest.axioms[0] == "pos('Diana') < pos('Ilya')"
    assert manifest.axioms[1] == "pos('Ilya') < author_pos"
    assert manifest.axioms[2] == "pos('Lera') == pos('Sofya') + 1"
    assert manifest.hypotheses["Sofia"][0] == "author == 'Sofya'"


def test_parse_linear_logic_schema_supports_relation_style_rules() -> None:
    schema = parse_linear_logic_schema(
        """
ENTITIES: [nation:English, color:Red, nation:Norwegian, color:Blue]
RULES:
- same(nation:English, color:Red)
- next_to(nation:Norwegian, color:Blue)
- directly_right(color:White, color:Green)
- at(nation:Norwegian, 0)
BRANCHES:
"""
    )

    manifest = linear_schema_to_manifest(schema)

    assert manifest.axioms[0] == "pos('nation:English') == pos('color:Red')"
    assert manifest.axioms[1] == "abs(pos('nation:Norwegian') - pos('color:Blue')) == 1"
    assert manifest.axioms[2] == "pos('color:Green') == pos('color:White') + 1"
    assert manifest.axioms[3] == "pos('nation:Norwegian') == 0"


def test_logic_parse_structured_endpoint_emits_puzzle_schema_when_convertible(monkeypatch, tmp_path) -> None:
    app = create_app(str(tmp_path))
    client = TestClient(app)

    monkeypatch.setattr(
        "kobold_sandbox.kobold_client.KoboldClient.chat",
        lambda self, prompt, model=None, system_prompt=None, config=None: {
            "choices": [
                {
                    "message": {
                        "content": """
ENTITIES: [nation:English, color:Red, nation:Norwegian, color:Blue, color:White, color:Green]
RULES:
- same(nation:English, color:Red)
- next_to(nation:Norwegian, color:Blue)
- directly_right(color:White, color:Green)
- at(nation:Norwegian, 0)
BRANCHES:
"""
                    }
                }
            ]
        },
    )

    response = client.post("/api/logic/parse-structured", json={"analysis_text": "demo"})

    assert response.status_code == 200
    payload = response.json()
    assert payload["puzzle_schema"] is not None
    assert payload["puzzle_schema"]["categories"]["nation"] == ["English", "Norwegian"]
    assert payload["puzzle_schema"]["rules"][0]["type"] == "same"
    assert payload["sieve_state"] is None
    assert payload["stage_counts"] is not None
    assert "# Structured Puzzle Stage Counts" in payload["stage_counts"]


def test_chat_endpoint_includes_nickname_and_context(monkeypatch, tmp_path) -> None:
    app = create_app(str(tmp_path))
    client = TestClient(app)

    monkeypatch.setattr(
        "kobold_sandbox.kobold_client.KoboldClient.chat",
        lambda self, prompt, model=None, system_prompt=None, config=None: {
            "choices": [{"message": {"content": "ok"}}]
        },
    )

    response = client.post(
        "/api/chat",
        json={
            "nickname": "Airy",
            "user_context": "Brief and direct.",
            "system_prompt": "Be concise.",
            "message": "Hello",
        },
    )

    assert response.status_code == 200
    payload = response.json()
    assert "User nickname: Airy" in payload["composed_prompt"]
    assert "Brief and direct." in payload["composed_prompt"]
    assert payload["response_text"] == "ok"


def test_chat_endpoint_uses_prior_history(monkeypatch, tmp_path) -> None:
    app = create_app(str(tmp_path))
    client = TestClient(app)
    seen_prompts: list[str] = []

    def fake_chat(self, prompt, model=None, system_prompt=None, config=None):
        seen_prompts.append(prompt)
        return {"choices": [{"message": {"content": f"reply-{len(seen_prompts)}"}}]}

    monkeypatch.setattr("kobold_sandbox.kobold_client.KoboldClient.chat", fake_chat)

    first = client.post("/api/chat", json={"message": "Hello"}).json()
    second = client.post("/api/chat", json={"message": "How are you?"}).json()

    assert first["history_size"] == 2
    assert second["history_size"] == 4
    assert "Conversation so far:" in seen_prompts[1]
    assert "User: Hello" in seen_prompts[1]
    assert "Assistant: reply-1" in seen_prompts[1]
    assert seen_prompts[1].rstrip().endswith("Assistant:")


def test_chat_reset_clears_history_and_log(monkeypatch, tmp_path) -> None:
    app = create_app(str(tmp_path))
    client = TestClient(app)

    monkeypatch.setattr(
        "kobold_sandbox.kobold_client.KoboldClient.chat",
        lambda self, prompt, model=None, system_prompt=None, config=None: {
            "choices": [{"message": {"content": "ok"}}]
        },
    )

    client.post("/api/chat", json={"message": "Hello"})
    reset = client.post("/api/chat/reset")
    history = client.get("/api/chat/history")
    log = client.get("/api/chat/log")

    assert reset.status_code == 200
    assert history.json()["messages"] == []
    assert log.json()["entries"] == []


def test_chat_sessions_are_isolated(monkeypatch, tmp_path) -> None:
    app = create_app(str(tmp_path))
    client = TestClient(app)

    monkeypatch.setattr(
        "kobold_sandbox.kobold_client.KoboldClient.chat",
        lambda self, prompt, model=None, system_prompt=None, config=None: {
            "choices": [{"message": {"content": "ok"}}]
        },
    )

    created = client.post("/api/chat/sessions", json={"title": "Second"}).json()["session"]
    client.post("/api/chat", json={"session_id": "default", "message": "Hello"})
    client.post("/api/chat", json={"session_id": created["id"], "message": "Other"})

    default_log = client.get("/api/chat/log?session_id=default").json()
    second_log = client.get(f"/api/chat/log?session_id={created['id']}").json()
    sessions = client.get("/api/chat/sessions").json()["sessions"]

    assert len(default_log["entries"]) == 1
    assert default_log["entries"][0]["request"]["message"] == "Hello"
    assert len(second_log["entries"]) == 1
    assert second_log["entries"][0]["request"]["message"] == "Other"
    assert {item["id"] for item in sessions} >= {"default", created["id"]}


def test_chat_endpoint_preserves_completed_think(monkeypatch, tmp_path) -> None:
    app = create_app(str(tmp_path))
    client = TestClient(app)

    monkeypatch.setattr(
        "kobold_sandbox.kobold_client.KoboldClient.chat",
        lambda self, prompt, model=None, system_prompt=None, config=None: {
            "choices": [{"message": {"content": "<think>plan</think>answer"}}]
        },
    )

    response = client.post("/api/chat", json={"message": "Hello"})

    assert response.status_code == 200
    payload = response.json()
    assert payload["response_text"] == "<think>plan</think>answer"


def test_imagegen_endpoint(monkeypatch, tmp_path) -> None:
    app = create_app(str(tmp_path))
    client = TestClient(app)

    monkeypatch.setattr(
        "kobold_sandbox.kobold_client.KoboldClient.generate_image",
        lambda self, **kwargs: {"images": ["ZmFrZS1wbmc="], "parameters": kwargs, "info": "{}"},
    )

    response = client.post(
        "/api/imagegen",
        json={
            "prompt": "red cube",
            "negative_prompt": "blurry",
            "steps": 6,
            "width": 512,
            "height": 512,
            "sampler_name": "Euler",
        },
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["kind"] == "imagegen"
    assert payload["request"]["prompt"] == "red cube"
    assert payload["preview_image"] == "ZmFrZS1wbmc="
    assert payload["raw_response"]["image_count"] == 1
    assert "images" not in payload["raw_response"]
