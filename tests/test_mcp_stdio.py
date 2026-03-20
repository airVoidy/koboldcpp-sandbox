import json
from io import StringIO

from kobold_sandbox.mcp_stdio import run_stdio_session
from kobold_sandbox.storage import Sandbox


def test_mcp_stdio_session_handles_initialize_and_tool_call(tmp_path) -> None:
    sandbox = Sandbox(tmp_path)
    sandbox.init(
        sandbox_name="test-sandbox",
        kobold_url="http://localhost:5001",
        root_title="Root hypothesis",
    )

    instream = StringIO(
        json.dumps({"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {}})
        + "\n"
        + json.dumps(
            {
                "jsonrpc": "2.0",
                "id": 2,
                "method": "tools/call",
                "params": {
                    "name": "sandbox.graph",
                    "arguments": {},
                },
            }
        )
        + "\n"
    )
    outstream = StringIO()

    run_stdio_session(str(tmp_path), instream, outstream)

    lines = [json.loads(line) for line in outstream.getvalue().splitlines() if line.strip()]
    assert lines[0]["result"]["serverInfo"]["name"] == "kobold-sandbox"
    assert lines[1]["result"]["structuredContent"]["active_node_id"] == "root"


def test_mcp_stdio_session_returns_parse_error(tmp_path) -> None:
    outstream = StringIO()

    run_stdio_session(str(tmp_path), StringIO("{not-json}\n"), outstream)

    payload = json.loads(outstream.getvalue().strip())
    assert payload["error"]["code"] == -32700
    assert payload["error"]["message"] == "Parse error"
