"""Export DataStore state for injection into LLM context.

Renders store data as compact markdown for token efficiency.
Used by the think interceptor to build checklists and status blocks.
"""

from __future__ import annotations

from typing import Any

from .schema import ChecklistSchema, TableSchema
from .store import DataStore


def export_for_context(
    store: DataStore,
    *,
    namespaces: list[str] | None = None,
    max_chars: int = 4000,
    include_schema_info: bool = False,
) -> str:
    """Render store data as markdown context block for LLM injection.

    Args:
        store: DataStore instance
        namespaces: Which namespaces to include (None = all)
        max_chars: Truncate output to this length
        include_schema_info: Add schema type hint for each namespace

    Returns:
        Markdown-formatted string ready for prompt insertion
    """
    ns_list = namespaces or store.list_namespaces()
    if not ns_list:
        return ""

    lines = ["## Active Data Store", ""]

    for ns_name in ns_list:
        try:
            ns = store.load_namespace(ns_name)
        except Exception:
            continue

        if not ns.entries:
            continue

        # Namespace header
        schema_hint = ""
        if include_schema_info and ns.target_schema:
            schema_hint = f" ({ns.target_schema.type})"
        lines.append(f"### {ns_name}{schema_hint}")

        # Render based on schema type
        if ns.target_schema and isinstance(ns.target_schema, TableSchema):
            lines.extend(_render_table(ns))
        elif ns.target_schema and isinstance(ns.target_schema, ChecklistSchema):
            lines.extend(_render_checklist(ns))
        else:
            lines.extend(_render_flat(ns))

        lines.append("")

    result = "\n".join(lines)
    if len(result) > max_chars:
        result = result[:max_chars - 20] + "\n... (truncated)"
    return result


def export_namespace_for_context(
    store: DataStore,
    ns: str,
    *,
    max_chars: int = 2000,
) -> str:
    """Export a single namespace."""
    return export_for_context(store, namespaces=[ns], max_chars=max_chars)


def _render_flat(ns: Any) -> list[str]:
    """Default rendering: key = value [status, source]."""
    lines = []
    for key, entry in sorted(ns.entries.items()):
        meta_parts = []
        if entry.status != "active":
            meta_parts.append(entry.status)
        if entry.source:
            meta_parts.append(entry.source)
        meta = f" [{', '.join(meta_parts)}]" if meta_parts else ""
        lines.append(f"- {key} = {entry.value}{meta}")
    return lines


def _render_table(ns: Any) -> list[str]:
    """Render as markdown table."""
    schema: TableSchema = ns.target_schema
    # Build grid
    grid: dict[str, dict[str, str]] = {}
    for key, entry in ns.entries.items():
        parts = key.split(".", 1)
        if len(parts) == 2:
            row, col = parts
            grid.setdefault(row, {})[col] = str(entry.value)

    if not grid:
        return _render_flat(ns)

    # Header
    cols = schema.columns
    lines = [f"| | {' | '.join(cols)} |"]
    lines.append(f"|---|{'|'.join(['---'] * len(cols))}|")

    # Rows
    for row in schema.rows:
        cells = [grid.get(row, {}).get(col, "?") for col in cols]
        lines.append(f"| {row} | {' | '.join(cells)} |")

    return lines


def _render_checklist(ns: Any) -> list[str]:
    """Render as checklist with [x] for completed items."""
    schema: ChecklistSchema = ns.target_schema
    strike_states = set(schema.strikethrough_states)
    lines = []
    for key, entry in sorted(ns.entries.items()):
        done = entry.value in strike_states
        marker = "x" if done else " "
        label = key.replace("_", " ")
        status_note = f" ({entry.value})" if entry.value != "done" and done else ""
        lines.append(f"- [{marker}] {label}{status_note}")
    return lines
