from __future__ import annotations

import hashlib
import json
import uuid
from typing import Any, Literal

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from .data_store.schema import utc_now
from .data_store.store import DataStore


DATA_TEXT_NAMESPACE = "data_text_artifacts"
DATA_REVISION_NAMESPACE = "data_revision_graph"


class DataTextArtifactMessage(BaseModel):
    text: str = ""
    format: Literal["plain_text", "markdown", "wikilike"] = "wikilike"


class DataTextArtifact(BaseModel):
    artifact_id: str
    data_ref: str
    scope: Literal["temp", "local", "global"] = "local"
    artifact_kind: Literal["wiki", "message", "note", "summary", "prompt"] = "wiki"
    title: str | None = None
    message: DataTextArtifactMessage = Field(default_factory=DataTextArtifactMessage)
    tags: list[str] = Field(default_factory=list)
    source_refs: list[str] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)
    updated_at: str = Field(default_factory=utc_now)


class UpsertDataTextArtifactRequest(BaseModel):
    scope: Literal["temp", "local", "global"] = "local"
    artifact_kind: Literal["wiki", "message", "note", "summary", "prompt"] = "wiki"
    title: str | None = None
    text: str = ""
    format: Literal["plain_text", "markdown", "wikilike"] = "wikilike"
    tags: list[str] = Field(default_factory=list)
    source_refs: list[str] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)
    auto_commit: bool = False
    commit_message: str | None = None


class CommitDataRevisionRequest(BaseModel):
    message: str
    text_refs: list[str] = Field(default_factory=list)
    object_hashes: dict[str, str] = Field(default_factory=dict)
    objects: dict[str, Any] = Field(default_factory=dict)
    metadata: dict[str, Any] = Field(default_factory=dict)


def _stable_hash(value: Any) -> str:
    payload = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def _build_text_artifact(data_ref: str, req: UpsertDataTextArtifactRequest) -> DataTextArtifact:
    return DataTextArtifact(
        artifact_id=f"data:{data_ref}",
        data_ref=data_ref,
        scope=req.scope,
        artifact_kind=req.artifact_kind,
        title=req.title,
        message=DataTextArtifactMessage(text=req.text, format=req.format),
        tags=req.tags,
        source_refs=req.source_refs,
        metadata=req.metadata,
    )


def create_atomic_data_revision_router(store: DataStore) -> APIRouter:
    router = APIRouter(tags=["atomic-data-revision"])

    if not store.exists():
        store.init()
    for namespace in (DATA_TEXT_NAMESPACE, DATA_REVISION_NAMESPACE):
        if namespace not in store.list_namespaces():
            store.create_namespace(namespace)

    def _load_text_artifact(data_ref: str) -> DataTextArtifact:
        entry = store.get(DATA_TEXT_NAMESPACE, data_ref)
        if entry is None:
            raise HTTPException(404, f"Data text artifact '{data_ref}' not found")
        return DataTextArtifact.model_validate(entry.value)

    @router.get("/")
    def status() -> dict[str, Any]:
        return {
            "status": "ok",
            "text_namespace": DATA_TEXT_NAMESPACE,
            "revision_namespace": DATA_REVISION_NAMESPACE,
            "text_count": len(store.list_keys(DATA_TEXT_NAMESPACE)),
            "revision_count": len(store.list_keys(DATA_REVISION_NAMESPACE)),
        }

    @router.get("/text")
    def list_text_artifacts(prefix: str | None = None) -> dict[str, Any]:
        artifacts: list[dict[str, Any]] = []
        for key in store.list_keys(DATA_TEXT_NAMESPACE, prefix=prefix):
            entry = store.get(DATA_TEXT_NAMESPACE, key)
            if entry is None:
                continue
            try:
                artifact = DataTextArtifact.model_validate(entry.value)
            except Exception:
                continue
            artifacts.append(
                {
                    "data_ref": artifact.data_ref,
                    "scope": artifact.scope,
                    "artifact_kind": artifact.artifact_kind,
                    "title": artifact.title,
                    "updated_at": artifact.updated_at,
                    "tags": artifact.tags,
                    "source_refs": artifact.source_refs,
                }
            )
        return {"artifacts": artifacts}

    @router.get("/text/{data_ref:path}")
    def get_text_artifact(data_ref: str) -> dict[str, Any]:
        return _load_text_artifact(data_ref).model_dump()

    @router.put("/text/{data_ref:path}")
    def upsert_text_artifact(data_ref: str, req: UpsertDataTextArtifactRequest) -> dict[str, Any]:
        artifact = _build_text_artifact(data_ref, req)
        store.set(
            DATA_TEXT_NAMESPACE,
            data_ref,
            artifact.model_dump(),
            source="atomic_data_revision",
            tags=list(dict.fromkeys([req.scope, req.artifact_kind, *req.tags])),
        )
        commit_hash = None
        if req.auto_commit:
            commit_hash = store.commit(req.commit_message or f"Update data text artifact: {data_ref}") or None
        return {
            "artifact": artifact.model_dump(),
            "commit": commit_hash,
        }

    @router.post("/revision/commit")
    def commit_revision(req: CommitDataRevisionRequest) -> dict[str, Any]:
        computed_hashes = {name: _stable_hash(value) for name, value in req.objects.items()}
        object_hashes = {**computed_hashes, **req.object_hashes}
        revision_id = f"rev_{uuid.uuid4().hex[:12]}"
        current_branch = store.current_branch()
        parent_commit = None
        log = store.log(1)
        if log:
            parent_commit = log[0].hash

        revision_entry = {
            "revision_id": revision_id,
            "created_at": utc_now(),
            "branch": current_branch,
            "parent_commit_ref": parent_commit,
            "text_refs": req.text_refs,
            "object_hashes": object_hashes,
            "metadata": req.metadata,
            "commit_message": req.message,
        }
        store.set(
            DATA_REVISION_NAMESPACE,
            revision_id,
            revision_entry,
            source="atomic_data_revision",
            tags=["revision", current_branch],
        )
        commit_message = f"Data revision {revision_id}: {req.message}"
        commit_hash = store.commit(commit_message) or None

        return {
            "revision": {
                **revision_entry,
                "git_commit_ref": commit_hash,
            },
            "commit": commit_hash,
        }

    @router.get("/revision/log")
    def revision_log(limit: int = 20) -> dict[str, Any]:
        commits = store.log(limit)
        revisions: list[dict[str, Any]] = []
        for key in store.list_keys(DATA_REVISION_NAMESPACE):
            entry = store.get(DATA_REVISION_NAMESPACE, key)
            if entry is None:
                continue
            revision = dict(entry.value if isinstance(entry.value, dict) else {})
            revision_id = str(revision.get("revision_id") or key)
            git_commit_ref = None
            for commit in commits:
                if revision_id in commit.message:
                    git_commit_ref = commit.hash
                    break
            revision["git_commit_ref"] = git_commit_ref
            revisions.append(revision)

        revisions.sort(key=lambda item: str(item.get("created_at") or ""), reverse=True)
        return {
            "revisions": revisions[:limit],
            "current_branch": store.current_branch(),
        }

    return router
