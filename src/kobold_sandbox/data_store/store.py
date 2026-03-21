"""DataStore — hierarchical JSON key-value store with git versioning.

Keys use dotted notation (e.g. "diana.position") stored flat in JSON.
get_tree() reconstructs the hierarchy for the tree viewer.
Every set/delete flushes to disk immediately; commits are explicit.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from .schema import (
    ChecklistSchema,
    CommitInfo,
    Namespace,
    RecordSchema,
    StoreEntry,
    StoreMeta,
    TableSchema,
    TargetSchema,
    utc_now,
)
from .git_history import DataStoreGit


class DataStoreError(Exception):
    pass


class DataStore:
    def __init__(self, root: Path):
        self.root = root.resolve()
        self.workspace = self.root / "workspace"
        self.meta_path = self.workspace / "_meta.json"
        self.ns_dir = self.workspace / "namespaces"
        self._git = DataStoreGit(self.root / "repo", self.workspace)

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    def init(self, store_name: str = "default") -> StoreMeta:
        """Initialize the datastore: create dirs, git repo, metadata."""
        self.workspace.mkdir(parents=True, exist_ok=True)
        self.ns_dir.mkdir(parents=True, exist_ok=True)
        self._git.init()

        meta = StoreMeta(store_name=store_name)
        self._save_meta(meta)
        self._git.commit_all(f"Init datastore: {store_name}")
        return meta

    def exists(self) -> bool:
        return self.meta_path.exists()

    def load_meta(self) -> StoreMeta:
        return StoreMeta.model_validate_json(self.meta_path.read_text(encoding="utf-8"))

    def _save_meta(self, meta: StoreMeta) -> None:
        self.meta_path.write_text(
            json.dumps(meta.model_dump(), ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

    # ------------------------------------------------------------------
    # Namespace CRUD
    # ------------------------------------------------------------------

    def create_namespace(
        self,
        ns: str,
        *,
        target_schema: TargetSchema | None = None,
    ) -> Namespace:
        """Create a new namespace, optionally with a target schema."""
        path = self._ns_path(ns)
        if path.exists():
            raise DataStoreError(f"Namespace '{ns}' already exists")

        namespace = Namespace(ns=ns, target_schema=target_schema)

        # Pre-populate entries from schema
        if target_schema:
            namespace = self._seed_from_schema(namespace, target_schema)

        self._save_namespace(namespace)

        meta = self.load_meta()
        if ns not in meta.namespaces:
            meta.namespaces.append(ns)
            self._save_meta(meta)

        return namespace

    def list_namespaces(self) -> list[str]:
        if not self.ns_dir.exists():
            return []
        return sorted(
            p.stem for p in self.ns_dir.glob("*.json")
        )

    def load_namespace(self, ns: str) -> Namespace:
        path = self._ns_path(ns)
        if not path.exists():
            raise DataStoreError(f"Namespace '{ns}' not found")
        return Namespace.model_validate_json(path.read_text(encoding="utf-8"))

    def delete_namespace(self, ns: str) -> None:
        path = self._ns_path(ns)
        if path.exists():
            path.unlink()
        meta = self.load_meta()
        if ns in meta.namespaces:
            meta.namespaces.remove(ns)
            self._save_meta(meta)

    # ------------------------------------------------------------------
    # Entry CRUD
    # ------------------------------------------------------------------

    def get(self, ns: str, key: str) -> StoreEntry | None:
        namespace = self.load_namespace(ns)
        return namespace.entries.get(key)

    def set(
        self,
        ns: str,
        key: str,
        value: Any,
        *,
        status: str = "active",
        source: str | None = None,
        tags: list[str] | None = None,
    ) -> StoreEntry:
        """Set a single entry. Validates against target_schema if present."""
        namespace = self.load_namespace(ns)

        # Validate against schema
        if namespace.target_schema:
            self._validate_entry(namespace.target_schema, key, value, status)

        entry = StoreEntry(
            value=value,
            status=status,
            source=source,
            tags=tags or [],
        )
        namespace.entries[key] = entry
        namespace.updated_at = utc_now()
        self._save_namespace(namespace)
        return entry

    def delete(self, ns: str, key: str) -> bool:
        namespace = self.load_namespace(ns)
        if key in namespace.entries:
            del namespace.entries[key]
            namespace.updated_at = utc_now()
            self._save_namespace(namespace)
            return True
        return False

    def list_keys(self, ns: str, *, prefix: str | None = None) -> list[str]:
        namespace = self.load_namespace(ns)
        keys = list(namespace.entries.keys())
        if prefix:
            keys = [k for k in keys if k.startswith(prefix)]
        return sorted(keys)

    def query(
        self,
        ns: str,
        *,
        status: str | None = None,
        tag: str | None = None,
        prefix: str | None = None,
    ) -> dict[str, StoreEntry]:
        """Query entries with filters."""
        namespace = self.load_namespace(ns)
        result = {}
        for key, entry in namespace.entries.items():
            if prefix and not key.startswith(prefix):
                continue
            if status and entry.status != status:
                continue
            if tag and tag not in entry.tags:
                continue
            result[key] = entry
        return result

    # ------------------------------------------------------------------
    # Bulk operations
    # ------------------------------------------------------------------

    def get_tree(self, ns: str) -> dict:
        """Reconstruct hierarchical tree from dotted keys.

        Example: {"a.b": 1, "a.c": 2} -> {"a": {"b": 1, "c": 2}}
        """
        namespace = self.load_namespace(ns)
        tree: dict = {}
        for key, entry in sorted(namespace.entries.items()):
            parts = key.split(".")
            node = tree
            for part in parts[:-1]:
                if part not in node:
                    node[part] = {}
                node = node[part]
            node[parts[-1]] = entry.model_dump()
        return tree

    def set_many(
        self,
        ns: str,
        entries: dict[str, Any],
        *,
        status: str = "active",
        source: str | None = None,
    ) -> int:
        """Set multiple entries at once. Returns count of entries set."""
        namespace = self.load_namespace(ns)
        count = 0
        for key, value in entries.items():
            if namespace.target_schema:
                self._validate_entry(namespace.target_schema, key, value, status)
            namespace.entries[key] = StoreEntry(
                value=value,
                status=status,
                source=source,
            )
            count += 1
        namespace.updated_at = utc_now()
        self._save_namespace(namespace)
        return count

    def snapshot(self) -> dict[str, Any]:
        """Full dump of all namespaces."""
        result = {}
        for ns_name in self.list_namespaces():
            ns = self.load_namespace(ns_name)
            result[ns_name] = ns.model_dump()
        return result

    # ------------------------------------------------------------------
    # Schema operations
    # ------------------------------------------------------------------

    def set_schema(self, ns: str, schema: TargetSchema) -> Namespace:
        """Set or update the target schema for a namespace."""
        namespace = self.load_namespace(ns)
        namespace.target_schema = schema
        namespace.updated_at = utc_now()

        # Seed missing entries from schema
        namespace = self._seed_from_schema(namespace, schema)

        self._save_namespace(namespace)
        return namespace

    def get_schema(self, ns: str) -> TargetSchema | None:
        namespace = self.load_namespace(ns)
        return namespace.target_schema

    def _seed_from_schema(self, namespace: Namespace, schema: TargetSchema) -> Namespace:
        """Pre-populate entries based on schema type."""
        if isinstance(schema, TableSchema):
            for row in schema.rows:
                for col in schema.columns:
                    key = f"{row}.{col}"
                    if key not in namespace.entries:
                        namespace.entries[key] = StoreEntry(
                            value=schema.default_value,
                            status="active",
                            source="schema_seed",
                        )

        elif isinstance(schema, ChecklistSchema):
            for item in schema.items:
                label = item if isinstance(item, str) else item.label
                key = label.replace(" ", "_").lower()
                if key not in namespace.entries:
                    metadata = {} if isinstance(item, str) else item.metadata
                    namespace.entries[key] = StoreEntry(
                        value=schema.default_state,
                        status="active",
                        source="schema_seed",
                        tags=list(metadata.keys()) if metadata else [],
                    )

        elif isinstance(schema, RecordSchema):
            for field_name, field_def in schema.fields.items():
                if field_name not in namespace.entries:
                    if isinstance(field_def, str):
                        default = None
                    else:
                        default = field_def.default
                    namespace.entries[field_name] = StoreEntry(
                        value=default,
                        status="active",
                        source="schema_seed",
                    )

        return namespace

    def _validate_entry(
        self,
        schema: TargetSchema,
        key: str,
        value: Any,
        status: str,
    ) -> None:
        """Validate an entry against the target schema. Raises on violation."""
        if isinstance(schema, TableSchema):
            parts = key.split(".", 1)
            if len(parts) == 2:
                row, col = parts
                if row not in schema.rows:
                    raise DataStoreError(
                        f"Row '{row}' not in schema rows: {schema.rows}"
                    )
                if col not in schema.columns:
                    raise DataStoreError(
                        f"Column '{col}' not in schema columns: {schema.columns}"
                    )
                if schema.cell_type == "enum" and value not in schema.cell_domain:
                    raise DataStoreError(
                        f"Value '{value}' not in cell_domain: {schema.cell_domain}"
                    )

        elif isinstance(schema, ChecklistSchema):
            if schema.item_states and value not in schema.item_states:
                raise DataStoreError(
                    f"State '{value}' not in item_states: {schema.item_states}"
                )

        elif isinstance(schema, RecordSchema):
            if key in schema.fields:
                field_def = schema.fields[key]
                if isinstance(field_def, str):
                    field_type = field_def
                else:
                    field_type = field_def.type
                # Basic type validation
                type_map = {
                    "string": str,
                    "number": (int, float),
                    "bool": bool,
                    "datetime": str,
                    "enum": str,
                }
                expected = type_map.get(field_type)
                if expected and value is not None and not isinstance(value, expected):
                    raise DataStoreError(
                        f"Field '{key}': expected {field_type}, got {type(value).__name__}"
                    )

    # ------------------------------------------------------------------
    # Git operations
    # ------------------------------------------------------------------

    def commit(self, message: str) -> str:
        """Commit current state. Returns commit hash."""
        return self._git.commit_all(message)

    def log(self, limit: int = 20) -> list[CommitInfo]:
        return self._git.log(limit)

    def diff(self, from_ref: str | None = None, to_ref: str | None = None) -> str:
        return self._git.diff(from_ref, to_ref)

    def branch(self, name: str) -> None:
        self._git.create_branch(name)

    def checkout(self, ref: str) -> None:
        self._git.checkout(ref)

    def list_branches(self) -> list[str]:
        return self._git.list_branches()

    def current_branch(self) -> str:
        return self._git.current_branch()

    def rollback(self, ref: str) -> None:
        self._git.reset_to(ref)

    def tag(self, name: str) -> None:
        self._git.tag(name)

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    def _ns_path(self, ns: str) -> Path:
        return self.ns_dir / f"{ns}.json"

    def _save_namespace(self, namespace: Namespace) -> None:
        self.ns_dir.mkdir(parents=True, exist_ok=True)
        path = self._ns_path(namespace.ns)
        path.write_text(
            json.dumps(namespace.model_dump(), ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
