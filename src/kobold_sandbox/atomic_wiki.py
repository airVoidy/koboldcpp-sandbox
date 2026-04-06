from __future__ import annotations

from typing import Any, Literal

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from .data_store.api import BranchRequest, CheckoutRequest, CommitRequest, TagRequest
from .data_store.schema import utc_now
from .data_store.store import DataStore


WIKI_NAMESPACE = "wiki_pages"


class WikiMessageEnvelope(BaseModel):
    role: Literal["system", "user", "assistant", "config"] = "config"
    kind: Literal["wiki_page", "config_page"] = "config_page"
    format: Literal["wikilike", "plain_text", "markdown"] = "wikilike"
    text: str = ""


class WikiBlock(BaseModel):
    block_id: str
    kind: Literal["text", "table", "alias", "param"] = "text"
    label: str | None = None
    text: str | None = None
    headers: list[str] = Field(default_factory=list)
    rows: list[list[Any]] = Field(default_factory=list)
    ref: str | None = None


class WikiPage(BaseModel):
    page_id: str
    slug: str
    title: str
    page_kind: Literal["config_page", "wiki_page", "grammar_page", "function_page"] = "config_page"
    item_kind: Literal["text", "table", "alias", "param"] = "text"
    message: WikiMessageEnvelope
    blocks: list[WikiBlock] = Field(default_factory=list)
    aliases: list[str] = Field(default_factory=list)
    tags: list[str] = Field(default_factory=list)
    links: list[str] = Field(default_factory=list)
    source: str | None = None
    updated_at: str = Field(default_factory=utc_now)


class UpsertWikiPageRequest(BaseModel):
    title: str | None = None
    page_kind: Literal["config_page", "wiki_page", "grammar_page", "function_page"] = "config_page"
    item_kind: Literal["text", "table", "alias", "param"] = "text"
    text: str = ""
    headers: list[str] = Field(default_factory=list)
    rows: list[list[Any]] = Field(default_factory=list)
    alias_of: str | None = None
    aliases: list[str] = Field(default_factory=list)
    tags: list[str] = Field(default_factory=list)
    links: list[str] = Field(default_factory=list)
    source: str | None = None
    auto_commit: bool = True
    commit_message: str | None = None


class MigrateGlobalParamsRequest(BaseModel):
    atomic_params: dict[str, str] = Field(default_factory=dict)
    global_items: list[dict[str, Any]] = Field(default_factory=list)
    auto_commit: bool = True
    commit_message: str | None = None
    replace_existing: bool = False


def _render_message_text(
    slug: str,
    item_kind: str,
    text: str,
    headers: list[str],
    rows: list[list[Any]],
    alias_of: str | None,
) -> str:
    if item_kind in {"text", "param"}:
        return text or ""
    if item_kind == "alias":
        return f"Alias to: {alias_of or ''}".strip()
    if item_kind == "table":
        if not headers:
            return f"Table page: {slug}"
        head = "| " + " | ".join(headers) + " |"
        sep = "| " + " | ".join(["---"] * len(headers)) + " |"
        body = ["| " + " | ".join(str(cell) for cell in row) + " |" for row in rows]
        return "\n".join([head, sep, *body])
    return text or ""


def _build_page(slug: str, req: UpsertWikiPageRequest) -> WikiPage:
    block = WikiBlock(
        block_id=f"{slug}:block:1",
        kind=req.item_kind,
        label=req.title or slug,
        text=req.text if req.item_kind in {"text", "param"} else None,
        headers=req.headers,
        rows=req.rows,
        ref=req.alias_of,
    )
    message_text = _render_message_text(
        slug,
        req.item_kind,
        req.text,
        req.headers,
        req.rows,
        req.alias_of,
    )
    return WikiPage(
        page_id=f"wiki:{slug}",
        slug=slug,
        title=req.title or f"$config.{slug}",
        page_kind=req.page_kind,
        item_kind=req.item_kind,
        message=WikiMessageEnvelope(text=message_text),
        blocks=[block],
        aliases=req.aliases or [f"$config.{slug}"],
        tags=req.tags,
        links=req.links,
        source=req.source,
    )


