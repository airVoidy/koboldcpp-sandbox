"""Pydantic models for the DataStore.

Design:
- StoreEntry is a single key-value record with status + provenance
- Namespace groups entries under a name, optionally with a TargetSchema
- TargetSchema defines expected structure: table, checklist, or record
- Workers create schemas; data is validated against them on write
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Literal

from pydantic import BaseModel, Field


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


# ---------------------------------------------------------------------------
# Target Schemas — templates that define expected data structure
# ---------------------------------------------------------------------------

class TableSchema(BaseModel):
    """Grid with rows x columns, each cell has a value from cell_domain."""
    type: Literal["table"] = "table"
    rows: list[str]
    columns: list[str]
    cell_type: Literal["enum", "number", "string", "bool"] = "enum"
    cell_domain: list[str] = Field(default_factory=lambda: ["yes", "no", "unknown"])
    default_value: Any = "unknown"


class ChecklistItem(BaseModel):
    """Single checklist item with optional metadata."""
    label: str
    group: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)


class ChecklistSchema(BaseModel):
    """List of items that transition through states (pending -> done)."""
    type: Literal["checklist"] = "checklist"
    items: list[str | ChecklistItem] = Field(default_factory=list)
    item_states: list[str] = Field(default_factory=lambda: ["pending", "in_progress", "done", "skipped"])
    default_state: str = "pending"
    strikethrough_states: list[str] = Field(default_factory=lambda: ["done", "skipped"])


class RecordField(BaseModel):
    """Field definition for a record schema."""
    type: Literal["string", "number", "bool", "datetime", "enum"] = "string"
    required: bool = False
    default: Any = None
    enum_values: list[str] | None = None


class RecordSchema(BaseModel):
    """Typed key-value record (like a form)."""
    type: Literal["record"] = "record"
    fields: dict[str, str | RecordField] = Field(default_factory=dict)


TargetSchema = TableSchema | ChecklistSchema | RecordSchema


# ---------------------------------------------------------------------------
# Store Entry — single piece of data
# ---------------------------------------------------------------------------

class StoreEntry(BaseModel):
    value: Any
    status: str = "active"
    source: str | None = None
    updated_at: str = Field(default_factory=utc_now)
    tags: list[str] = Field(default_factory=list)


# ---------------------------------------------------------------------------
# Namespace — a named group of entries, optionally schema-bound
# ---------------------------------------------------------------------------

class Namespace(BaseModel):
    ns: str
    schema_version: int = 1
    target_schema: TargetSchema | None = None
    entries: dict[str, StoreEntry] = Field(default_factory=dict)
    created_at: str = Field(default_factory=utc_now)
    updated_at: str = Field(default_factory=utc_now)


# ---------------------------------------------------------------------------
# Store Metadata
# ---------------------------------------------------------------------------

class StoreMeta(BaseModel):
    store_name: str
    created_at: str = Field(default_factory=utc_now)
    schema_version: int = 1
    namespaces: list[str] = Field(default_factory=list)


# ---------------------------------------------------------------------------
# Git commit info
# ---------------------------------------------------------------------------

class CommitInfo(BaseModel):
    hash: str
    short_hash: str
    message: str
    timestamp: str
    author: str = "DataStore"


# ---------------------------------------------------------------------------
# Contracts — semantic templates that can be instantiated per-node
# ---------------------------------------------------------------------------

class ContractSlot(BaseModel):
    """A single slot in a contract template."""
    bind: str                            # field name on node (e.g. 'axioms_list')
    type: str = "list"                   # slot type: list, text, tags, children, etc.
    label: str = ""
    ds: str | None = None                # DS key template (e.g. 'axioms.$id')
    accept: str = "auto"                 # 'auto' | 'manual'
    color: str | None = None


class Contract(BaseModel):
    """A contract template (Schema workscope entry).

    Semantic skeleton — defines what fields are possible and how they behave.
    No data until instantiated. Rules (accept, constraints) are declared here.
    """
    name: str                            # template name (e.g. 'root', 'entity')
    icon: str = "#"
    extends: str | None = None           # parent contract for inheritance
    slots: list[ContractSlot] = Field(default_factory=list)
    patch: list[dict[str, Any]] | None = None  # patch ops for inheritance
    created_at: str = Field(default_factory=utc_now)
    updated_at: str = Field(default_factory=utc_now)


class ContractInstance(BaseModel):
    """An instantiated contract property — someone accepted the contract."""
    contract: str                        # contract name
    node_id: str                         # owner node
    ds_key: str                          # scoped key (e.g. 'axioms.n_0')
    field: str                           # slot bind (e.g. 'axioms_list')
    status: str = "instantiated"         # instantiated | active | closed
    source: str | None = None            # who instantiated
    created_at: str = Field(default_factory=utc_now)


class PatchProposal(BaseModel):
    """A proposed data delivery to a node, evaluated against contract rules."""
    node_id: str
    data: dict[str, Any]
    meta: dict[str, Any] = Field(default_factory=dict)
    resolved: dict[str, str] = Field(default_factory=dict)  # key → accepted|pending|rejected|unknown
    created_at: str = Field(default_factory=utc_now)
