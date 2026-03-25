"""Shared macro registry for GUI / Atomic / Workflow bridges."""
from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any


@dataclass
class MacroRecord:
    name: str
    layer: str = "atomic"
    inputs: list[str] = field(default_factory=list)
    outputs: list[str] = field(default_factory=list)
    dsl: str = ""
    workflow_alias: list[dict[str, Any]] = field(default_factory=list)
    tags: list[str] = field(default_factory=list)
    description: str = ""

    @classmethod
    def from_payload(cls, name: str, payload: Any) -> "MacroRecord":
        if isinstance(payload, str):
            return cls(name=name, layer="atomic", dsl=payload)
        if not isinstance(payload, dict):
            raise ValueError(f"Unsupported macro payload for {name!r}: {type(payload).__name__}")
        return cls(
            name=str(payload.get("name") or name),
            layer=str(payload.get("layer") or "atomic"),
            inputs=[str(x) for x in (payload.get("inputs") or [])],
            outputs=[str(x) for x in (payload.get("outputs") or [])],
            dsl=str(payload.get("dsl") or ""),
            workflow_alias=list(payload.get("workflow_alias") or []),
            tags=[str(x) for x in (payload.get("tags") or [])],
            description=str(payload.get("description") or ""),
        )

    def to_payload(self) -> dict[str, Any]:
        return asdict(self)


def default_registry_path() -> Path:
    return Path(__file__).resolve().parents[2] / "docs" / "dsl_layers_v1" / "macro_registry.json"


def load_macro_registry(path: str | Path | None = None) -> dict[str, MacroRecord]:
    registry_path = Path(path) if path else default_registry_path()
    if not registry_path.exists():
        return {}
    data = json.loads(registry_path.read_text(encoding="utf-8"))
    if isinstance(data, dict) and "macros" in data:
        data = data["macros"]
    if not isinstance(data, dict):
        raise ValueError(f"Macro registry must be an object: {registry_path}")
    return {str(name): MacroRecord.from_payload(str(name), payload) for name, payload in data.items()}


def save_macro_registry(macros: dict[str, MacroRecord], path: str | Path | None = None) -> Path:
    registry_path = Path(path) if path else default_registry_path()
    registry_path.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "version": 1,
        "macros": {name: macro.to_payload() for name, macro in macros.items()},
    }
    registry_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    return registry_path


def get_macro(name: str, path: str | Path | None = None) -> MacroRecord | None:
    return load_macro_registry(path).get(name)
