from fastapi.testclient import TestClient

from kobold_sandbox.server import create_app


def test_behavior_template_and_tree_endpoints_return_json(tmp_path) -> None:
    client = TestClient(create_app(str(tmp_path)))

    template = client.get("/api/behavior/template")
    tree = client.get("/api/behavior/tree")

    assert template.status_code == 200
    assert template.json()["template"]["tree_id"] == "character-description-reference"
    assert template.json()["path"].endswith("character_description_reference_tree.json")
    assert tree.status_code == 200
    assert tree.headers["etag"].startswith('W/"rev-')
    assert tree.headers["last-modified"]
    assert tree.json()["nodes"]["root"]["kind"] == "description_root"


def test_behavior_node_update_and_run_endpoints_are_reactive(tmp_path) -> None:
    client = TestClient(create_app(str(tmp_path)))

    node_response = client.get("/api/behavior/nodes/description-02")
    node_payload = node_response.json()
    start_revision = node_payload["revision"]
    node_payload["data"]["style"] = "baroque neon"
    node_payload["elements"][1]["handler"] = "local_check_v2"

    updated = client.post(
        "/api/behavior/nodes/description-02",
        json={"payload": node_payload, "expected_revision": start_revision},
    )
    fetched = client.get("/api/behavior/nodes/description-02")

    assert updated.status_code == 200
    assert updated.json()["data"]["style"] == "baroque neon"
    assert updated.json()["revision"] > start_revision
    assert fetched.json()["elements"][1]["handler"] == "local_check_v2"
    assert node_response.headers["etag"].startswith('W/"rev-')


def test_behavior_run_endpoints_execute_reference_tree(tmp_path) -> None:
    client = TestClient(create_app(str(tmp_path)))

    node_run = client.post("/api/behavior/nodes/description-01/run?sync=true")
    tree_run = client.post("/api/behavior/run?sync=true")

    assert node_run.status_code == 200
    assert node_run.json()["record"]["executed_elements"] == ["draft", "local_check", "repair", "compress", "audit"]
    assert node_run.json()["node"]["data"]["repair_count"] == 1

    assert tree_run.status_code == 200
    payload = tree_run.json()
    assert len(payload["outputs"]) == 10
    assert payload["tree"]["nodes"]["root"]["data"]["outputs"]


def test_behavior_tree_update_endpoint_can_modify_global_meta(tmp_path) -> None:
    client = TestClient(create_app(str(tmp_path)))

    tree_payload = client.get("/api/behavior/tree").json()
    start_revision = tree_payload["revision"]
    tree_payload["global_meta"]["task"] = "rewritten task"

    response = client.post(
        "/api/behavior/tree",
        json={"payload": tree_payload, "expected_revision": start_revision},
    )

    assert response.status_code == 200
    assert response.json()["global_meta"]["task"] == "rewritten task"
    assert response.json()["revision"] > start_revision


def test_behavior_api_isolates_tree_state_by_session_id(tmp_path) -> None:
    client = TestClient(create_app(str(tmp_path)))

    session_a = client.get("/api/behavior/tree?session_id=a").json()
    session_b = client.get("/api/behavior/tree?session_id=b").json()
    session_a["global_meta"]["task"] = "session-a task"

    client.post("/api/behavior/tree?session_id=a", json={"payload": session_a})
    fetched_a = client.get("/api/behavior/tree?session_id=a").json()
    fetched_b = client.get("/api/behavior/tree?session_id=b").json()

    assert fetched_a["global_meta"]["task"] == "session-a task"
    assert fetched_b["global_meta"]["task"] != "session-a task"


def test_behavior_node_update_rejects_stale_revision(tmp_path) -> None:
    client = TestClient(create_app(str(tmp_path)))

    node_payload = client.get("/api/behavior/nodes/description-03").json()
    current_revision = node_payload["revision"]
    node_payload["data"]["style"] = "session-one-style"

    first = client.post(
        "/api/behavior/nodes/description-03",
        json={"payload": node_payload, "expected_revision": current_revision},
    )
    stale = client.post(
        "/api/behavior/nodes/description-03",
        json={"payload": node_payload, "expected_revision": current_revision},
    )

    assert first.status_code == 200
    assert stale.status_code == 409
    assert stale.json()["detail"]["error"] == "revision_conflict"


