"""
JupyterScope — L0 view of a kernel's global namespace.

L0 contract: only IDs (variable names) and type hints are materialized eagerly.
Actual values are fetched explicitly via .fetch() — never pulled automatically.
"""

from __future__ import annotations

from typing import Any, TYPE_CHECKING

if TYPE_CHECKING:
    from .kernel import KernelSession


# Variables injected by IPython/kernel internals — skip them in listings
_SKIP_PREFIXES = ("_", "In", "Out", "get_ipython", "exit", "quit", "open")


class JupyterScope:
    """
    Read-only L0 view of one kernel's globals namespace.

    list_ids()        → List[str]          — names only, no values
    list_typed()      → List[(name, type)] — names + type strings, still no values
    fetch(name)       → Any                — materialise one variable via JSON
    fetch_repr(name)  → str                — safe repr() of any variable
    run(code)         → dict               — pass-through to KernelSession.run()
    """

    def __init__(self, kernel: "KernelSession", skip_internals: bool = True):
        self._kernel = kernel
        self._skip_internals = skip_internals

    # ── L0: IDs + type hints ─────────────────────────────────────────────────

    def list_ids(self) -> list[str]:
        """Return variable names in kernel globals — no values."""
        raw: list[str] = self._kernel.eval_json(
            "[k for k in globals().keys()]"
        )
        if self._skip_internals:
            raw = [n for n in raw if not any(n.startswith(p) for p in _SKIP_PREFIXES)]
        return raw

    def list_typed(self) -> list[tuple[str, str]]:
        """Return (name, type_name) pairs — still L0, no value serialization."""
        raw: list[list[str]] = self._kernel.eval_json(
            "[[k, type(v).__name__] for k, v in globals().items()]"
        )
        pairs = [(k, t) for k, t in raw]
        if self._skip_internals:
            pairs = [(k, t) for k, t in pairs
                     if not any(k.startswith(p) for p in _SKIP_PREFIXES)]
        return pairs

    # ── materialization ──────────────────────────────────────────────────────

    def fetch(self, name: str) -> Any:
        """
        Materialise a variable via JSON round-trip.
        Works for: int, float, str, list, dict, bool, None.
        Raises ValueError for non-serializable types — use fetch_repr() instead.
        """
        self._validate_name(name)
        try:
            return self._kernel.eval_json(name)
        except Exception as exc:
            raise ValueError(
                f"Cannot JSON-serialize '{name}'. Try fetch_repr() instead."
            ) from exc

    def fetch_repr(self, name: str) -> str:
        """Return repr() string — works for any picklable/printable object."""
        self._validate_name(name)
        result = self._kernel.run(f"print(repr({name}))")
        if result["status"] != "ok":
            raise RuntimeError(f"Kernel error fetching repr({name}): {result['error']}")
        return result["output"].strip()

    # ── execution pass-through ───────────────────────────────────────────────

    def run(self, code: str) -> dict:
        """Execute arbitrary code in kernel scope."""
        return self._kernel.run(code)

    # ── helpers ──────────────────────────────────────────────────────────────

    @staticmethod
    def _validate_name(name: str) -> None:
        if not name.isidentifier():
            raise ValueError(f"Invalid Python identifier: {name!r}")
