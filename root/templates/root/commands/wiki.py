"""wiki - manage project wiki via CMD.

Usage:
  /wiki init              Initialize wiki structure under root/wiki/
  /wiki status            Show page/source counts and last update
  /wiki ingest <path>     Ingest a local file as wiki source note
  /wiki index             Rebuild wiki index page
  /wiki list              List all pages
  /wiki read <slug>       Read a wiki page
  /wiki write <slug> <text>  Create or update a page
  /wiki rm <slug>         Delete a page
"""
import json as _json
import os
import time


def execute(args, user, scope, ws):
    if not args:
        return _status(ws)
    sub = args[0].lower()
    rest = args[1:]

    dispatch = {
        "init": lambda: _init(ws, user),
        "status": lambda: _status(ws),
        "ingest": lambda: _ingest(ws, user, rest),
        "index": lambda: _rebuild_index(ws),
        "list": lambda: _list_pages(ws),
        "ls": lambda: _list_pages(ws),
        "read": lambda: _read_page(ws, rest),
        "cat": lambda: _read_page(ws, rest),
        "write": lambda: _write_page(ws, user, rest),
        "rm": lambda: _rm_page(ws, user, rest),
        "help": lambda: {"help": __doc__},
    }
    handler = dispatch.get(sub)
    if not handler:
        return {"error": f"unknown wiki subcommand: {sub}", "help": __doc__}
    return handler()


def _wiki_root(ws):
    return ws.root / "wiki"


def _pages_dir(ws):
    return _wiki_root(ws) / "pages"


def _sources_dir(ws):
    return _wiki_root(ws) / "sources"


def _schema_path(ws):
    return _wiki_root(ws) / "schema.md"


def _index_path(ws):
    return _wiki_root(ws) / "index.md"


def _log_path(ws):
    return _wiki_root(ws) / "log.md"


def _ts():
    from kobold_sandbox.data_store.schema import utc_now
    return utc_now()


# ── init ──

def _init(ws, user):
    root = _wiki_root(ws)
    already = root.is_dir()
    created = []

    for d in (root, _pages_dir(ws), _sources_dir(ws)):
        if not d.is_dir():
            d.mkdir(parents=True, exist_ok=True)
            created.append(str(d.relative_to(ws.root)))

    schema = _schema_path(ws)
    if not schema.exists():
        schema.write_text(
            "# Wiki Schema\n\n"
            "Project wiki for durable, human-readable knowledge.\n\n"
            "## Structure\n"
            "- `pages/` — wiki pages (markdown)\n"
            "- `sources/` — ingested source notes\n"
            "- `index.md` — auto-generated page index\n"
            "- `log.md` — append-only change log\n"
            "- `schema.md` — this file\n",
            encoding="utf-8",
        )
        created.append("wiki/schema.md")

    index = _index_path(ws)
    if not index.exists():
        index.write_text("# Wiki Index\n\n_No pages yet._\n", encoding="utf-8")
        created.append("wiki/index.md")

    log = _log_path(ws)
    if not log.exists():
        log.write_text(f"# Wiki Log\n\n- {_ts()}: wiki initialized by {user}\n", encoding="utf-8")
        created.append("wiki/log.md")

    return {
        "ok": True,
        "root": str(root.relative_to(ws.root)),
        "created": created,
        "already_existed": already and not created,
    }


# ── status ──

def _status(ws):
    root = _wiki_root(ws)
    if not root.is_dir():
        return {"initialized": False, "hint": "run /wiki init"}

    pages = list(_pages_dir(ws).glob("*.md")) if _pages_dir(ws).is_dir() else []
    sources = list(_sources_dir(ws).glob("*.md")) if _sources_dir(ws).is_dir() else []

    all_files = pages + sources + [
        p for p in [_schema_path(ws), _index_path(ws), _log_path(ws)] if p.exists()
    ]
    last_mtime = max((f.stat().st_mtime for f in all_files), default=0)

    return {
        "initialized": True,
        "root": str(root.relative_to(ws.root)),
        "pages": len(pages),
        "sources": len(sources),
        "has_schema": _schema_path(ws).exists(),
        "has_index": _index_path(ws).exists(),
        "has_log": _log_path(ws).exists(),
        "last_updated": time.strftime("%Y-%m-%dT%H:%M:%S", time.localtime(last_mtime)) if last_mtime else None,
    }


# ── ingest ──

