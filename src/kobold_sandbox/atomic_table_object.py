from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Any


@dataclass
class ObjectField:
    name: str
    type: type
    default: Any = None
    aliases: list[str] = field(default_factory=list)
    description: str = ""
    group: str = ""
    required: bool = False

    @property
    def type_name(self) -> str:
        return getattr(self.type, "__name__", str(self.type))


class TableObjectSchema:
    """Universal schema -> object -> table helper for Atomic mid-layer data."""

    _fields: list[ObjectField] = []
    schema_name: str = "table_object"
    object_path: str = ""

    def __init__(self) -> None:
        self._values: dict[str, Any] = {}
        self._alias_map: dict[str, str] = {}
        for field_def in self._fields:
            self._alias_map[field_def.name] = field_def.name
            for alias in field_def.aliases:
                self._alias_map[alias] = field_def.name

    def _resolve(self, key: str) -> str:
        if key in self._alias_map:
            return self._alias_map[key]
        raise KeyError(f"Unknown field or alias: {key!r}")

    def _field_by_name(self, name: str) -> ObjectField:
        for field_def in self._fields:
            if field_def.name == name:
                return field_def
        raise KeyError(name)

    def get(self, key: str) -> Any:
        canonical = self._resolve(key)
        field_def = self._field_by_name(canonical)
        return self._values.get(canonical, field_def.default)

    def set(self, key: str, value: Any) -> None:
        canonical = self._resolve(key)
        field_def = self._field_by_name(canonical)
        self._values[canonical] = self._coerce_value(field_def, value)

    def _coerce_value(self, field_def: ObjectField, value: Any) -> Any:
        if value is None:
            return None
        target_type = field_def.type
        if target_type is bool:
            if isinstance(value, str):
                lowered = value.strip().lower()
                if lowered in {"true", "1", "yes", "on"}:
                    return True
                if lowered in {"false", "0", "no", "off"}:
                    return False
            return bool(value)
        return target_type(value)

    @classmethod
    def from_json(cls, raw: str | dict[str, Any]) -> TableObjectSchema:
        data = json.loads(raw) if isinstance(raw, str) else raw
        obj = cls()
        for key, value in data.items():
            try:
                obj.set(key, value)
            except KeyError:
                continue
        return obj

    def to_json(self, *, by_alias: bool = False, include_unknown_defaults: bool = True) -> dict[str, Any]:
        output: dict[str, Any] = {}
        for field_def in self._fields:
            key = field_def.aliases[0] if (by_alias and field_def.aliases) else field_def.name
            if field_def.name in self._values:
                output[key] = self._values[field_def.name]
            elif include_unknown_defaults:
                output[key] = field_def.default
        return output

    def to_table_rows(self) -> list[dict[str, Any]]:
        rows: list[dict[str, Any]] = []
        for field_def in self._fields:
            rows.append(
                {
                    "field": field_def.name,
                    "group": field_def.group,
                    "type": field_def.type_name,
                    "value": self._values.get(field_def.name, field_def.default),
                    "default": field_def.default,
                    "aliases": list(field_def.aliases),
                    "path": self._build_path(field_def.name),
                    "required": field_def.required,
                    "description": field_def.description,
                }
            )
        return rows

    def to_envelope(self, *, meta_data: dict[str, Any] | None = None) -> dict[str, Any]:
        return {
            "table_data": {
                "schema_name": self.schema_name,
                "object_path": self.object_path,
                "rows": self.to_table_rows(),
            },
            "meta_data": meta_data or {},
        }

    def _build_path(self, field_name: str) -> str:
        if self.object_path:
            return f"{self.object_path}.{field_name}"
        return field_name


class KoboldGenerateSchema(TableObjectSchema):
    schema_name = "kobold_generate"
    object_path = "generate.params"
    _fields = [
        ObjectField("max_context_length", int, 2048, ["generate.max_context_length", "ctx_len"], group="limits"),
        ObjectField("max_length", int, 100, ["generate.max_length"], group="limits"),
        ObjectField("prompt", str, "", ["generate.prompt"], group="content"),
        ObjectField("quiet", bool, False, ["generate.quiet"], group="controls"),
        ObjectField("rep_pen", float, 1.1, ["generate.rep_pen", "repetition_penalty"], group="sampler"),
        ObjectField("rep_pen_range", int, 256, ["generate.rep_pen_range"], group="sampler"),
        ObjectField("rep_pen_slope", float, 1.0, ["generate.rep_pen_slope"], group="sampler"),
        ObjectField("temperature", float, 0.5, ["gen.temp", "sampler.temperature"], group="sampler"),
        ObjectField("tfs", float, 1.0, ["sampler.tfs", "tail_free_sampling"], group="sampler"),
        ObjectField("top_a", float, 0.0, ["sampler.top_a"], group="sampler"),
        ObjectField("top_k", int, 100, ["sampler.top_k"], group="sampler"),
        ObjectField("top_p", float, 0.9, ["sampler.top_p", "nucleus"], group="sampler"),
        ObjectField("typical", float, 1.0, ["sampler.typical", "typical_p"], group="sampler"),
    ]


class NativeGenerateRequestSchema(TableObjectSchema):
    """Table projection for the actual native generate request used by this repo."""

    schema_name = "native_generate_request"
    object_path = "generate.request"
    _fields = [
        ObjectField("prompt", str, "", ["generate.prompt", "request.prompt"], group="content", required=True),
        ObjectField(
            "temperature",
            float,
            0.2,
            ["generate.temperature", "request.temperature", "gen.temp"],
            group="sampling",
        ),
        ObjectField(
            "max_length",
            int,
            None,
            ["generate.max_length", "request.max_length"],
            group="limits",
        ),
        ObjectField("model", str, None, ["generate.model", "request.model"], group="routing"),
    ]
