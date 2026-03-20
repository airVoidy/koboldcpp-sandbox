from __future__ import annotations

import json
import re
from pathlib import Path
from typing import TYPE_CHECKING

from .git_backend import GitBackend
from .models import Node, SandboxState, utc_now
from .outcomes import BranchOutcome, OutcomeWriter, StepSnapshot

if TYPE_CHECKING:
    from .assertions import AtomicClaim


def slugify(value: str) -> str:
    slug = re.sub(r"[^a-zA-Z0-9]+", "-", value.strip().lower()).strip("-")
    return slug or "node"


class Sandbox:
    def __init__(self, root: Path):
        self.root = root.resolve()
        self.meta_dir = self.root / ".sandbox"
        self.repo_dir = self.meta_dir / "repo"
        self.nodes_dir = self.root / "nodes"
        self.state_path = self.meta_dir / "state.json"
        self.git = GitBackend(self.repo_dir)

    def exists(self) -> bool:
        return self.state_path.exists()

    def init(self, sandbox_name: str, kobold_url: str, default_model: str | None = None, root_title: str = "root") -> SandboxState:
        self.meta_dir.mkdir(parents=True, exist_ok=True)
        self.nodes_dir.mkdir(parents=True, exist_ok=True)
        self.git.ensure_repo()
        root_node = Node(id="root", title=root_title, branch="main")
        workspace = self.workspace_for(root_node.id)
        if not workspace.exists():
            self.git.add_worktree(workspace, root_node.branch)
        self._ensure_node_scaffold(root_node.id, root_node.title, parent_id=None)
        state = SandboxState(
            sandbox_name=sandbox_name,
            kobold_url=kobold_url.rstrip("/"),
            default_model=default_model,
            active_node_id=root_node.id,
            nodes={root_node.id: root_node},
        )
        self.save_state(state)
        return state

    def load_state(self) -> SandboxState:
        return SandboxState.model_validate_json(self.state_path.read_text(encoding="utf-8"))

    def save_state(self, state: SandboxState) -> None:
        self.state_path.write_text(json.dumps(state.model_dump(), ensure_ascii=False, indent=2), encoding="utf-8")

    def node_dir(self, node_id: str) -> Path:
        return self.nodes_dir / node_id

    def workspace_for(self, node_id: str) -> Path:
        return self.node_dir(node_id) / "workspace"

    def notes_path(self, node_id: str) -> Path:
        return self.node_dir(node_id) / "notes.md"

    def tables_dir(self, node_id: str) -> Path:
        return self.node_dir(node_id) / "tables"

    def runs_dir(self, node_id: str) -> Path:
        return self.node_dir(node_id) / "runs"

    def analysis_dir(self, node_id: str) -> Path:
        return self.node_dir(node_id) / "analysis"

    def _ensure_node_scaffold(self, node_id: str, title: str, parent_id: str | None) -> None:
        node_dir = self.node_dir(node_id)
        node_dir.mkdir(parents=True, exist_ok=True)
        self.tables_dir(node_id).mkdir(exist_ok=True)
        self.runs_dir(node_id).mkdir(exist_ok=True)
        notes = self.notes_path(node_id)
        if not notes.exists():
            parent_line = parent_id if parent_id else "none"
            notes.write_text(
                f"# {title}\n\nParent: {parent_line}\n\n## Goal\n\n## Hypotheses\n\n## Findings\n",
                encoding="utf-8",
            )
        table_readme = self.tables_dir(node_id) / "README.md"
        if not table_readme.exists():
            table_readme.write_text("Store CSV or Markdown tables for this branch.\n", encoding="utf-8")
        self.analysis_dir(node_id).mkdir(exist_ok=True)

    def _unique_node_id(self, preferred_id: str) -> str:
        state = self.load_state()
        node_id = preferred_id
        suffix = 2
        while node_id in state.nodes:
            node_id = f"{preferred_id}-{suffix}"
            suffix += 1
        return node_id

    def create_node(
        self,
        parent_id: str,
        title: str,
        summary: str = "",
        tags: list[str] | None = None,
        *,
        preferred_node_id: str | None = None,
        branch_name: str | None = None,
        kind: str = "generic",
        claim_id: str | None = None,
        assumptions: list[str] | None = None,
        consequences: list[str] | None = None,
    ) -> Node:
        state = self.load_state()
        if parent_id not in state.nodes:
            raise KeyError(f"Unknown parent node: {parent_id}")
        parent = state.nodes[parent_id]
        base_slug = preferred_node_id or slugify(title)
        node_id = self._unique_node_id(base_slug)
        branch = branch_name or f"hyp/{node_id}"
        self.git.create_branch(branch, parent.branch)
        workspace = self.workspace_for(node_id)
        self.git.add_worktree(workspace, branch)
        self._ensure_node_scaffold(node_id, title, parent_id)
        node = Node(
            id=node_id,
            title=title,
            branch=branch,
            parent_id=parent_id,
            summary=summary,
            kind=kind,
            claim_id=claim_id,
            assumptions=assumptions or [],
            consequences=consequences or [],
            tags=tags or [],
        )
        state.nodes[node.id] = node
        state.active_node_id = node.id
        self.save_state(state)
        return node

    def create_claim_node(
        self,
        parent_id: str,
        claim: AtomicClaim,
        *,
        title: str | None = None,
        summary: str = "",
        tags: list[str] | None = None,
    ) -> Node:
        node = self.create_node(
            parent_id=parent_id,
            title=title or claim.title,
            summary=summary or claim.formal_text or claim.title,
            tags=tags or [claim.status.value, claim.phase.value],
            preferred_node_id=claim.branch_slug(),
            branch_name=f"hyp/{claim.branch_slug()}",
            kind="claim",
            claim_id=claim.claim_id,
            assumptions=[claim.claim_id],
            consequences=list(claim.consequences),
        )
        self.update_notes(node.id, self._claim_notes(node=node, claim=claim))
        return node

    def _claim_notes(self, node: Node, claim: AtomicClaim) -> str:
        value_range = ""
        if claim.value_range:
            if claim.value_range.values:
                value_range = ", ".join(claim.value_range.values)
            else:
                value_range = f"{claim.value_range.lower}..{claim.value_range.upper}"
        consequences = "\n".join(f"- {item}" for item in claim.consequences) or "-"
        variables = ", ".join(claim.variables) or "-"
        source_refs = ", ".join(claim.source_refs) or "-"
        atomic_code = claim.python_code or "# TODO: attach atomic code"
        return (
            f"# {node.title}\n\n"
            f"Parent: {node.parent_id}\n\n"
            f"## Claim\n\n"
            f"- claim_id: {claim.claim_id}\n"
            f"- status: {claim.status.value}\n"
            f"- phase: {claim.phase.value}\n"
            f"- variables: {variables}\n"
            f"- source_refs: {source_refs}\n"
            f"- value_range: {value_range or '-'}\n\n"
            f"## Constraint Spec\n\n"
            f"{claim.formal_constraint.to_python_expr() if claim.formal_constraint else '-'}\n\n"
            f"## Formalization\n\n"
            f"{claim.formal_text or '-'}\n\n"
            f"## Atomic Python\n\n"
            f"```python\n{atomic_code}\n```\n\n"
            f"## Consequences\n\n"
            f"{consequences}\n"
        )

    def set_active_node(self, node_id: str) -> Node:
        state = self.load_state()
        node = state.nodes[node_id]
        state.active_node_id = node.id
        node.updated_at = utc_now()
        state.nodes[node_id] = node
        self.save_state(state)
        return node

    def update_notes(self, node_id: str, content: str) -> None:
        self.notes_path(node_id).write_text(content, encoding="utf-8")
        state = self.load_state()
        node = state.nodes[node_id]
        node.updated_at = utc_now()
        state.nodes[node_id] = node
        self.save_state(state)

    def write_table(self, node_id: str, name: str, content: str) -> Path:
        path = self.tables_dir(node_id) / name
        path.write_text(content, encoding="utf-8")
        return path

    def outcome_writer(self, node_id: str) -> OutcomeWriter:
        return OutcomeWriter(self.node_dir(node_id))

    def write_branch_outcome(self, node_id: str, outcome: BranchOutcome) -> Path:
        return self.outcome_writer(node_id).write_branch_outcome(outcome)

    def write_step_snapshot(self, node_id: str, snapshot: StepSnapshot) -> Path:
        return self.outcome_writer(node_id).write_step_snapshot(snapshot)

    def list_context_files(self, node_id: str) -> list[Path]:
        paths = [self.notes_path(node_id)]
        paths.extend(sorted(self.tables_dir(node_id).glob("*")))
        workspace = self.workspace_for(node_id)
        for path in sorted(workspace.rglob("*")):
            if ".git" in path.parts or path.is_dir():
                continue
            paths.append(path)
        return paths