def _ingest(ws, user, rest):
    if not rest:
        return {"error": "usage: /wiki ingest <path>"}

    raw_path = " ".join(rest)
    # Resolve relative to root
    target = ws.root / raw_path
    if not target.is_file():
        # Try absolute
        from pathlib import Path
        target = Path(raw_path)
    if not target.is_file():
        return {"error": f"file not found: {raw_path}"}

    # Ensure wiki exists
    if not _wiki_root(ws).is_dir():
        _init(ws, user)

    content = target.read_text(encoding="utf-8", errors="replace")
    basename = target.stem
    slug = _sanitize_slug(basename)

    # Extract title: first # heading or filename
    title = basename
    for line in content.split("\n"):
        line = line.strip()
        if line.startswith("# "):
            title = line[2:].strip()
            break

    # Summary: first 3 non-empty lines
    lines = [l.strip() for l in content.split("\n") if l.strip() and not l.startswith("#")]
    summary = " ".join(lines[:3])[:200]

    # Excerpt: first 20 lines
    excerpt = "\n".join(content.split("\n")[:20])

    # Write source note
    source_path = _sources_dir(ws) / f"{slug}.md"
    rel_source = str(target.relative_to(ws.root)) if _is_under(target, ws.root) else str(target)

    source_path.write_text(
        f"# {title}\n\n"
        f"## Source\n\n"
        f"- Path: `{rel_source}`\n"
        f"- Ingested at: {_ts()}\n"
        f"- Ingested by: {user}\n\n"
        f"## Summary\n\n{summary}\n\n"
        f"## Excerpt\n\n```\n{excerpt}\n```\n",
        encoding="utf-8",
    )

    # Append to log
    _append_log(ws, f"ingested `{rel_source}` as source \"{title}\" by {user}")

    # Rebuild index
    _rebuild_index(ws)

    return {
        "ok": True,
        "title": title,
        "slug": slug,
        "source": rel_source,
        "summary": summary,
    }


# ── list ──

def _list_pages(ws):
    pages_dir = _pages_dir(ws)
    sources_dir = _sources_dir(ws)
    pages = []
    if pages_dir.is_dir():
        for f in sorted(pages_dir.glob("*.md")):
            pages.append({"slug": f.stem, "type": "page", "size": f.stat().st_size})
    sources = []
    if sources_dir.is_dir():
        for f in sorted(sources_dir.glob("*.md")):
            sources.append({"slug": f.stem, "type": "source", "size": f.stat().st_size})
    return {"pages": pages, "sources": sources}


# ── read ──

def _read_page(ws, rest):
    if not rest:
        return {"error": "usage: /wiki read <slug>"}
    slug = rest[0]
    # Try pages first, then sources
    for d in (_pages_dir(ws), _sources_dir(ws)):
        path = d / f"{slug}.md"
        if path.is_file():
            return {
                "ok": True,
                "slug": slug,
                "type": "page" if d == _pages_dir(ws) else "source",
                "content": path.read_text(encoding="utf-8"),
            }
    return {"error": f"not found: {slug}"}


# ── write ──

def _write_page(ws, user, rest):
    if len(rest) < 2:
        return {"error": "usage: /wiki write <slug> <text>"}
    slug = _sanitize_slug(rest[0])
    text = " ".join(rest[1:])

    if not _wiki_root(ws).is_dir():
        _init(ws, user)

    page_path = _pages_dir(ws) / f"{slug}.md"
    existed = page_path.exists()
    page_path.write_text(text, encoding="utf-8")

    action = "updated" if existed else "created"
    _append_log(ws, f"{action} page \"{slug}\" by {user}")
    _rebuild_index(ws)

    return {"ok": True, "slug": slug, "action": action}


# ── rm ──

def _rm_page(ws, user, rest):
    if not rest:
        return {"error": "usage: /wiki rm <slug>"}
    slug = rest[0]
    for d in (_pages_dir(ws), _sources_dir(ws)):
        path = d / f"{slug}.md"
        if path.is_file():
            path.unlink()
            _append_log(ws, f"deleted \"{slug}\" by {user}")
            _rebuild_index(ws)
            return {"ok": True, "slug": slug, "deleted": True}
    return {"error": f"not found: {slug}"}


# ── index rebuild ──

def _rebuild_index(ws):
    pages_dir = _pages_dir(ws)
    sources_dir = _sources_dir(ws)

    lines = ["# Wiki Index\n"]

    pages = sorted(pages_dir.glob("*.md")) if pages_dir.is_dir() else []
    if pages:
        lines.append("## Pages\n")
        for f in pages:
            title = _extract_title(f)
            lines.append(f"- [{title}](pages/{f.name})")
        lines.append("")

    sources = sorted(sources_dir.glob("*.md")) if sources_dir.is_dir() else []
    if sources:
        lines.append("## Sources\n")
        for f in sources:
            title = _extract_title(f)
            lines.append(f"- [{title}](sources/{f.name})")
        lines.append("")

    if not pages and not sources:
        lines.append("_No pages yet._\n")

    _index_path(ws).write_text("\n".join(lines), encoding="utf-8")
    return {"ok": True, "pages": len(pages), "sources": len(sources)}


# ── helpers ──

def _sanitize_slug(name):
    import re
    slug = re.sub(r"[^a-zA-Z0-9_-]", "-", name.strip().lower())
    slug = re.sub(r"-+", "-", slug).strip("-")
    return slug or f"page-{int(time.time())}"


def _extract_title(path):
    try:
        for line in path.read_text(encoding="utf-8").split("\n"):
            if line.startswith("# "):
                return line[2:].strip()
    except Exception:
        pass
    return path.stem


def _append_log(ws, message):
    log = _log_path(ws)
    if log.exists():
        with open(log, "a", encoding="utf-8") as f:
            f.write(f"- {_ts()}: {message}\n")


def _is_under(path, root):
    try:
        path.relative_to(root)
        return True
    except ValueError:
        return False
