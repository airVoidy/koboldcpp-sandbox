from __future__ import annotations

import json
import urllib.request


BASE_URL = "http://127.0.0.1:8060/api/mcp"


def rpc(method: str, params: dict | None = None, request_id: int = 1) -> dict:
    payload = {
        "jsonrpc": "2.0",
        "id": request_id,
        "method": method,
        "params": params or {},
    }
    request = urllib.request.Request(
        BASE_URL,
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(request) as response:
        return json.loads(response.read().decode("utf-8"))


def dump(title: str, payload: dict) -> None:
    print(f"\n== {title} ==")
    print(json.dumps(payload, ensure_ascii=False, indent=2))


def main() -> None:
    dump("initialize", rpc("initialize", request_id=1))
    dump("tools/list", rpc("tools/list", request_id=2))

    dump(
        "atoms.evaluate",
        rpc(
            "tools/call",
            {
                "name": "atoms.evaluate",
                "arguments": {
                    "atom_id": "a1",
                    "expression": "assert x == 2",
                    "variables": ["x"],
                    "context": {"x": 2},
                },
            },
            request_id=3,
        ),
    )

    dump(
        "sandbox.graph",
        rpc(
            "tools/call",
            {"name": "sandbox.graph", "arguments": {}},
            request_id=4,
        ),
    )

    created = rpc(
        "tools/call",
        {
            "name": "sandbox.create_node",
            "arguments": {
                "parent_id": "root",
                "title": "Japan report",
                "summary": "Need structured facts for the report",
                "tags": ["report", "japan"],
            },
        },
        request_id=5,
    )
    dump("sandbox.create_node", created)

    node_id = created["result"]["structuredContent"]["id"]

    dump(
        "sandbox.update_notes",
        rpc(
            "tools/call",
            {
                "name": "sandbox.update_notes",
                "arguments": {
                    "node_id": node_id,
                    "content": "# Japan report\n\n## Goal\n\nCollect concise facts.\n",
                },
            },
            request_id=6,
        ),
    )


if __name__ == "__main__":
    main()
