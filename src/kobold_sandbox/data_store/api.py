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
    Contract,
    ContractInstance,
    ContractSlot,
    PatchProposal,
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


class SaveContractRequest(BaseModel):
    name: str
    icon: str = "#"
    extends: str | None = None
    slots: list[dict[str, Any]] = []
    patch: list[dict[str, Any]] | None = None


class InstantiateRequest(BaseModel):
    contract: str          # contract name
    node_id: str           # owner node id
    slot_bind: str         # which slot to instantiate
    value: Any = None      # initial value (or None = empty)
    source: str | None = None


class ProposePatchRequest(BaseModel):
    node_id: str
    contract: str          # contract name of the target node
    data: dict[str, Any]
    meta: dict[str, Any] = {}


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

    # ------------------------------------------------------------------
    # Contracts — semantic templates (Schema workscope)
    # ------------------------------------------------------------------

    _CONTRACTS_NS = "_contracts"
    _INSTANCES_NS = "_contract_instances"
    _PATCHES_NS = "_contract_patches"

    def _ensure_contract_ns():
        for ns in (_CONTRACTS_NS, _INSTANCES_NS, _PATCHES_NS):
            if ns not in store.list_namespaces():
                store.create_namespace(ns)

    @router.get("/contracts")
    def list_contracts():
        """List all contract templates."""
        _ensure_contract_ns()
        entries = store.query(_CONTRACTS_NS)
        return {
            "contracts": {
                k: e.value for k, e in entries.items()
            }
        }

    @router.get("/contracts/{name}")
    def get_contract(name: str):
        """Get a single contract template."""
        _ensure_contract_ns()
        entry = store.get(_CONTRACTS_NS, name)
        if entry is None:
            raise HTTPException(404, f"Contract '{name}' not found")
        return entry.value

    @router.put("/contracts/{name}")
    def save_contract(name: str, req: SaveContractRequest):
        """Create or update a contract template."""
        _ensure_contract_ns()
        contract = Contract(
            name=name,
            icon=req.icon,
            extends=req.extends,
            slots=[ContractSlot.model_validate(s) for s in req.slots],
            patch=req.patch,
        )
        store.set(_CONTRACTS_NS, name, contract.model_dump())
        return {"saved": name}

    @router.delete("/contracts/{name}")
    def delete_contract(name: str):
        """Delete a contract template."""
        _ensure_contract_ns()
        store.delete(_CONTRACTS_NS, name)
        return {"deleted": name}

    @router.post("/contracts/instantiate")
    def instantiate_contract(req: InstantiateRequest):
        """Instantiate a contract property — accept the contract for a node.

        Creates a scoped DS key (e.g. axioms.n_0) and records the instance.
        No data is created if value is None — just the binding record.
        """
        _ensure_contract_ns()
        # Verify contract exists
        entry = store.get(_CONTRACTS_NS, req.contract)
        if entry is None:
            raise HTTPException(404, f"Contract '{req.contract}' not found")
        contract_data = entry.value

        # Find the slot
        slots = contract_data.get("slots", [])
        slot = next((s for s in slots if s.get("bind") == req.slot_bind), None)
        if slot is None:
            raise HTTPException(400, f"Slot '{req.slot_bind}' not in contract '{req.contract}'")

        ds_template = slot.get("ds")
        if not ds_template:
            raise HTTPException(400, f"Slot '{req.slot_bind}' has no ds template")

        ds_key = ds_template.replace("$id", req.node_id)

        # Record the instance
        instance = ContractInstance(
            contract=req.contract,
            node_id=req.node_id,
            ds_key=ds_key,
            field=req.slot_bind,
            source=req.source,
        )
        instance_key = f"{req.node_id}.{req.slot_bind}"
        store.set(_INSTANCES_NS, instance_key, instance.model_dump())

        # If value provided, write to the scoped data namespace
        if req.value is not None:
            data_ns = req.contract + "_data"
            if data_ns not in store.list_namespaces():
                store.create_namespace(data_ns)
            store.set(data_ns, ds_key, req.value)

        return {
            "instance": instance.model_dump(),
            "ds_key": ds_key,
        }

    @router.get("/contracts/instances/{node_id}")
    def get_node_instances(node_id: str):
        """Get all contract instances for a node."""
        _ensure_contract_ns()
        entries = store.query(_INSTANCES_NS, prefix=node_id + ".")
        return {
            "instances": {k: e.value for k, e in entries.items()}
        }

    @router.post("/contracts/propose")
    def propose_patch(req: ProposePatchRequest):
        """Propose data to a node — contract rules decide accept/pending.

        Evaluates each key against the contract's slot accept rules.
        Auto-accepted data is written immediately. Pending data waits.
        """
        _ensure_contract_ns()
        # Load contract
        entry = store.get(_CONTRACTS_NS, req.contract)
        if entry is None:
            raise HTTPException(404, f"Contract '{req.contract}' not found")
        contract_data = entry.value
        slots = contract_data.get("slots", [])

        resolved = {}
        accepted_data = {}

        for key, val in req.data.items():
            # Match slot: exact bind or bind without _list suffix
            slot = next(
                (s for s in slots if s.get("bind") == key or s.get("bind") == key + "_list"),
                None
            )
            if slot is None:
                resolved[key] = "unknown"
                continue

            rule = slot.get("accept", "auto")
            if rule == "auto":
                resolved[key] = "accepted"
                accepted_data[slot["bind"]] = val
            else:
                resolved[key] = "pending"

        # Write accepted data to instances
        for field, val in accepted_data.items():
            instance_key = f"{req.node_id}.{field}"
            # Update instance value in data namespace
            data_ns = req.contract + "_data"
            if data_ns not in store.list_namespaces():
                store.create_namespace(data_ns)
            slot = next(s for s in slots if s.get("bind") == field)
            ds_template = slot.get("ds", "")
            ds_key = ds_template.replace("$id", req.node_id) if ds_template else f"{field}.{req.node_id}"
            store.set(data_ns, ds_key, val)

        # Store patch proposal if anything pending/unknown
        proposal = PatchProposal(
            node_id=req.node_id,
            data=req.data,
            meta=req.meta,
            resolved=resolved,
        )
        has_pending = any(s in ("pending", "unknown") for s in resolved.values())
        if has_pending:
            patch_key = f"{req.node_id}.{proposal.created_at}"
            store.set(_PATCHES_NS, patch_key, proposal.model_dump())

        return {
            "resolved": resolved,
            "pending": has_pending,
            "proposal": proposal.model_dump(),
        }

    @router.get("/contracts/patches/{node_id}")
    def get_pending_patches(node_id: str):
        """Get pending patch proposals for a node."""
        _ensure_contract_ns()
        entries = store.query(_PATCHES_NS, prefix=node_id + ".")
        return {
            "patches": {k: e.value for k, e in entries.items()}
        }

    return router
