"""
LocalStore — JSON-backed persistence for Panel metadata and object catalogs.

Scope: one store per Panel (keyed by panel name).
Stores only metadata + IDs — never raw Python object values (those live in kernel).

Layout on disk:
  <base_dir>/
    <panel_name>/
      panel.json       — Panel meta + child ID list
      objects/
        <id>.json      — per-object metadata
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Optional, TYPE_CHECKING

if TYPE_CHECKING:
    from .panel import Panel, JupyterObject


class LocalStore:
    """File-backed store scoped to one panel name."""

    def __init__(self, base_dir: str | Path, panel_name: str):
        self.base_dir = Path(base_dir)
        self.panel_name = panel_name
        self._root = self.base_dir / panel_name
        self._obj_dir = self._root / "objects"

    def _ensure_dirs(self) -> None:
        self._root.mkdir(parents=True, exist_ok=True)
        self._obj_dir.mkdir(parents=True, exist_ok=True)

    # ── panel-level ──────────────────────────────────────────────────────────

    def save_panel_meta(self, panel: "Panel") -> None:
        self._ensure_dirs()
        data = {
            "name": panel.name,
            "meta": panel.meta,
            "child_ids": panel.list_ids(),
            "sub_panel_ids": panel.list_panel_ids(),
        }
        (self._root / "panel.json").write_text(json.dumps(data, indent=2), encoding="utf-8")

    def load_panel_meta(self) -> Optional[dict]:
        p = self._root / "panel.json"
        if not p.exists():
            return None
        return json.loads(p.read_text(encoding="utf-8"))

    # ── per-object ───────────────────────────────────────────────────────────

    def save_object_meta(self, obj: "JupyterObject") -> None:
        self._ensure_dirs()
        data = {"id": obj.id, "meta": obj.meta}
        (self._obj_dir / f"{obj.id}.json").write_text(
            json.dumps(data, indent=2), encoding="utf-8"
        )

    def load_object_meta(self, object_id: str) -> Optional[dict]:
        p = self._obj_dir / f"{object_id}.json"
        if not p.exists():
            return None
        return json.loads(p.read_text(encoding="utf-8"))

    def list_stored_ids(self) -> list[str]:
        if not self._obj_dir.exists():
            return []
        return [f.stem for f in self._obj_dir.glob("*.json")]

    # ── arbitrary JSON blobs (for preprocessing outputs, etc.) ───────────────

    def save_blob(self, key: str, data: Any) -> None:
        """Store any JSON-serializable blob under panel/<key>.json."""
        self._ensure_dirs()
        (self._root / f"{key}.json").write_text(
            json.dumps(data, indent=2), encoding="utf-8"
        )

    def load_blob(self, key: str) -> Optional[Any]:
        p = self._root / f"{key}.json"
        if not p.exists():
            return None
        return json.loads(p.read_text(encoding="utf-8"))

    def list_blobs(self) -> list[str]:
        if not self._root.exists():
            return []
        return [
            f.stem for f in self._root.glob("*.json")
            if f.name != "panel.json"
        ]
