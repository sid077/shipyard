"""Project and git plumbing.

Git is owned by the orchestrator. Roles edit files; Python branches, commits,
merges and reverts. That split is deliberate: agents are good at writing code
and bad at repository surgery, and a botched merge is far more expensive to
recover from than a botched function.
"""

from __future__ import annotations

import re
import shutil
import subprocess
from dataclasses import dataclass, field
from pathlib import Path

TRUNK = "trunk"


class GitError(RuntimeError):
    def __init__(self, args: list[str], code: int, out: str, err: str) -> None:
        super().__init__(f"git {' '.join(args)} failed ({code}): {err.strip() or out.strip()}")
        self.args_list = args
        self.code = code
        self.stdout = out
        self.stderr = err


@dataclass
class Git:
    repo: Path

    def run(self, *args: str, check: bool = True) -> subprocess.CompletedProcess[str]:
        proc = subprocess.run(
            ["git", *args],
            cwd=str(self.repo),
            capture_output=True,
            text=True,
        )
        if check and proc.returncode != 0:
            raise GitError(list(args), proc.returncode, proc.stdout, proc.stderr)
        return proc

    def out(self, *args: str) -> str:
        return self.run(*args).stdout.strip()

    # -- setup -------------------------------------------------------------

    def init(self, branch: str = TRUNK) -> None:
        self.repo.mkdir(parents=True, exist_ok=True)
        self.run("init", "-q", "-b", branch)
        self.run("config", "user.name", "Shipyard")
        self.run("config", "user.email", "shipyard@localhost")

    def commit_all(self, message: str, allow_empty: bool = False) -> str | None:
        self.run("add", "-A")
        args = ["commit", "-q", "-m", message]
        if allow_empty:
            args.append("--allow-empty")
        proc = self.run(*args, check=False)
        if proc.returncode != 0:
            if "nothing to commit" in (proc.stdout + proc.stderr):
                return None
            raise GitError(args, proc.returncode, proc.stdout, proc.stderr)
        return self.head()

    def head(self) -> str:
        return self.out("rev-parse", "HEAD")

    def current_branch(self) -> str:
        return self.out("rev-parse", "--abbrev-ref", "HEAD")

    def is_dirty(self) -> bool:
        return bool(self.out("status", "--porcelain"))

    def diff(self, base: str, head: str = "HEAD", stat: bool = False) -> str:
        args = ["diff", f"{base}...{head}"]
        if stat:
            args.append("--stat")
        return self.out(*args)

    def changed_files(self, base: str, head: str = "HEAD") -> list[str]:
        out = self.out("diff", "--name-only", f"{base}...{head}")
        return [line for line in out.splitlines() if line.strip()]


@dataclass
class MergeResult:
    ok: bool
    conflicts: list[str] = field(default_factory=list)
    message: str = ""


def _branch_for(ticket_id: str) -> str:
    safe = re.sub(r"[^A-Za-z0-9._-]+", "-", ticket_id).strip("-").lower()
    return f"ticket/{safe or 'unnamed'}"


@dataclass
class AppRepo:
    """The generated app's git repository, plus its per-ticket worktrees."""

    root: Path
    trunk: str = TRUNK

    @property
    def git(self) -> Git:
        return Git(self.root)

    @property
    def worktrees_dir(self) -> Path:
        return self.root.parent / "worktrees"

    @classmethod
    def from_template(cls, template_dir: Path, dest: Path) -> "AppRepo":
        """Copy the golden template into `dest` and make it the trunk commit."""
        template_dir = Path(template_dir)
        if not template_dir.is_dir():
            raise FileNotFoundError(f"template not found: {template_dir}")
        dest = Path(dest)
        if dest.exists():
            raise FileExistsError(f"app directory already exists: {dest}")
        shutil.copytree(
            template_dir,
            dest,
            ignore=shutil.ignore_patterns(
                "node_modules", ".git", ".expo", "dist", "__pycache__", "*.log"
            ),
        )
        repo = cls(dest)
        git = repo.git
        git.init(repo.trunk)
        git.commit_all("chore: scaffold from shipyard expo-app template")
        return repo

    @classmethod
    def open(cls, root: Path) -> "AppRepo":
        root = Path(root)
        if not (root / ".git").exists():
            raise FileNotFoundError(f"no git repository at {root}")
        return cls(root)

    # -- worktrees ---------------------------------------------------------

    def worktree_path(self, ticket_id: str) -> Path:
        return self.worktrees_dir / re.sub(r"[^A-Za-z0-9._-]+", "-", ticket_id).lower()

    def add_worktree(self, ticket_id: str) -> Path:
        """Create an isolated checkout of trunk for one ticket."""
        path = self.worktree_path(ticket_id)
        branch = _branch_for(ticket_id)
        if path.exists():
            self.remove_worktree(ticket_id)
        path.parent.mkdir(parents=True, exist_ok=True)
        git = self.git
        git.run("branch", "-D", branch, check=False)
        git.run("worktree", "add", "-q", "-b", branch, str(path), self.trunk)
        return path

    def remove_worktree(self, ticket_id: str, delete_branch: bool = False) -> None:
        path = self.worktree_path(ticket_id)
        git = self.git
        git.run("worktree", "remove", "--force", str(path), check=False)
        if path.exists():
            shutil.rmtree(path, ignore_errors=True)
        git.run("worktree", "prune", check=False)
        if delete_branch:
            git.run("branch", "-D", _branch_for(ticket_id), check=False)

    def commit_worktree(self, ticket_id: str, message: str) -> str | None:
        return Git(self.worktree_path(ticket_id)).commit_all(message)

    def worktree_diff(self, ticket_id: str) -> str:
        return Git(self.worktree_path(ticket_id)).diff(self.trunk)

    def worktree_changed_files(self, ticket_id: str) -> list[str]:
        return Git(self.worktree_path(ticket_id)).changed_files(self.trunk)

    # -- integration -------------------------------------------------------

    def merge_ticket(self, ticket_id: str) -> MergeResult:
        """Merge a ticket branch into trunk. On conflict, leave the merge open
        inside the ticket's worktree so a `dev` role can resolve it as a code
        task rather than a git task."""
        branch = _branch_for(ticket_id)
        git = self.git
        proc = git.run(
            "merge", "--no-ff", "-m", f"merge({ticket_id}): integrate", branch, check=False
        )
        if proc.returncode == 0:
            return MergeResult(True, message=git.head())
        conflicts = [
            line for line in git.out("diff", "--name-only", "--diff-filter=U").splitlines()
        ]
        git.run("merge", "--abort", check=False)
        # Replay the conflict inside the worktree, where the dev role works.
        wt = Git(self.worktree_path(ticket_id))
        wt.run("merge", "--no-ff", "-m", f"merge trunk into {ticket_id}", self.trunk, check=False)
        return MergeResult(
            False,
            conflicts=conflicts,
            message=(proc.stderr or proc.stdout).strip(),
        )

    def revert_last_merge(self) -> None:
        """Undo the most recent merge commit on trunk."""
        git = self.git
        git.run("reset", "--hard", "HEAD~1")


def create_project(projects_dir: Path, slug: str) -> Path:
    project_dir = Path(projects_dir) / slug
    for sub in ("research", "product", "design", "arch", "backlog", "qa", "release", "inbox"):
        (project_dir / sub).mkdir(parents=True, exist_ok=True)
    return project_dir
