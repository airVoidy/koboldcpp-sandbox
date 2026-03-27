from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass
class EmitStatement:
    name: str
    spec: dict[str, Any]


@dataclass
class OnStatement:
    source: str
    event: str
    spec: dict[str, Any]


EventStatement = EmitStatement | OnStatement


class EventDslSyntaxError(ValueError):
    pass


_NATIVE_DEFAULTS: dict[str, dict[str, Any]] = {
    "native_generate_defaults": {
        "prompt": "",
        "temperature": 0.2,
        "max_length": None,
        "model": None,
    }
}


class _Parser:
    def __init__(self, text: str) -> None:
        self.text = text
        self.i = 0

    def parse_program(self) -> list[EventStatement]:
        statements: list[EventStatement] = []
        while True:
            self._skip_ws()
            if self._eof():
                return statements
            ident = self._parse_ident()
            self._skip_ws()
            self._expect("(")
            if ident == "emit":
                statements.append(self._parse_emit())
            elif ident == "on":
                statements.append(self._parse_on())
            else:
                raise EventDslSyntaxError(f"Unknown top-level form: {ident}")
            self._skip_ws()

    def _parse_emit(self) -> EmitStatement:
        name = self._parse_string()
        self._skip_ws()
        self._expect(",")
        spec = self._parse_value()
        self._skip_ws()
        self._expect(")")
        return EmitStatement(name=name, spec=self._ensure_object(spec, "emit"))

    def _parse_on(self) -> OnStatement:
        source = self._parse_string()
        self._skip_ws()
        self._expect(",")
        event = self._parse_string()
        self._skip_ws()
        self._expect(",")
        spec = self._parse_value()
        self._skip_ws()
        self._expect(")")
        return OnStatement(source=source, event=event, spec=self._ensure_object(spec, "on"))

    def _parse_value(self) -> Any:
        self._skip_ws()
        if self._eof():
            raise EventDslSyntaxError("Unexpected end of input while parsing value")
        ch = self.text[self.i]
        if ch == "{":
            return self._parse_object()
        if ch == "[":
            return self._parse_array()
        if ch == '"':
            return self._parse_string()
        if ch == "@":
            return self._parse_ref()
        if ch in "-0123456789":
            return self._parse_number()
        ident = self._parse_ident()
        if ident == "true":
            return True
        if ident == "false":
            return False
        if ident == "null":
            return None
        return ident

    def _parse_object(self) -> dict[str, Any]:
        obj: dict[str, Any] = {}
        self._expect("{")
        while True:
            self._skip_ws()
            if self._peek("}"):
                self.i += 1
                return obj
            key = self._parse_string() if self._peek('"') else self._parse_ident()
            self._skip_ws()
            self._expect(":")
            value = self._parse_value()
            obj[key] = value
            self._skip_ws()
            if self._peek(","):
                self.i += 1
                continue
            if self._peek("}"):
                self.i += 1
                return obj
            raise EventDslSyntaxError(f"Expected ',' or '}}' at position {self.i}")

    def _parse_array(self) -> list[Any]:
        items: list[Any] = []
        self._expect("[")
        while True:
            self._skip_ws()
            if self._peek("]"):
                self.i += 1
                return items
            items.append(self._parse_value())
            self._skip_ws()
            if self._peek(","):
                self.i += 1
                continue
            if self._peek("]"):
                self.i += 1
                return items
            raise EventDslSyntaxError(f"Expected ',' or ']' at position {self.i}")

    def _parse_string(self) -> str:
        self._expect('"')
        chars: list[str] = []
        while not self._eof():
            ch = self.text[self.i]
            self.i += 1
            if ch == '"':
                return "".join(chars)
            if ch == "\\":
                if self._eof():
                    break
                nxt = self.text[self.i]
                self.i += 1
                escapes = {"n": "\n", "t": "\t", '"': '"', "\\": "\\"}
                chars.append(escapes.get(nxt, nxt))
                continue
            chars.append(ch)
        raise EventDslSyntaxError("Unterminated string literal")

    def _parse_ref(self) -> str:
        start = self.i
        self.i += 1
        while not self._eof() and self.text[self.i] not in ",:]})( \t\r\n":
            self.i += 1
        return self.text[start:self.i]

    def _parse_number(self) -> int | float:
        start = self.i
        if self.text[self.i] == "-":
            self.i += 1
        while not self._eof() and self.text[self.i].isdigit():
            self.i += 1
        if not self._eof() and self.text[self.i] == ".":
            self.i += 1
            while not self._eof() and self.text[self.i].isdigit():
                self.i += 1
            return float(self.text[start:self.i])
        return int(self.text[start:self.i])

    def _parse_ident(self) -> str:
        self._skip_ws()
        start = self.i
        while not self._eof() and (self.text[self.i].isalnum() or self.text[self.i] in "._-"):
            self.i += 1
        if start == self.i:
            raise EventDslSyntaxError(f"Expected identifier at position {self.i}")
        return self.text[start:self.i]

    def _expect(self, token: str) -> None:
        self._skip_ws()
        if not self.text.startswith(token, self.i):
            raise EventDslSyntaxError(f"Expected '{token}' at position {self.i}")
        self.i += len(token)

    def _peek(self, token: str) -> bool:
        return self.text.startswith(token, self.i)

    def _skip_ws(self) -> None:
        while not self._eof() and self.text[self.i].isspace():
            self.i += 1

    def _eof(self) -> bool:
        return self.i >= len(self.text)

    @staticmethod
    def _ensure_object(value: Any, name: str) -> dict[str, Any]:
        if not isinstance(value, dict):
            raise EventDslSyntaxError(f"{name} body must be an object")
        return value