def _page_summary(page: WikiPage) -> dict[str, Any]:
    return {
        "slug": page.slug,
        "title": page.title,
        "page_kind": page.page_kind,
        "item_kind": page.item_kind,
        "updated_at": page.updated_at,
        "aliases": page.aliases,
        "tags": page.tags,
    }


def _item_to_request(item: dict[str, Any]) -> UpsertWikiPageRequest:
    item_type = str(item.get("type") or "text").strip().lower()
    name = str(item.get("name") or "").strip()
    if not name:
        raise ValueError("global item name is required")
    if item_type == "table":
        return UpsertWikiPageRequest(
            title=f"$config.{name}",
            item_kind="table",
            headers=[str(h) for h in item.get("headers") or []],
            rows=[[cell for cell in row] for row in item.get("rows") or []],
            tags=["config", "wikilike", "table"],
            source="global_items_migration",
            auto_commit=False,
        )
    if item_type == "alias":
        return UpsertWikiPageRequest(
            title=f"$config.{name}",
            item_kind="alias",
            alias_of=str(item.get("ref") or "").strip() or None,
            tags=["config", "wikilike", "alias"],
            source="global_items_migration",
            auto_commit=False,
        )
    return UpsertWikiPageRequest(
        title=f"$config.{name}",
        item_kind="text",
        text=str(item.get("text") or ""),
        tags=["config", "wikilike", "text"],
        source="global_items_migration",
        auto_commit=False,
    )


