"""DSL Builtins — Python utility functions for Assembly DSL.

Registered via @asm_function decorator from assembly_dsl.
These are low-level helpers that can't be expressed as DSL fn definitions:
string ops, parsing, annotation construction.

DSL-level functions (prompt templates, compositions) should live as
Assembly fn definitions in wiki function_page entries instead.
"""
from __future__ import annotations

import re
from typing import Any


# ---------------------------------------------------------------------------
# Pure utility functions (no assembly dependency)
# ---------------------------------------------------------------------------

def slice_lines(text: Any, start: Any, end: Any) -> str:
    """Extract lines from start (1-based) to end (1-based, inclusive)."""
    lines = str(text).split("\n")
    try:
        s = max(0, int(start) - 1)
    except (ValueError, TypeError):
        s = 0
    try:
        e = min(len(lines), int(end))
    except (ValueError, TypeError):
        e = len(lines)
    if e < s + 1:
        e = s + 1
    return "\n".join(lines[s:e]).strip()


def numbered(text: Any) -> str:
    """Add line numbers to text (1-based)."""
    return "\n".join(f"{i+1}. {l}" for i, l in enumerate(str(text).split("\n")))


def char_indexed(text: Any) -> str:
    """Add character position indices to text for probe annotation.

    Example: "Anime" -> "«0:A»«1:n»«2:i»«3:m»«4:e»"
    For probes that need to find char_start/char_end positions.
    """
    s = str(text)
    parts: list[str] = []
    for i, ch in enumerate(s):
        if ch == "\n":
            parts.append(f"[{i}:\\n]\n")
        elif ch == " ":
            parts.append(f"[{i}: ]")
        else:
            parts.append(f"[{i}:{ch}]")
    return "".join(parts)


def check_status(text: Any) -> str:
    """Extract PASS/FAIL status from text."""
    value = str(text or "").strip()
    if re.search(r"\bPASS\b", value, re.IGNORECASE):
        return "pass"
    if re.search(r"\bFAIL\b", value, re.IGNORECASE):
        return "fail"
    return "pending"


def concat_lists(*args: Any) -> list:
    """Flatten args into a single list."""
    result: list = []
    for a in args:
        if isinstance(a, list):
            result.extend(a)
        else:
            result.append(a)
    return result


def wrap_list(items: list, key: str = "name") -> list[dict]:
    """Wrap a list of values into dicts with auto-increment local_id.

    ["a","b"] → [{local_id:1, key:"a"}, {local_id:2, key:"b"}]
    """
    return [{"local_id": i + 1, key: item} for i, item in enumerate(items)]


def split_blocks(text: str, pattern: str = "") -> list[dict]:
    """Split text into blocks by a regex pattern (default: markdown headers like **N. Title**).

    Returns [{local_id:1, header:"...", start_line:N, text:"..."}, ...]
    Each block runs from its header to the next header (or end).
    """
    lines = str(text).split("\n")
    if not pattern:
        pattern = r"^\*{0,2}\d+[\.\)]\s"  # matches "1. " or "**1. " etc.

    blocks: list[dict] = []
    current_start: int | None = None
    current_header = ""

    for i, line in enumerate(lines):
        if re.match(pattern, line.strip()):
            # Close previous block
            if current_start is not None:
                block_text = "\n".join(lines[current_start:i]).strip()
                blocks.append({
                    "local_id": len(blocks) + 1,
                    "header": current_header,
                    "_startNum": current_start + 1,
                    "text": block_text,
                })
            current_start = i
            current_header = line.strip()

    # Close last block
    if current_start is not None:
        block_text = "\n".join(lines[current_start:]).strip()
        blocks.append({
            "local_id": len(blocks) + 1,
            "header": current_header,
            "_startNum": current_start + 1,
            "text": block_text,
        })

    return blocks


def enrich_entities(entities: list[dict], answer: str, key: str = "") -> list[dict]:
    """Add _startNum and _firstLine to each entity by matching title in answer.

    key: field name to use as title (default: tries _title, title, local_id, name).
    """
    lines = str(answer).split("\n")

    for idx, entity in enumerate(entities):
        # Set local_id if not present (1-based stable ID)
        if "local_id" not in entity:
            entity["local_id"] = idx + 1

        if key:
            title = str(entity.get(key, ""))
        else:
            title = str(entity.get("_title", entity.get("title", entity.get("name", ""))))
        # Normalize: strip markdown bold, numbering prefixes, quotes
        norm = re.sub(r"\*\*", "", title)
        norm = re.sub(r"^\d+[\.\)]\s*", "", norm)
        norm = re.sub(r'^["\']|["\']$', "", norm).strip()

        found = False
        for idx, line in enumerate(lines):
            if norm and norm.lower() in line.lower():
                entity["_startNum"] = idx + 1
                entity["_firstLine"] = line
                found = True
                break
        if not found:
            entity["_startNum"] = 1
            entity["_firstLine"] = lines[0] if lines else ""

    return entities


def parse_sections(text: str) -> dict[str, Any]:
    """Parse ENTITIES/AXIOMS/HYPOTHESES sections from claims output."""
    result: dict[str, Any] = {"entities": [], "axioms": [], "hypotheses": []}
    current_section: str | None = None

    for line in str(text).split("\n"):
        stripped = line.strip()
        upper = stripped.upper()

        if upper.startswith("ENTITIES"):
            current_section = "entities"
            # Try to extract inline list: ENTITIES: [a, b, c]
            after = stripped.split(":", 1)[1].strip() if ":" in stripped else ""
            if after.startswith("[") and after.endswith("]"):
                items = [x.strip().strip("'\"") for x in after[1:-1].split(",") if x.strip()]
                result["entities"] = items
            continue
        elif upper.startswith("AXIOMS"):
            current_section = "axioms"
            continue
        elif upper.startswith("HYPOTHESES"):
            current_section = "hypotheses"
            continue

        if current_section and stripped.startswith("- "):
            item = stripped[2:].strip()
            if item:
                result[current_section].append(item)

    return result


