"""Git version control adapter for DataStore.

Wraps GitBackend to provide commit/branch/diff/log operations
on the datastore workspace directory.
"""

from __future__ import annotations

from pathlib import Path

from ..git_backend import GitBackend
from .schema import CommitInfo


class DataStoreGit:
    def __init__(self, repo_dir: Path, workspace_dir: Path):
        self.git = GitBackend(repo_dir)
        self.workspace = workspace_dir

    def init(self) -> None:
        """Initialize git repo and link workspace."""
        self.workspace.mkdir(parents=True, exist_ok=True)
        if not (self.workspace / ".git").exists():
            # Init repo directly in workspace (simpler than worktree for single workspace)
            self.git = GitBackend(self.workspace)
            self.git.ensure_repo()

    def commit_all(self, message: str) -> str:
        """Stage all changes and commit. Returns commit hash or empty string if nothing to commit."""
        return self.git.commit_all(self.workspace, message)

    def log(self, limit: int = 20) -> list[CommitInfo]:
        """Parse git log into CommitInfo objects."""
        try:
            sep = "---COMMIT---"
            fmt = f"%H{sep}%h{sep}%s{sep}%aI{sep}%an"
            raw = self.git.run(
                "log", f"--format={fmt}", f"-{limit}",
                cwd=self.workspace,
            )
        except Exception:
            return []

        commits = []
        for line in raw.strip().splitlines():
            parts = line.split(sep)
            if len(parts) >= 5:
                commits.append(CommitInfo(
                    hash=parts[0],
                    short_hash=parts[1],
                    message=parts[2],
                    timestamp=parts[3],
                    author=parts[4],
                ))
        return commits

    def diff(self, from_ref: str | None = None, to_ref: str | None = None) -> str:
        """Get diff between refs, or working tree diff if no args."""
        args = ["diff"]
        if from_ref and to_ref:
            args.append(f"{from_ref}..{to_ref}")
        elif from_ref:
            args.append(from_ref)
        try:
            return self.git.run(*args, cwd=self.workspace)
        except Exception:
            return ""

    def create_branch(self, name: str) -> None:
        current = self.current_branch()
        self.git.run("branch", name, current, cwd=self.workspace)

    def checkout(self, ref: str) -> None:
        self.git.run("checkout", ref, cwd=self.workspace)

    def list_branches(self) -> list[str]:
        raw = self.git.run("branch", "--list", "--format=%(refname:short)", cwd=self.workspace)
        return [b.strip() for b in raw.splitlines() if b.strip()]

    def current_branch(self) -> str:
        return self.git.run("branch", "--show-current", cwd=self.workspace)

    def reset_to(self, ref: str) -> None:
        """Reset workspace to a specific commit (destructive)."""
        self.git.run("checkout", ref, "--", ".", cwd=self.workspace)

    def tag(self, name: str) -> None:
        self.git.run("tag", name, cwd=self.workspace)
