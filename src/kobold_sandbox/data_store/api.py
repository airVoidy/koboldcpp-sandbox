"""FastAPI router for DataStore.

Mount into server.py:
    from .data_store.api import create_datastore_router
    app.include_router(create_datastore_router(sandbox_root), prefix="/api/datastore")
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from .schema import (
    ChecklistSchema,
    RecordSchema,
    TableSchema,
    TargetSchema,
)
from .store import DataStore, DataStoreError


# ---------------------------------------------------------------------------
# Request models
# ---------------------------------------------------------------------------

class CreateNamespaceRequest(BaseModel):
    ns: str
    target_schema: dict[str, Any] | None = None


class SetEntryRequest(BaseModel):
    value: Any
    status: str = "active"
    source: str | None = None
    tags: list[str] = []


class BulkSetRequest(BaseModel):
    entries: dict[str, Any]
    status: str = "active"
    source: str | None = None


class SetSchemaRequest(BaseModel):
    target_schema: dict[str, Any]


class CommitRequest(BaseModel):
    message: str


class BranchRequest(BaseModel):
    name: str


class CheckoutRequest(BaseModel):
    ref: str


class TagRequest(BaseModel):
    name: str


# ---------------------------------------------------------------------------
# Schema parser
# ---------------------------------------------------------------------------

def _parse_schema(raw: dict[str, Any]) -> TargetSchema:
    """Parse a raw dict into the correct TargetSchema subtype."""
    schema_type = raw.get("type")
    if schema_type == "table":
        return TableSchema.model_validate(raw)
    elif schema_type == "checklist":
        return ChecklistSchema.model_validate(raw)
    elif schema_type == "record":
        return RecordSchema.model_validate(raw)
    else:
        raise HTTPException(400, f"Unknown schema type: {schema_type}")


# ---------------------------------------------------------------------------
# Router factory
# ---------------------------------------------------------------------------

def create_datastore_router(datastore_root: Path) -> APIRouter:
    """Create a FastAPI router bound to a specific DataStore root."""

    router = APIRouter(tags=["datastore"])
    store = DataStore(datastore_root)

    # Ensure store is initialized
    if not store.exists():
        store.init()

    # --- Health ---

    @router.get("/")
    def datastore_status():
        meta = store.load_meta()
        return {
            "status": "ok",
            "store_name": meta.store_name,
            "namespaces": meta.namespaces,
            "schema_version": meta.schema_version,
        }

    # --- Namespace CRUD ---

    @router.get("/namespaces")
    def list_namespaces():
        return {"namespaces": store.list_namespaces()}

    @router.post("/namespaces")
    def create_namespace(req: CreateNamespaceRequest):
        try:
            schema = _parse_schema(req.target_schema) if req.target_schema else None
            ns = store.create_namespace(req.ns, target_schema=schema)
            return ns.model_dump()
        except DataStoreError as e:
            raise HTTPException(409, str(e))

    @router.get("/namespaces/{ns}")
    def get_namespace(ns: str):
        try:
            return store.load_namespace(ns).model_dump()
        except DataStoreError as e:
            raise HTTPException(404, str(e))

    @router.delete("/namespaces/{ns}")
    def delete_namespace(ns: str):
        store.delete_namespace(ns)
        return {"deleted": ns}

    # --- Schema ---

    @router.get("/namespaces/{ns}/schema")
    def get_schema(ns: str):
        try:
            schema = store.get_schema(ns)
            return {"schema": schema.model_dump() if schema else None}
        except DataStoreError as e:
            raise HTTPException(404, str(e))

    @router.put("/namespaces/{ns}/schema")
    def set_schema(ns: str, req: SetSchemaRequest):
        try:
            schema = _parse_schema(req.target_schema)
            result = store.set_schema(ns, schema)
            return result.model_dump()
        except DataStoreError as e:
            raise HTTPException(400, str(e))

    # --- Entry CRUD ---

    @router.get("/{ns}/entries")
    def list_entries(ns: str, prefix: str | None = None, status: str | None = None, tag: str | None = None):
        try:
            entries = store.query(ns, prefix=prefix, status=status, tag=tag)
            return {
                "ns": ns,
                "count": len(entries),
                "entries": {k: v.model_dump() for k, v in entries.items()},
            }
        except DataStoreError as e:
            raise HTTPException(404, str(e))

    @router.get("/{ns}/entries/{key:path}")
    def get_entry(ns: str, key: str):
        try:
            entry = store.get(ns, key)
            if entry is None:
                raise HTTPException(404, f"Key '{key}' not found in '{ns}'")
            return entry.model_dump()
        except DataStoreError as e:
            raise HTTPException(404, str(e))

    @router.put("/{ns}/entries/{key:path}")
    def set_entry(ns: str, key: str, req: SetEntryRequest):
        try:
            entry = store.set(ns, key, req.value, status=req.status, source=req.source, tags=req.tags)
            return entry.model_dump()
        except DataStoreError as e:
            raise HTTPException(400, str(e))

    @router.delete("/{ns}/entries/{key:path}")
    def delete_entry(ns: str, key: str):
        try:
            deleted = store.delete(ns, key)
            if not deleted:
                raise HTTPException(404, f"Key '{key}' not found in '{ns}'")
            return {"deleted": key}
        except DataStoreError as e:
            raise HTTPException(404, str(e))

    @router.post("/{ns}/entries/_bulk")
    def bulk_set(ns: str, req: BulkSetRequest):
        try:
            count = store.set_many(ns, req.entries, status=req.status, source=req.source)
            return {"ns": ns, "count": count}
        except DataStoreError as e:
            raise HTTPException(400, str(e))

    # --- Tree view ---

    @router.get("/{ns}/tree")
    def get_tree(ns: str):
        try:
            tree = store.get_tree(ns)
            return {"ns": ns, "tree": tree}
        except DataStoreError as e:
            raise HTTPException(404, str(e))

    # --- Snapshot ---

    @router.get("/snapshot")
    def snapshot():
        return store.snapshot()

    # --- Git operations ---

    @router.post("/git/commit")
    def git_commit(req: CommitRequest):
        commit_hash = store.commit(req.message)
        return {"hash": commit_hash or None, "message": req.message}

    @router.get("/git/log")
    def git_log(limit: int = 20):
        return {"commits": [c.model_dump() for c in store.log(limit)]}

    @router.get("/git/diff")
    def git_diff(from_ref: str | None = None, to_ref: str | None = None):
        return {"diff": store.diff(from_ref, to_ref)}

    @router.get("/git/branches")
    def git_branches():
        return {
            "branches": store.list_branches(),
            "current": store.current_branch(),
        }

    @router.post("/git/branch")
    def git_branch(req: BranchRequest):
        store.branch(req.name)
        return {"created": req.name}

    @router.post("/git/checkout")
    def git_checkout(req: CheckoutRequest):
        store.checkout(req.ref)
        return {"checked_out": req.ref}

    @router.post("/git/rollback")
    def git_rollback(req: CheckoutRequest):
        store.rollback(req.ref)
        return {"rolled_back_to": req.ref}

    @router.post("/git/tag")
    def git_tag(req: TagRequest):
        store.tag(req.name)
        return {"tagged": req.name}

    @router.get("/git/current-branch")
    def git_current_branch():
        return {"branch": store.current_branch()}

    return router
