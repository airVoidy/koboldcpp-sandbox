"""
KernelSession — thin lifecycle wrapper over jupyter_client.

Manages one kernel process: start/stop, code execution, variable fetch.
All I/O goes through ZMQ Shell + IOPub channels (standard Jupyter wire protocol).
"""

from __future__ import annotations

import json
import queue
from typing import Any

try:
    from jupyter_client.manager import KernelManager
    _HAS_JUPYTER = True
except ImportError:
    _HAS_JUPYTER = False


_TIMEOUT = 30  # seconds for kernel replies


class KernelSession:
    """One kernel process with a client channel pair."""

    def __init__(self, kernel_name: str = "python3"):
        if not _HAS_JUPYTER:
            raise RuntimeError(
                "jupyter_client is not installed. "
                "Run: pip install jupyter_client ipykernel"
            )
        self._km = KernelManager(kernel_name=kernel_name)
        self._kc = None
        self.kernel_name = kernel_name

    # ── lifecycle ────────────────────────────────────────────────────────────

    def start(self) -> "KernelSession":
        self._km.start_kernel()
        self._kc = self._km.client()
        self._kc.start_channels()
        self._kc.wait_for_ready(timeout=_TIMEOUT)
        return self

    def stop(self) -> None:
        if self._kc:
            self._kc.stop_channels()
        self._km.shutdown_kernel(now=True)
        self._kc = None

    def __enter__(self) -> "KernelSession":
        return self.start()

    def __exit__(self, *_) -> None:
        self.stop()

    # ── execution ────────────────────────────────────────────────────────────

    def run(self, code: str) -> dict:
        """Execute code, return {status, output, error}."""
        self._require_started()
        msg_id = self._kc.execute(code, silent=False)
        return self._collect(msg_id)

    def eval_json(self, expr: str) -> Any:
        """Evaluate expression, return Python value via JSON round-trip."""
        result = self.run(f"import json as _j; print(_j.dumps({expr}))")
        if result["status"] != "ok":
            raise RuntimeError(f"Kernel error: {result['error']}")
        raw = result["output"].strip()
        return json.loads(raw)

    # ── internal ─────────────────────────────────────────────────────────────

    def _require_started(self) -> None:
        if self._kc is None:
            raise RuntimeError("KernelSession not started — call .start() first")

    def _collect(self, msg_id: str) -> dict:
        output_parts: list[str] = []
        error_text: str = ""
        status: str = "ok"

        while True:
            try:
                msg = self._kc.get_iopub_msg(timeout=_TIMEOUT)
            except queue.Empty:
                status = "timeout"
                break

            msg_type = msg["msg_type"]
            content = msg.get("content", {})

            if msg_type == "stream":
                output_parts.append(content.get("text", ""))
            elif msg_type == "error":
                status = "error"
                error_text = "\n".join(content.get("traceback", [content.get("evalue", "")]))
            elif msg_type == "status" and content.get("execution_state") == "idle":
                # Check that this idle belongs to our execute request
                parent_id = msg.get("parent_header", {}).get("msg_id", "")
                if parent_id == msg_id:
                    break

        return {
            "status": status,
            "output": "".join(output_parts),
            "error": error_text,
        }
