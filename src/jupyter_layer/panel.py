"""
Panel > JupyterObject hierarchy.

Panel   = named container holding child JupyterObjects by ID.
Object  = (id, meta, lazy value-accessor).

At L0, Panel.list_ids() returns only IDs — no values pulled.
Values are accessed explicitly via panel.get(id).value or panel.scope.fetch(id).

A Panel can be:
  - standalone (in-memory, no kernel) — useful for metadata/config grouping
  - kernel-backed (scope= provided) — IDs mirror kernel globals
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Callable, Optional, TYPE_CHECKING

if TYPE_CHECKING:
    from .scope import JupyterScope


@dataclass
class JupyterObject:
    """
    One named value within a Panel.

    id      — stable identifier (str)
    meta    — arbitrary metadata dict (type hint, provenance, tags, …)
    _fetch  — callable that materialises the value on demand (or None for standalone)
    _value  — cached value once fetched
    """

    id: str
    meta: dict = field(default_factory=dict)
    _fetch: Optional[Callable[[], Any]] = field(default=None, repr=False)
    _value: Any = field(default=None, repr=False, compare=False)
    _fetched: bool = field(default=False, repr=False, compare=False)

    @property
    def value(self) -> Any:
        if self._fetch is not None and not self._fetched:
            self._value = self._fetch()
            self._fetched = True
        return self._value

    @value.setter
    def value(self, v: Any) -> None:
        self._value = v
        self._fetched = True

    def invalidate(self) -> None:
        """Clear cached value — next .value access re-fetches."""
        self._fetched = False
        self._value = None

    def __repr__(self) -> str:
        fetched = "fetched" if self._fetched else "lazy"
        return f"JupyterObject(id={self.id!r}, meta={self.meta}, [{fetched}])"


class Panel:
    """
    Named container with Panel > JupyterObject hierarchy.

    Children are stored by id. Supports:
      - standalone objects (add manually)
      - kernel-backed objects (sync_from_scope())

    L0 rule: list_ids() and children are always cheap. Values are pull-only.
    """

    def __init__(
        self,
        name: str,
        scope: Optional["JupyterScope"] = None,
        meta: Optional[dict] = None,
    ):
        self.name = name
        self.scope = scope
        self.meta = meta or {}
        self._children: dict[str, JupyterObject] = {}
        self._sub_panels: dict[str, "Panel"] = {}

    # ── L0 surface ───────────────────────────────────────────────────────────

    def list_ids(self) -> list[str]:
        """IDs of all direct children — no values materialized."""
        return list(self._children.keys())

    def list_panel_ids(self) -> list[str]:
        """IDs of sub-panels."""
        return list(self._sub_panels.keys())

    # ── child management ─────────────────────────────────────────────────────

    def add(self, obj: JupyterObject) -> "Panel":
        self._children[obj.id] = obj
        return self

    def add_value(self, id: str, value: Any, meta: Optional[dict] = None) -> JupyterObject:
        """Convenience: create a standalone Object with a known value."""
        obj = JupyterObject(id=id, meta=meta or {})
        obj.value = value
        self._children[id] = obj
        return obj

    def get(self, id: str) -> JupyterObject:
        if id not in self._children:
            raise KeyError(f"Object {id!r} not in panel {self.name!r}")
        return self._children[id]

    def remove(self, id: str) -> None:
        self._children.pop(id, None)

    def __contains__(self, id: str) -> bool:
        return id in self._children

    def __len__(self) -> int:
        return len(self._children)

    # ── sub-panel hierarchy ──────────────────────────────────────────────────

    def sub_panel(self, name: str, **kwargs) -> "Panel":
        """Get-or-create a named sub-panel."""
        if name not in self._sub_panels:
            child_scope = kwargs.get("scope", self.scope)
            self._sub_panels[name] = Panel(name=name, scope=child_scope)
        return self._sub_panels[name]

    # ── kernel-backed sync ───────────────────────────────────────────────────

    def sync_from_scope(self) -> list[str]:
        """
        Refresh children from kernel namespace (L0 sync).
        - Adds new IDs as lazy JupyterObjects.
        - Removes IDs no longer in kernel.
        - Does NOT re-fetch values for existing objects.
        Returns list of new IDs added.
        """
        if self.scope is None:
            raise RuntimeError(f"Panel {self.name!r} has no scope attached")

        kernel_ids = set(self.scope.list_ids())
        current_ids = set(self._children.keys())

        added = []
        for kid in kernel_ids - current_ids:
            obj = JupyterObject(
                id=kid,
                meta={"source": "kernel"},
                _fetch=lambda name=kid: self.scope.fetch(name),
            )
            self._children[kid] = obj
            added.append(kid)

        for removed_id in current_ids - kernel_ids:
            del self._children[removed_id]

        return added

    # ── repr ─────────────────────────────────────────────────────────────────

    def __repr__(self) -> str:
        backed = f"scope={self.scope!r}" if self.scope else "standalone"
        return (
            f"Panel(name={self.name!r}, children={self.list_ids()}, "
            f"sub_panels={self.list_panel_ids()}, {backed})"
        )
