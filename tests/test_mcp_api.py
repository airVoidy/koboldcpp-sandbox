from fastapi.testclient import TestClient

from kobold_sandbox.server import create_app
from kobold_sandbox.storage import Sandbox


def test_mcp_initialize_and_list_tools(tmp_path) -> None:
    client = TestClient(create_app(str(tmp_path)))

    initialize_response = client.post(
        "/api/mcp",
        json={"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {}},
    )

    assert initialize_response.status_code == 200
    initialize_payload = initialize_response.json()
    assert initialize_payload["result"]["serverInfo"]["name"] == "kobold-sandbox"
    assert initialize_payload["result"]["capabilities"]["tools"]["listChanged"] is False

    tools_response = client.post(
        "/api/mcp",
        json={"jsonrpc": "2.0", "id": 2, "method": "tools/list", "params": {}},
    )

    assert tools_response.status_code == 200
    tools = tools_response.json()["result"]["tools"]
    tool_names = {tool["name"] for tool in tools}
    assert "sandbox.graph" in tool_names
    assert "atoms.evaluate" in tool_names


def test_mcp_calls_atom_tool(tmp_path) -> None:
    client = TestClient(create_app(str(tmp_path)))

    response = client.post(
        "/api/mcp",
        json={
            "jsonrpc": "2.0",
            "id": 3,
            "method": "tools/call",
            "params": {
                "name": "atoms.evaluate",
                "arguments": {
                    "atom_id": "a1",
                    "expression": "assert x == 2",
                    "variables": ["x"],
                    "context": {"x": 2},
                },
            },
        },
    )

    assert response.status_code == 200
    payload = response.json()["result"]["structuredContent"]
    assert payload["atom_id"] == "a1"
    assert payload["passed"] is True


def test_mcp_calls_sandbox_tools_after_init(tmp_path) -> None:
    sandbox = Sandbox(tmp_path)
    sandbox.init(
        sandbox_name="test-sandbox",
        kobold_url="http://localhost:5001",
        root_title="Root hypothesis",
    )
    client = TestClient(create_app(str(tmp_path)))

    graph_response = client.post(
        "/api/mcp",
        json={"jsonrpc": "2.0", "id": 4, "method": "tools/call", "params": {"name": "sandbox.graph", "arguments": {}}},
    )

    assert graph_response.status_code == 200
    graph_payload = graph_response.json()["result"]["structuredContent"]
    assert graph_payload["active_node_id"] == "root"

    create_response = client.post(
        "/api/mcp",
        json={
            "jsonrpc": "2.0",
            "id": 5,
            "method": "tools/call",
            "params": {
                "name": "sandbox.create_node",
                "arguments": {"parent_id": "root", "title": "Japan report", "summary": "Need more context"},
            },
        },
    )

    assert create_response.status_code == 200
    create_payload = create_response.json()["result"]["structuredContent"]
    assert create_payload["title"] == "Japan report"

    notes_response = client.post(
        "/api/mcp",
        json={
            "jsonrpc": "2.0",
            "id": 6,
            "method": "tools/call",
            "params": {
                "name": "sandbox.update_notes",
                "arguments": {"node_id": create_payload["id"], "content": "# Japan\n\nCollected facts."},
            },
        },
    )

    assert notes_response.status_code == 200
    assert notes_response.json()["result"]["structuredContent"]["ok"] is True
    assert sandbox.notes_path(create_payload["id"]).read_text(encoding="utf-8") == "# Japan\n\nCollected facts."
