#!/usr/bin/env python3
"""
KoboldCpp No-Think Proxy
========================
Transparent reverse-proxy that:
  1. Injects an empty <thinking></thinking> block into the assistant's
     response prefix so the model believes it already "thought" and
     goes straight to answering.
  2. Strips any <thinking>…</thinking> / <think>…</think> blocks that
     still leak through in the output.

Usage:
    python kobold_nothink_proxy.py                                   # defaults
    python kobold_nothink_proxy.py --port 5055 --target http://localhost:5050
    python kobold_nothink_proxy.py --strip-only                      # don't inject, only clean output

Flags:
    --port        PORT  Local proxy port           (default: 5055)
    --target      URL   Upstream KoboldCpp URL     (default: http://localhost:5050)
    --strip-only        Only strip thinking from output, don't inject prefix
"""

import argparse
import json
import re
import sys
from http.server import BaseHTTPRequestHandler, HTTPServer
from urllib.error import HTTPError, URLError
from urllib.parse import urljoin
from urllib.request import Request, urlopen

# ── regex ────────────────────────────────────────────────────────────

THINK_RE = re.compile(r"<thinking>.*?</thinking>\s*", re.DOTALL)
THINK_SHORT_RE = re.compile(r"<think>.*?</think>\s*", re.DOTALL)
# Match our injected empty prefix specifically
THINK_EMPTY_RE = re.compile(r"<think>\s*</think>\s*", re.DOTALL)

# The prefix we inject — an already-closed thinking block with double newlines.
# Combined with continue_assistant_turn: true, KoboldCpp sees thinking as
# already done and generates content directly.
NO_THINK_PREFIX = "<think>\n\n</think>\n\n"


def strip_thinking(text: str) -> str:
    """Remove all <thinking>…</thinking> and <think>…</think> blocks."""
    text = THINK_RE.sub("", text)
    text = THINK_SHORT_RE.sub("", text)
    return text.strip()


# ── request mutation ─────────────────────────────────────────────────


def inject_empty_think(body: dict) -> dict:
    """
    Add an assistant message with a closed <think> block at the end
    of the messages list (OpenAI format), or append it to the prompt
    (native KoboldCpp format).  Also sets continue_assistant_turn: true
    so KoboldCpp continues from after the think block.

    This tricks the model into believing it already performed CoT.
    """
    # OpenAI chat format  /v1/chat/completions
    if "messages" in body and isinstance(body["messages"], list):
        msgs = body["messages"]
        # If the last message is already from assistant with our prefix, skip
        if msgs and msgs[-1].get("role") == "assistant":
            content = msgs[-1].get("content", "")
            if (
                isinstance(content, str)
                and "<think>" in content
                and "</think>" in content
            ):
                body["continue_assistant_turn"] = True
                return body
        # Append a partial assistant message with closed think block
        msgs.append(
            {
                "role": "assistant",
                "content": NO_THINK_PREFIX,
            }
        )
        body["continue_assistant_turn"] = True

    # Native KoboldCpp  /api/v1/generate
    elif "prompt" in body and isinstance(body["prompt"], str):
        if "</think>" not in body["prompt"]:
            body["prompt"] = body["prompt"] + NO_THINK_PREFIX

    return body


# ── SSE streaming ────────────────────────────────────────────────────


