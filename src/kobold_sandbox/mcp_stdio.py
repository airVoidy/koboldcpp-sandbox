from __future__ import annotations

import json
import sys
from io import TextIOBase

from fastapi.testclient import TestClient

from .server import create_app


def _jsonrpc_error(request_id: object, code: int, message: str) -> dict:
    return {
        "jsonrpc": "2.0",
        "id": request_id,
        "error": {
            "code": code,
            "message": message,
        },
    }


def run_stdio_session(root: str, instream: TextIOBase, outstream: TextIOBase) -> None:
    client = TestClient(create_app(root))
    for raw_line in instream:
        line = raw_line.strip()
        if not line:
            continue
        try:
            payload = json.loads(line)
        except json.JSONDecodeError:
            response_payload = _jsonrpc_error(None, -32700, "Parse error")
        else:
            response = client.post("/api/mcp", json=payload)
            response_payload = response.json()
        outstream.write(json.dumps(response_payload, ensure_ascii=False) + "\n")
        outstream.flush()


def main() -> None:
    root = sys.argv[1] if len(sys.argv) > 1 else "."
    run_stdio_session(root, sys.stdin, sys.stdout)


if __name__ == "__main__":
    main()
