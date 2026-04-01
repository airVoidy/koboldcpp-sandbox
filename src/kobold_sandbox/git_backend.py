from __future__ import annotations

import os
import shutil
import subprocess
from pathlib import Path


class GitError(RuntimeError):
    pass


def resolve_git() -> str:
    candidates = [
        os.environ.get("KOBOLD_SANDBOX_GIT"),
        r"C:\Program Files\Microsoft Visual Studio\2022\Community\Common7\IDE\CommonExtensions\Microsoft\TeamFoundation\Team Explorer\Git\cmd\git.exe",
        r"C:\Program Files (x86)\Microsoft Visual Studio\2019\BuildTools\Common7\IDE\CommonExtensions\Microsoft\TeamFoundation\Team Explorer\Git\cmd\git.exe",
        r"C:\Program Files\Git\cmd\git.exe",
        shutil.which("git"),
    ]
    for candidate in candidates:
        if candidate and Path(candidate).exists():
            return str(candidate)
    raise GitError("Git executable was not found.")


class GitBackend:
    def __init__(self, repo_dir: Path):
        self.repo_dir = repo_dir
        self.git = resolve_git()

    def run(self, *args: str, cwd: Path | None = None) -> str:
        import sys
        kwargs: dict = dict(
            cwd=str(cwd or self.repo_dir),
            capture_output=True,
            text=True,
            check=False,
        )
        if sys.platform == 'win32':
            kwargs['creationflags'] = subprocess.CREATE_NO_WINDOW
        result = subprocess.run([self.git, *args], **kwargs)
        if result.returncode != 0:
            raise GitError(result.stderr.strip() or result.stdout.strip() or f"git {' '.join(args)} failed")
        return result.stdout.strip()

    def ensure_repo(self) -> None:
        if (self.repo_dir / ".git").exists():
            return
        self.repo_dir.mkdir(parents=True, exist_ok=True)
        self.run("init", "-b", "main")
        self.run("config", "user.name", "Kobold Sandbox")
        self.run("config", "user.email", "sandbox@local")
        readme = self.repo_dir / "README.md"
        readme.write_text("# Sandbox Root\n\nShared git history for hypothesis branches.\n", encoding="utf-8")
        self.run("add", "README.md")
        self.run("commit", "-m", "Initial sandbox commit")
        self.run("checkout", "--detach")

    def current_branch(self) -> str:
        return self.run("branch", "--show-current")

    def create_branch(self, new_branch: str, from_branch: str) -> None:
        self.run("branch", new_branch, from_branch)

    def add_worktree(self, path: Path, branch: str) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        self.run("worktree", "add", str(path), branch)

    def remove_worktree(self, path: Path) -> None:
        if path.exists():
            self.run("worktree", "remove", "--force", str(path))

    def commit_all(self, worktree: Path, message: str) -> str:
        self.run("add", "-A", cwd=worktree)
        status = self.run("status", "--short", cwd=worktree)
        if not status.strip():
            return ""
        try:
            self.run("commit", "-m", message, cwd=worktree)
        except GitError as e:
            # "nothing to commit" is not a real error
            if "nothing to commit" in str(e):
                return ""
            raise
        return self.run("rev-parse", "HEAD", cwd=worktree)
