"""Pipeline Store — local JSON key-value storage for pipeline data.

Stores pipeline state snapshots and intermediate results between runs.
Data lives in .data/pipeline_store.json within the data directory.
"""
from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Any

from fastapi import APIRouter


_FILENAME = "pipeline_store.json"


class PipelineStore:
    """In-memory store backed by a JSON file."""

    def __init__(self, data_dir: str | Path) -> None:
        self._dir = Path(data_dir)
        self._dir.mkdir(parents=True, exist_ok=True)
        self._path = self._dir / _FILENAME
        self._data: dict[str, Any] = {"slots": {}, "snapshots": {}}
        self._load()

    def _load(self) -> None:
        if self._path.exists():
            try:
                self._data = json.loads(self._path.read_text(encoding="utf-8"))
            except (json.JSONDecodeError, OSError):
                pass

    def _flush(self) -> None:
        self._path.write_text(json.dumps(self._data, ensure_ascii=False, indent=2), encoding="utf-8")

    # ── Slots ──────────────────────────────────────────

    def list_slots(self) -> dict[str, Any]:
        return dict(self._data.get("slots", {}))

    def get_slot(self, key: str) -> Any:
        slot = self._data.get("slots", {}).get(key)
        return slot

    def set_slot(self, key: str, value: Any, meta: dict | None = None) -> None:
        self._data.setdefault("slots", {})[key] = {
            "value": value,
            "meta": meta or {},
            "updated_at": time.time(),
        }
        self._flush()

    def delete_slot(self, key: str) -> bool:
        removed = self._data.get("slots", {}).pop(key, None)
        if removed is not None:
            self._flush()
        return removed is not None

    # ── Snapshots ──────────────────────────────────────

    def save_snapshot(self, name: str, state: dict[str, Any]) -> None:
        self._data.setdefault("snapshots", {})[name] = {
            "state": state,
            "saved_at": time.time(),
        }
        self._flush()

    def load_snapshot(self, name: str) -> dict[str, Any] | None:
        snap = self._data.get("snapshots", {}).get(name)
        return snap

    def list_snapshots(self) -> dict[str, Any]:
        return {k: {"saved_at": v.get("saved_at")} for k, v in self._data.get("snapshots", {}).items()}

    def delete_snapshot(self, name: str) -> bool:
        removed = self._data.get("snapshots", {}).pop(name, None)
        if removed is not None:
            self._flush()
        return removed is not None


# Singleton store (set by server)
_store: PipelineStore | None = None


def get_store() -> PipelineStore:
    if _store is None:
        raise RuntimeError("Pipeline store not initialized")
    return _store


def create_pipeline_store_router(data_dir: str | Path) -> APIRouter:
    global _store
    _store = PipelineStore(data_dir)
    router = APIRouter(tags=["pipeline-store"])

    @router.get("/")
    def list_all():
        return {"slots": _store.list_slots(), "snapshots": _store.list_snapshots()}

    @router.get("/slot/{key}")
    def get_slot(key: str):
        slot = _store.get_slot(key)
        if slot is None:
            return {"error": f"Slot '{key}' not found", "value": None}
        return slot

    @router.put("/slot/{key}")
    def set_slot(key: str, body: dict[str, Any]):
        value = body.get("value")
        meta = body.get("meta")
        _store.set_slot(key, value, meta)
        return {"ok": True, "key": key}

    @router.delete("/slot/{key}")
    def delete_slot(key: str):
        removed = _store.delete_slot(key)
        return {"ok": removed, "key": key}

    @router.post("/snapshot")
    def save_snapshot(body: dict[str, Any]):
        name = body.get("name", f"snap_{int(time.time())}")
        state = body.get("state", {})
        _store.save_snapshot(name, state)
        return {"ok": True, "name": name}

    @router.get("/snapshot/{name}")
    def load_snapshot(name: str):
        snap = _store.load_snapshot(name)
        if snap is None:
            return {"error": f"Snapshot '{name}' not found"}
        return snap

    @router.delete("/snapshot/{name}")
    def delete_snapshot(name: str):
        removed = _store.delete_snapshot(name)
        return {"ok": removed, "name": name}

    return router