def test_behavior_tree_update_rejects_stale_revision(tmp_path) -> None:
    client = TestClient(create_app(str(tmp_path)))

    tree_payload = client.get("/api/behavior/tree").json()
    current_revision = tree_payload["revision"]
    tree_payload["global_meta"]["task"] = "first update"

    first = client.post(
        "/api/behavior/tree",
        json={"payload": tree_payload, "expected_revision": current_revision},
    )
    stale = client.post(
        "/api/behavior/tree",
        json={"payload": tree_payload, "expected_revision": current_revision},
    )

    assert first.status_code == 200
    assert stale.status_code == 409
    assert stale.json()["detail"]["error"] == "revision_conflict"


def test_behavior_tree_update_accepts_if_match_header(tmp_path) -> None:
    client = TestClient(create_app(str(tmp_path)))

    tree_response = client.get("/api/behavior/tree")
    tree_payload = tree_response.json()
    tree_payload["global_meta"]["task"] = "etag update"

    response = client.post(
        "/api/behavior/tree",
        headers={"If-Match": tree_response.headers["etag"]},
        json={"payload": tree_payload},
    )

    assert response.status_code == 200
    assert response.json()["global_meta"]["task"] == "etag update"
    assert response.headers["etag"].startswith('W/"rev-')
    assert response.headers["last-modified"]
    assert response.headers["x-behavior-merge"] == "none"


def test_behavior_node_update_rejects_stale_if_match_header(tmp_path) -> None:
    client = TestClient(create_app(str(tmp_path)))

    node_response = client.get("/api/behavior/nodes/description-04")
    node_payload = node_response.json()
    stale_etag = node_response.headers["etag"]
    node_payload["data"]["style"] = "first style"
    client.post(
        "/api/behavior/nodes/description-04",
        headers={"If-Match": stale_etag},
        json={"payload": node_payload},
    )

    node_payload["data"]["style"] = "second style"
    stale = client.post(
        "/api/behavior/nodes/description-04",
        headers={"If-Match": stale_etag},
        json={"payload": node_payload},
    )

    assert stale.status_code == 409
    assert stale.json()["detail"]["error"] == "revision_conflict"


def test_behavior_tree_patch_updates_only_requested_fields(tmp_path) -> None:
    client = TestClient(create_app(str(tmp_path)))

    tree_response = client.get("/api/behavior/tree")
    patch = {"global_meta": {"task": "patched task"}}

    response = client.patch(
        "/api/behavior/tree",
        headers={"If-Match": tree_response.headers["etag"]},
        json={"patch": patch},
    )

    assert response.status_code == 200
    assert response.json()["global_meta"]["task"] == "patched task"
    assert response.json()["nodes"]["root"]["kind"] == "description_root"


def test_behavior_node_patch_can_merge_non_overlapping_stale_changes(tmp_path) -> None:
    client = TestClient(create_app(str(tmp_path)))

    node_response = client.get("/api/behavior/nodes/description-05")
    stale_etag = node_response.headers["etag"]

    first = client.patch(
        "/api/behavior/nodes/description-05",
        headers={"If-Match": stale_etag},
        json={"patch": {"data": {"style": "first style"}}},
    )
    merged = client.patch(
        "/api/behavior/nodes/description-05",
        headers={"If-Match": stale_etag},
        json={"patch": {"data": {"hair_color": "deep red"}}, "merge_on_conflict": True},
    )

    assert first.status_code == 200
    assert merged.status_code == 200
    assert merged.json()["data"]["style"] == "first style"
    assert merged.json()["data"]["hair_color"] == "deep red"
    assert first.headers["x-behavior-merge"] == "none"
    assert merged.headers["x-behavior-merge"] == "applied"


def test_behavior_node_patch_rejects_overlapping_stale_changes(tmp_path) -> None:
    client = TestClient(create_app(str(tmp_path)))

    node_response = client.get("/api/behavior/nodes/description-06")
    stale_etag = node_response.headers["etag"]

    client.patch(
        "/api/behavior/nodes/description-06",
        headers={"If-Match": stale_etag},
        json={"patch": {"data": {"style": "first style"}}},
    )
    stale = client.patch(
        "/api/behavior/nodes/description-06",
        headers={"If-Match": stale_etag},
        json={"patch": {"data": {"style": "second style"}}, "merge_on_conflict": True},
    )

    assert stale.status_code == 409
    assert stale.json()["detail"]["error"] == "revision_conflict"
