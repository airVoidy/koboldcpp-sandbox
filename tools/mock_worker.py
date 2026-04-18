from __future__ import annotations

import json
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer


HOST = "127.0.0.1"
PORT = 5001


def _json_bytes(payload: dict) -> bytes:
    return json.dumps(payload, ensure_ascii=False).encode("utf-8")


def _extract_last_user(messages: list[dict]) -> str:
    for item in reversed(messages or []):
        if item.get("role") == "user":
            return str(item.get("content") or "")
    return ""


def _mock_reply(text: str) -> str:
    value = (text or "").strip()
    lower = value.lower()
    if not value:
        return "empty input"
    if "ping" in lower:
        return "pong"
    if "status" in lower:
        return "status: ok\nworker: mock\nmode: local"
    return (
        f"mock-worker reply\n\n"
        f"echo: {value}\n\n"
        f"notes:\n"
        f"- local worker is up\n"
        f"- model backend is mocked\n"
        f"- good for transport/UI tests"
    )


class Handler(BaseHTTPRequestHandler):
    server_version = "MockWorker/0.1"

    def log_message(self, format: str, *args) -> None:
        return

    def _send_json(self, status: int, payload: dict) -> None:
        body = _json_bytes(payload)
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Headers", "Content-Type, Authorization")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.end_headers()
        self.wfile.write(body)

    def _read_json(self) -> dict:
        length = int(self.headers.get("Content-Length", "0") or "0")
        if length <= 0:
            return {}
        raw = self.rfile.read(length)
        if not raw:
            return {}
        return json.loads(raw.decode("utf-8"))

    def do_OPTIONS(self) -> None:
        self.send_response(204)
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Headers", "Content-Type, Authorization")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.end_headers()

    def do_GET(self) -> None:
        if self.path == "/api/extra/version":
            self._send_json(
                200,
                {
                    "name": "mock-worker",
                    "version": "0.1",
                    "mode": "local",
                    "time": int(time.time()),
                },
            )
            return

        if self.path == "/v1/models":
            self._send_json(
                200,
                {
                    "object": "list",
                    "data": [
                        {
                            "id": "mock-echo-1",
                            "object": "model",
                            "created": int(time.time()),
                            "owned_by": "local",
                        }
                    ],
                },
            )
            return

        if self.path == "/api/v1/model":
            self._send_json(200, {"result": "mock-echo-1"})
            return

        self._send_json(404, {"error": "not found", "path": self.path})

    def do_POST(self) -> None:
        if self.path == "/v1/chat/completions":
            body = self._read_json()
            messages = body.get("messages") or []
            reply = _mock_reply(_extract_last_user(messages))
            self._send_json(
                200,
                {
                    "id": "chatcmpl-mock",
                    "object": "chat.completion",
                    "created": int(time.time()),
                    "model": body.get("model") or "mock-echo-1",
                    "choices": [
                        {
                            "index": 0,
                            "finish_reason": "stop",
                            "message": {
                                "role": "assistant",
                                "content": reply,
                            },
                        }
                    ],
                },
            )
            return

        if self.path == "/api/v1/generate":
            body = self._read_json()
            reply = _mock_reply(str(body.get("prompt") or ""))
            self._send_json(
                200,
                {
                    "results": [
                        {
                            "text": reply,
                        }
                    ]
                },
            )
            return

        self._send_json(404, {"error": "not found", "path": self.path})


def main() -> None:
    httpd = ThreadingHTTPServer((HOST, PORT), Handler)
    print(f"mock worker listening on http://{HOST}:{PORT}", flush=True)
    httpd.serve_forever()


if __name__ == "__main__":
    main()