def fmt(template: str, *args: Any) -> str:
    """Positional string formatting: fmt("hello {0}, you are {1}", name, adj).

    Supports {0}, {1}, ... placeholders. Also supports {name} if args
    are dicts (uses first dict for named lookup).
    """
    result = str(template)
    for i, arg in enumerate(args):
        result = result.replace(f"{{{i}}}", str(arg))
    # Named placeholders from dict args
    for arg in args:
        if isinstance(arg, dict):
            for k, v in arg.items():
                result = result.replace(f"{{{k}}}", str(v))
    return result


def create_span_annotation(
    entity: dict,
    constraint: dict,
    char_start: int,
    char_end: int,
) -> dict[str, Any]:
    """Build an annotation dict for a span in entity text."""
    message_ref = entity.get("_message_ref", entity.get("message_id", ""))
    container_ref = entity.get("_container_ref", "main_text")
    text = str(entity.get("answer", ""))
    char_start = max(0, int(char_start))
    char_end = min(len(text), int(char_end))
    span_text = text[char_start:char_end]

    return {
        "kind": "annotation",
        "source": {
            "message_ref": message_ref,
            "container_ref": container_ref,
            "char_start": char_start,
            "char_end": char_end,
            "char_len": char_end - char_start,
        },
        "tags": list(constraint.get("tags", [])),
        "meta": {
            "label": constraint.get("name", ""),
            "normalized_value": span_text.strip().lower() if span_text else None,
            "probe_prompt": constraint.get("probe_prompt", ""),
        },
    }


# ---------------------------------------------------------------------------
# Registration: call register_dsl_builtins() to hook into assembly_dsl
# ---------------------------------------------------------------------------

def register_dsl_builtins() -> None:
    """Register all Python utility builtins with the Assembly DSL engine."""
    from .assembly_dsl import asm_function

    @asm_function("slice_lines", params=["text", "start", "end"], outputs=["result"])
    def _slice_lines(ctx, args, flags):
        return slice_lines(*args[:3])

    @asm_function("numbered", params=["text"], outputs=["result"])
    def _numbered(ctx, args, flags):
        return numbered(args[0] if args else "")

    @asm_function("char_indexed", params=["text"], outputs=["result"])
    def _char_indexed(ctx, args, flags):
        return char_indexed(args[0] if args else "")

    @asm_function("check_status", params=["text"], outputs=["result"])
    def _check_status(ctx, args, flags):
        return check_status(args[0] if args else "")

    @asm_function("concat", params=["*args"], outputs=["result"])
    def _concat(ctx, args, flags):
        return concat_lists(*args)

    @asm_function("split_blocks", params=["text", "pattern"], outputs=["result"])
    def _split_blocks(ctx, args, flags):
        text = args[0] if args else ""
        pattern = str(args[1]) if len(args) > 1 else ""
        return split_blocks(str(text), pattern)

    @asm_function("wrap_list", params=["items", "key"], outputs=["result"])
    def _wrap_list(ctx, args, flags):
        items = args[0] if args else []
        key = str(args[1]) if len(args) > 1 else "local_id"
        if not isinstance(items, list):
            items = [items] if items else []
        return wrap_list(items, key)

    @asm_function("enrich_entities", params=["entities", "answer", "key"], outputs=["result"])
    def _enrich_entities(ctx, args, flags):
        entities = args[0] if args else []
        answer = args[1] if len(args) > 1 else ""
        key = str(args[2]) if len(args) > 2 else ""
        if not isinstance(entities, list):
            entities = []
        return enrich_entities(entities, answer, key)

    @asm_function("parse_sections", params=["text"], outputs=["result"])
    def _parse_sections(ctx, args, flags):
        return parse_sections(args[0] if args else "")

    @asm_function("fmt", params=["template", "*args"], outputs=["result"])
    def _fmt(ctx, args, flags):
        template = args[0] if args else ""
        return fmt(str(template), *args[1:])

    @asm_function("store_get", params=["key"], outputs=["result"])
    def _store_get(ctx, args, flags):
        try:
            from .pipeline_store import get_store
            slot = get_store().get_slot(str(args[0]) if args else "")
            return slot.get("value") if isinstance(slot, dict) else None
        except Exception:
            return None

    @asm_function("store_set", params=["key", "value"], outputs=["result"])
    def _store_set(ctx, args, flags):
        try:
            from .pipeline_store import get_store
            key = str(args[0]) if args else ""
            value = args[1] if len(args) > 1 else None
            get_store().set_slot(key, value)
            return True
        except Exception:
            return False

    @asm_function("store_snapshot", params=["name"], outputs=["result"])
    def _store_snapshot(ctx, args, flags):
        try:
            from .pipeline_store import get_store
            name = str(args[0]) if args else "auto"
            state = dict(ctx.vars)
            get_store().save_snapshot(name, state)
            return True
        except Exception:
            return False

    @asm_function("create_span_annotation", params=["entity", "constraint", "start", "end"], outputs=["result"])
    def _create_span_annotation(ctx, args, flags):
        entity = args[0] if args else {}
        constraint = args[1] if len(args) > 1 else {}
        start = args[2] if len(args) > 2 else 0
        end = args[3] if len(args) > 3 else 0
        return create_span_annotation(entity, constraint, int(start), int(end))