def parse_event_dsl(text: str) -> list[EventStatement]:
    return _Parser(text).parse_program()


def compile_event_dsl(text: str) -> str:
    statements = parse_event_dsl(text)
    emits = [stmt for stmt in statements if isinstance(stmt, EmitStatement)]
    listeners = [stmt for stmt in statements if isinstance(stmt, OnStatement)]
    listener_map: dict[tuple[str, str], list[OnStatement]] = {}
    for listener in listeners:
        listener_map.setdefault((listener.source, listener.event), []).append(listener)

    lines: list[str] = []
    for emit in emits:
        lines.extend(_compile_emit(emit))
        if emit.name == "generate.request":
            lines.extend(_compile_generate_call(emit))
            for listener in listener_map.get((emit.name, "response"), []):
                lines.extend(_compile_on_response(listener))
    return "\n".join(line for line in lines if line.strip())


def _compile_emit(stmt: EmitStatement) -> list[str]:
    data = stmt.spec.get("data") or {}
    if not isinstance(data, dict):
        raise EventDslSyntaxError(f"emit({stmt.name}) data must be an object")
    lines: list[str] = []
    schema = str(stmt.spec.get("schema") or "").strip()
    defaults = str(stmt.spec.get("defaults") or "").strip()
    if defaults:
        default_map = _NATIVE_DEFAULTS.get(defaults)
        if default_map is None:
            raise EventDslSyntaxError(f"Unknown defaults object: {defaults}")
        for field_name, value in default_map.items():
            lines.append(f"MOV  @{stmt.name}.{field_name}, {_asm_value(value)}")
    for field_name, value in data.items():
        lines.append(f"MOV  @{stmt.name}.{field_name}, {_asm_value(value)}")
    if "complete" in _as_str_list(stmt.spec.get("checks")):
        target = f"@{stmt.name}.check"
        if schema:
            lines.append(f'CALL {target}, check_complete, @{stmt.name}, schema:{_asm_value(schema)}')
        else:
            lines.append(f"CALL {target}, check_complete, @{stmt.name}")
    return lines


def _compile_generate_call(stmt: EmitStatement) -> list[str]:
    data = stmt.spec.get("data") or {}
    if not isinstance(data, dict):
        return []
    defaults_name = str(stmt.spec.get("defaults") or "").strip()
    defaults = _NATIVE_DEFAULTS.get(defaults_name, {})
    prompt_value = data.get("prompt", "@generate.request.prompt")
    temperature = data.get("temperature", defaults.get("temperature", 0.2))
    max_length = data.get("max_length", defaults.get("max_length", 2048))
    worker = str(stmt.spec.get("worker") or "generator")
    flags = [f"worker:{worker}", f"temp:{_asm_value(temperature)}"]
    if max_length is not None:
        flags.append(f"max:{_asm_value(max_length)}")
    return [f"GEN  @generate.call.raw, {_asm_value(prompt_value)}, {', '.join(flags)}"]


def _compile_on_response(stmt: OnStatement) -> list[str]:
    lines: list[str] = []
    bind_name = str(stmt.spec.get("bind") or "").strip()
    if bind_name:
        lines.append(f"CALL @{{bind}}, bind_native_generate_response, @generate.call.raw".replace("{bind}", bind_name))
    checks = _as_str_list(stmt.spec.get("checks"))
    schema = str(stmt.spec.get("schema") or "").strip()
    if bind_name and "complete" in checks:
        target = f"@{bind_name}.check"
        if schema:
            lines.append(f'CALL {target}, check_complete, @{bind_name}, schema:{_asm_value(schema)}')
        else:
            lines.append(f"CALL {target}, check_complete, @{bind_name}")
    for emit_name in _as_str_list(stmt.spec.get("emit")):
        if emit_name == "response.output_message":
            lines.append("CALL @response.output_message, emit_output_message, @generate.response")
        else:
            safe_name = emit_name.replace('"', "")
            lines.append(f"CALL @{safe_name}, emit_object, @{safe_name}")
    for project_name in _as_str_list(stmt.spec.get("project")):
        if project_name == "response.table":
            lines.append("CALL @response.table, build_table_from_text, @generate.response.raw_text")
        else:
            safe_name = project_name.replace('"', "")
            lines.append(f"CALL @{safe_name}, build_projection, @{safe_name}")
    return lines


def _as_str_list(value: Any) -> list[str]:
    if isinstance(value, list):
        return [str(item) for item in value]
    if value is None:
        return []
    return [str(value)]


def _asm_value(value: Any) -> str:
    if isinstance(value, str):
        if value.startswith("@") or value.startswith("$"):
            return value
        escaped = value.replace("\\", "\\\\").replace('"', '\\"').replace("\n", "\\n")
        return f'"{escaped}"'
    if value is None:
        return "null"
    if isinstance(value, bool):
        return "true" if value else "false"
    return str(value)
