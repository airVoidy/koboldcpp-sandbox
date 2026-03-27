from fastapi.testclient import TestClient

from kobold_sandbox.server import create_app


def test_atomic_wiki_upsert_and_get_page(tmp_path) -> None:
    client = TestClient(create_app(str(tmp_path)))

    response = client.put(
        "/api/atomic-wiki/pages/extract_constraints_instruction",
        json={
            "title": "$config.extract_constraints_instruction",
            "item_kind": "text",
            "text": "Extract constraints from the task.",
            "tags": ["config", "wikilike"],
            "auto_commit": True,
            "commit_message": "Add extract constraints instruction wiki page",
        },
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["page"]["slug"] == "extract_constraints_instruction"
    assert payload["page"]["message"]["text"] == "Extract constraints from the task."
    assert payload["commit"]

    page_response = client.get("/api/atomic-wiki/pages/extract_constraints_instruction")
    assert page_response.status_code == 200
    page = page_response.json()
    assert page["title"] == "$config.extract_constraints_instruction"
    assert page["item_kind"] == "text"
    assert page["aliases"] == ["$config.extract_constraints_instruction"]


def test_atomic_wiki_migrates_global_params_to_message_pages(tmp_path) -> None:
    client = TestClient(create_app(str(tmp_path)))

    response = client.post(
        "/api/atomic-wiki/migrate/global-params",
        json={
            "atomic_params": {
                "extract_constraints_instruction": "Extract strict constraints.",
            },
            "global_items": [
                {
                    "type": "text",
                    "name": "task_a_prompt",
                    "text": "Write 4 demoness descriptions in anime style.",
                },
                {
                    "type": "table",
                    "name": "task_a_axes",
                    "headers": ["axis", "value"],
                    "rows": [["eyes", "amber"], ["hair", "black"]],
                },
            ],
            "auto_commit": True,
            "commit_message": "Migrate global params to wiki pages",
        },
    )

    assert response.status_code == 200
    payload = response.json()
    assert "extract_constraints_instruction" in payload["migrated"]
    assert "task_a_prompt" in payload["migrated"]
    assert "task_a_axes" in payload["migrated"]
    assert payload["commit"]

    list_response = client.get("/api/atomic-wiki/pages")
    assert list_response.status_code == 200
    pages = {page["slug"]: page for page in list_response.json()["pages"]}
    assert "extract_constraints_instruction" in pages
    assert "task_a_prompt" in pages
    assert "task_a_axes" in pages

    param_page = client.get("/api/atomic-wiki/pages/extract_constraints_instruction").json()
    assert param_page["item_kind"] == "param"
    assert param_page["message"]["text"] == "Extract strict constraints."

    table_page = client.get("/api/atomic-wiki/pages/task_a_axes").json()
    assert table_page["item_kind"] == "table"
    assert table_page["blocks"][0]["headers"] == ["axis", "value"]
    assert table_page["blocks"][0]["rows"][0] == ["eyes", "amber"]

    log_response = client.get("/api/atomic-wiki/git/log")
    assert log_response.status_code == 200
    commits = log_response.json()["commits"]
    assert any(commit["message"] == "Migrate global params to wiki pages" for commit in commits)
