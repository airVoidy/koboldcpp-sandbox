from __future__ import annotations

import json
from pathlib import Path

from .kobold_client import KoboldClient
from .models import RunResult
from .storage import Sandbox


DEFAULT_SYSTEM_PROMPT = """You are an analysis agent working inside a local hypothesis sandbox.
Use the provided node notes, tables, and workspace files.
Prefer explicit reasoning artifacts:
- update or propose tables when comparing hypotheses
- keep tentative branches separate
- state contradictions clearly
- end with concrete next actions
"""


def _read_text(path: Path, max_chars: int = 12000) -> str:
    try:
        text = path.read_text(encoding="utf-8")
    except UnicodeDecodeError:
        return f"[binary or non-utf8 omitted] {path.name}"
    if len(text) > max_chars:
        return text[:max_chars] + "\n...[truncated]"
    return text


def build_prompt(sandbox: Sandbox, node_id: str, task: str) -> str:
    sections = [f"# Task\n{task}", "# Node Context"]
    for path in sandbox.list_context_files(node_id):
        rel = path.relative_to(sandbox.root)
        sections.append(f"## File: {rel}\n{_read_text(path)}")
    return "\n\n".join(sections)


def run_task(
    sandbox: Sandbox,
    node_id: str,
    task: str,
    model: str | None = None,
    system_prompt: str = DEFAULT_SYSTEM_PROMPT,
    commit: bool = False,
) -> RunResult:
    state = sandbox.load_state()
    client = KoboldClient(state.kobold_url)
    prompt = build_prompt(sandbox, node_id, task)
    raw = client.chat(prompt=prompt, model=model or state.default_model, system_prompt=system_prompt)
    text = client.extract_text(raw)
    run_dir = sandbox.runs_dir(node_id)
    run_dir.mkdir(exist_ok=True)
    run_index = len(list(run_dir.glob("run-*.md"))) + 1
    output_path = run_dir / f"run-{run_index:03d}.md"
    output_path.write_text(f"# Task\n\n{task}\n\n# Response\n\n{text}\n", encoding="utf-8")
    if commit:
        sandbox.git.commit_all(sandbox.workspace_for(node_id), f"Sandbox commit after run {run_index}")
    return RunResult(
        node_id=node_id,
        prompt=prompt,
        response_text=text,
        raw_response=raw,
        saved_to=str(output_path),
    )


def export_graph(sandbox: Sandbox) -> dict:
    state = sandbox.load_state()
    return {
        "sandbox_name": state.sandbox_name,
        "active_node_id": state.active_node_id,
        "nodes": [
            {
                "id": node.id,
                "title": node.title,
                "parent_id": node.parent_id,
                "branch": node.branch,
                "summary": node.summary,
                "tags": node.tags,
                "workspace": str(sandbox.workspace_for(node.id)),
                "notes": str(sandbox.notes_path(node.id)),
            }
            for node in state.nodes.values()
        ],
    }


def export_graph_json(sandbox: Sandbox) -> str:
    return json.dumps(export_graph(sandbox), ensure_ascii=False, indent=2)