class ThinkingStripper:
    """
    Stateful per-stream filter that buffers tokens while inside a
    <thinking> block and drops them.  Tokens outside thinking blocks
    pass through immediately.
    """

    def __init__(self):
        self._inside = False
        self._buf = ""
        self._suppressed_prefix = True  # suppress our injected prefix echo

    def feed(self, token: str) -> str:
        """Return the portion of `token` that should be forwarded."""
        out = []
        for ch in token:
            self._buf += ch

            # Detect opening tag
            if not self._inside:
                if self._buf.endswith("<thinking>") or self._buf.endswith("<think>"):
                    # Everything before the tag was already emitted char-by-char
                    self._inside = True
                    self._buf = ""
                    continue
                # Emit char if we're not in a potential tag start
                if "<" not in self._buf:
                    out.append(self._buf)
                    self._buf = ""
                elif len(self._buf) > 12:
                    # False alarm — flush buffer
                    out.append(self._buf)
                    self._buf = ""
            else:
                # Inside thinking — check for closing tag
                if self._buf.endswith("</thinking>") or self._buf.endswith("</think>"):
                    self._inside = False
                    self._buf = ""
                    # Consume trailing whitespace
                    continue

        return "".join(out)

    def flush(self) -> str:
        """Flush any remaining buffered text."""
        if self._inside:
            return ""  # drop unclosed thinking block
        result = self._buf
        self._buf = ""
        return result


def process_sse_stream(upstream_resp, wfile, do_strip: bool):
    """Read SSE stream from upstream, strip thinking, forward to client."""
    stripper = ThinkingStripper() if do_strip else None
    buffer = b""

    while True:
        chunk = upstream_resp.read(4096)
        if not chunk:
            break
        buffer += chunk
        while b"\n" in buffer:
            line, buffer = buffer.split(b"\n", 1)
            line_str = line.decode("utf-8", errors="replace")

            if line_str.startswith("data: ") and do_strip:
                data_part = line_str[6:]
                if data_part.strip() == "[DONE]":
                    wfile.write(b"data: [DONE]\n\n")
                    wfile.flush()
                    return  # stream is done
                else:
                    try:
                        obj = json.loads(data_part)

                        # OpenAI streaming format
                        for choice in obj.get("choices", []):
                            delta = choice.get("delta", {})
                            if "content" in delta and isinstance(delta["content"], str):
                                cleaned = stripper.feed(delta["content"])
                                delta["content"] = cleaned

                        # KoboldCpp streaming format
                        if "token" in obj and isinstance(obj["token"], str):
                            cleaned = stripper.feed(obj["token"])
                            obj["token"] = cleaned

                        wfile.write(f"data: {json.dumps(obj)}\n".encode())
                    except json.JSONDecodeError:
                        wfile.write(f"{line_str}\n".encode())
            else:
                wfile.write(f"{line_str}\n".encode())

            wfile.flush()

    # Flush remaining buffer
    if buffer:
        line_str = buffer.decode("utf-8", errors="replace").strip()
        if line_str:
            wfile.write(f"{line_str}\n".encode())
    # Send final [DONE] if upstream didn't
    wfile.write(b"data: [DONE]\n\n")
    wfile.flush()


# ── proxy handler ────────────────────────────────────────────────────