def create_atomic_wiki_router(store: DataStore) -> APIRouter:
    router = APIRouter(tags=["atomic-wiki"])

    if not store.exists():
        store.init()
    if WIKI_NAMESPACE not in store.list_namespaces():
        store.create_namespace(WIKI_NAMESPACE)

    def _load_page(slug: str) -> WikiPage:
        entry = store.get(WIKI_NAMESPACE, slug)
        if entry is None:
            raise HTTPException(404, f"Wiki page '{slug}' not found")
        return WikiPage.model_validate(entry.value)

    def _save_page(slug: str, page: WikiPage, source: str | None) -> None:
        store.set(
            WIKI_NAMESPACE,
            slug,
            page.model_dump(),
            source=source or "atomic_wiki",
            tags=list(page.tags),
        )

    @router.get("/")
    def wiki_status():
        return {
            "status": "ok",
            "namespace": WIKI_NAMESPACE,
            "count": len(store.list_keys(WIKI_NAMESPACE)),
        }

    @router.get("/pages")
    def list_pages(full: bool = False):
        pages: list[dict[str, Any]] = []
        for key in store.list_keys(WIKI_NAMESPACE):
            entry = store.get(WIKI_NAMESPACE, key)
            if entry is None:
                continue
            try:
                page = WikiPage.model_validate(entry.value)
                pages.append(page.model_dump() if full else _page_summary(page))
            except Exception:
                pages.append({"slug": key, "title": key, "page_kind": "unknown", "item_kind": "unknown"})
        return {"pages": sorted(pages, key=lambda item: item["slug"])}

    @router.get("/pages/{slug}")
    def get_page(slug: str):
        return _load_page(slug).model_dump()

    @router.put("/pages/{slug}")
    def upsert_page(slug: str, req: UpsertWikiPageRequest):
        page = _build_page(slug, req)
        _save_page(slug, page, req.source)
        commit_hash = None
        if req.auto_commit:
            commit_hash = store.commit(req.commit_message or f"Update wiki page: {slug}") or None
        return {
            "page": page.model_dump(),
            "commit": commit_hash,
        }

    @router.delete("/pages/{slug}")
    def delete_page(slug: str, auto_commit: bool = True):
        deleted = store.delete(WIKI_NAMESPACE, slug)
        if not deleted:
            raise HTTPException(404, f"Wiki page '{slug}' not found")
        commit_hash = None
        if auto_commit:
            commit_hash = store.commit(f"Delete wiki page: {slug}") or None
        return {"deleted": slug, "commit": commit_hash}

    @router.post("/migrate/global-params")
    def migrate_global_params(req: MigrateGlobalParamsRequest):
        existing = set(store.list_keys(WIKI_NAMESPACE))
        migrated: list[str] = []
        skipped: list[str] = []

        for key, value in req.atomic_params.items():
            slug = str(key).strip()
            if not slug:
                continue
            if slug in existing and not req.replace_existing:
                skipped.append(slug)
                continue
            page_req = UpsertWikiPageRequest(
                title=f"$config.{slug}",
                item_kind="param",
                text=str(value or ""),
                tags=["config", "wikilike", "param"],
                source="global_params_migration",
                auto_commit=False,
            )
            page = _build_page(slug, page_req)
            _save_page(slug, page, page_req.source)
            existing.add(slug)
            migrated.append(slug)

        for item in req.global_items:
            name = str(item.get("name") or "").strip()
            if not name:
                continue
            slug = name
            if slug in existing and not req.replace_existing:
                skipped.append(slug)
                continue
            page_req = _item_to_request(item)
            page = _build_page(slug, page_req)
            _save_page(slug, page, page_req.source)
            existing.add(slug)
            migrated.append(slug)

        commit_hash = None
        if req.auto_commit and migrated:
            commit_hash = store.commit(req.commit_message or "Migrate global params to wiki pages") or None

        return {
            "namespace": WIKI_NAMESPACE,
            "migrated": migrated,
            "skipped": skipped,
            "commit": commit_hash,
        }

    @router.post("/git/commit")
    def git_commit(req: CommitRequest):
        return {"hash": store.commit(req.message) or None, "message": req.message}

    @router.get("/git/log")
    def git_log(limit: int = 20):
        return {"commits": [c.model_dump() for c in store.log(limit)]}

    @router.get("/git/diff")
    def git_diff(from_ref: str | None = None, to_ref: str | None = None):
        return {"diff": store.diff(from_ref, to_ref)}

    @router.get("/git/branches")
    def git_branches():
        return {"branches": store.list_branches(), "current": store.current_branch()}

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

    @router.get("/export")
    def wiki_export():
        """Export all pages as compact JSON — one file, loadable back via /import."""
        pages = {}
        for slug in store.list_keys(WIKI_NAMESPACE):
            entry = store.get(WIKI_NAMESPACE, slug)
            if entry is None:
                continue
            p = entry.value
            compact: dict[str, Any] = {
                "title": p.get("title", slug),
                "kind": p.get("item_kind", "text"),
                "page_kind": p.get("page_kind", "config_page"),
                "text": p.get("message", {}).get("text", ""),
                "tags": p.get("tags", []),
            }
            if p.get("aliases"):
                compact["aliases"] = p["aliases"]
            blocks = p.get("blocks", [])
            if len(blocks) == 1 and blocks[0].get("kind") == "table":
                compact["headers"] = blocks[0].get("headers", [])
                compact["rows"] = blocks[0].get("rows", [])
            elif len(blocks) > 1:
                compact["blocks"] = blocks
            pages[slug] = compact
        return {"pages": pages, "count": len(pages)}

    class WikiImportRequest(BaseModel):
        pages: dict[str, dict[str, Any]]
        auto_commit: bool = True
        replace_existing: bool = True

    @router.post("/import")
    def wiki_import(req: WikiImportRequest):
        """Import pages from compact JSON format (from /export or root/wiki.json)."""
        imported = []
        skipped = []
        existing = set(store.list_keys(WIKI_NAMESPACE))
        for slug, data in req.pages.items():
            if slug in existing and not req.replace_existing:
                skipped.append(slug)
                continue
            page_req = UpsertWikiPageRequest(
                title=data.get("title", slug),
                page_kind=data.get("page_kind", "config_page"),
                item_kind=data.get("kind", "text"),
                text=data.get("text", ""),
                headers=data.get("headers", []),
                rows=data.get("rows", []),
                tags=data.get("tags", []),
                aliases=data.get("aliases", []),
                auto_commit=False,
            )
            page = _build_page(slug, page_req)
            _save_page(slug, page, "wiki_import")
            imported.append(slug)
        commit_hash = None
        if req.auto_commit and imported:
            commit_hash = store.commit(f"Wiki import: {len(imported)} pages") or None
        return {"imported": imported, "skipped": skipped, "commit": commit_hash}

    return router