class ProxyHandler(BaseHTTPRequestHandler):
    target_url: str = "http://localhost:5050"
    do_inject: bool = True

    def log_message(self, fmt, *args):
        sys.stderr.write(f"[nothink-proxy] {args[0]} {args[1]}\n")

    def _proxy(self, method: str):
        url = urljoin(self.target_url, self.path)

        content_len = int(self.headers.get("Content-Length", 0))
        raw_body = self.rfile.read(content_len) if content_len > 0 else None

        is_gen = any(
            p in self.path
            for p in [
                "/v1/chat/completions",
                "/v1/completions",
                "/api/v1/generate",
                "/api/extra/generate/stream",
            ]
        )
        is_streaming = False

        if raw_body and is_gen:
            try:
                body = json.loads(raw_body)
                if self.do_inject:
                    body = inject_empty_think(body)
                is_streaming = body.get("stream", False)
                raw_body = json.dumps(body).encode()
            except (json.JSONDecodeError, AttributeError):
                pass

        headers = {}
        for key in self.headers:
            if key.lower() not in ("host", "transfer-encoding"):
                headers[key] = self.headers[key]
        if raw_body:
            headers["Content-Length"] = str(len(raw_body))

        req = Request(url, data=raw_body, headers=headers, method=method)

        try:
            resp = urlopen(req, timeout=600)
        except HTTPError as e:
            self.send_response(e.code)
            for k, v in e.headers.items():
                if k.lower() not in ("transfer-encoding",):
                    self.send_header(k, v)
            self.end_headers()
            self.wfile.write(e.read())
            return
        except URLError as e:
            self.send_response(502)
            self.end_headers()
            self.wfile.write(f"Proxy error: {e.reason}".encode())
            return

        self.send_response(resp.status)
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header(
            "Access-Control-Allow-Methods", "GET, POST, PUT, DELETE, OPTIONS"
        )
        self.send_header("Access-Control-Allow-Headers", "*")

        for k, v in resp.headers.items():
            if k.lower() not in (
                "transfer-encoding",
                "content-length" if is_streaming else "",
                "connection",
                "access-control-allow-origin",
                "access-control-allow-methods",
                "access-control-allow-headers",
            ):
                self.send_header(k, v)
        if is_streaming and is_gen:
            self.send_header("Connection", "close")
        self.end_headers()

        if is_streaming and is_gen:
            process_sse_stream(resp, self.wfile, do_strip=True)
            self.close_connection = True
        else:
            data = resp.read()
            if is_gen:
                try:
                    obj = json.loads(data)
                    for choice in obj.get("choices", []):
                        msg = choice.get("message", {})
                        if "content" in msg and isinstance(msg["content"], str):
                            msg["content"] = strip_thinking(msg["content"])
                        if "text" in choice and isinstance(choice["text"], str):
                            choice["text"] = strip_thinking(choice["text"])
                    for result in obj.get("results", []):
                        if "text" in result and isinstance(result["text"], str):
                            result["text"] = strip_thinking(result["text"])
                    data = json.dumps(obj).encode()
                except (json.JSONDecodeError, AttributeError):
                    pass
            self.wfile.write(data)

    def do_GET(self):
        self._proxy("GET")

    def do_POST(self):
        self._proxy("POST")

    def do_PUT(self):
        self._proxy("PUT")

    def do_DELETE(self):
        self._proxy("DELETE")

    def do_OPTIONS(self):
        self.send_response(204)
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header(
            "Access-Control-Allow-Methods", "GET, POST, PUT, DELETE, OPTIONS"
        )
        self.send_header("Access-Control-Allow-Headers", "*")
        self.send_header("Access-Control-Max-Age", "86400")
        self.end_headers()


# ── main ─────────────────────────────────────────────────────────────


def main():
    p = argparse.ArgumentParser(description="KoboldCpp No-Think Proxy")
    p.add_argument("--port", type=int, default=5055, help="Proxy port (default 5055)")
    p.add_argument(
        "--target", default="http://localhost:5050", help="Upstream KoboldCpp URL"
    )
    p.add_argument(
        "--strip-only",
        action="store_true",
        help="Only strip thinking from output, don't inject prefix",
    )
    args = p.parse_args()

    target = args.target.rstrip("/")
    ProxyHandler.target_url = target
    ProxyHandler.do_inject = not args.strip_only

    server = HTTPServer(("0.0.0.0", args.port), ProxyHandler)

    mode = "strip-only" if args.strip_only else "inject + strip"
    print(f"""
┌─────────────────────────────────────────────────┐
│       KoboldCpp No-Think Proxy                  │
├─────────────────────────────────────────────────┤
│  Listen:   http://0.0.0.0:{args.port:<5}                 │
│  Target:   {target:<37}│
│  Mode:     {mode:<37}│
│                                                 │
│  Method:   Inject <think></think> prefix +      │
│            continue_assistant_turn: true        │
│            Model skips CoT, answers directly.   │
│            + strip any leaked thinking blocks.  │
└─────────────────────────────────────────────────┘

Use http://localhost:{args.port} as the agent URL in multi_agent_chat.html
Press Ctrl+C to stop.
""")

    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nStopped.")
        server.shutdown()


if __name__ == "__main__":
    main()
