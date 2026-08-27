from pathlib import Path

import pytest

from shipyard.workspace import AppRepo, Git, create_project


@pytest.fixture()
def template(tmp_path: Path) -> Path:
    src = tmp_path / "template"
    (src / "src").mkdir(parents=True)
    (src / "package.json").write_text('{"name":"demo"}\n')
    (src / "src" / "app.ts").write_text("export const a = 1;\n")
    (src / "src" / "shared.ts").write_text("export const shared = 'base';\n")
    (src / "node_modules").mkdir()
    (src / "node_modules" / "junk.js").write_text("nope\n")
    return src


def test_from_template_ignores_node_modules_and_commits(template: Path, tmp_path: Path):
    repo = AppRepo.from_template(template, tmp_path / "proj" / "app")
    assert (repo.root / "package.json").is_file()
    assert not (repo.root / "node_modules").exists()
    assert repo.git.current_branch() == "trunk"
    assert not repo.git.is_dirty()


def test_worktrees_are_isolated_and_merge_cleanly(template: Path, tmp_path: Path):
    repo = AppRepo.from_template(template, tmp_path / "proj" / "app")

    a = repo.add_worktree("T-01")
    b = repo.add_worktree("T-02")
    assert a != b and a.is_dir() and b.is_dir()

    (a / "src" / "feature_a.ts").write_text("export const a = 'A';\n")
    (b / "src" / "feature_b.ts").write_text("export const b = 'B';\n")
    # Each worktree sees only its own change.
    assert not (b / "src" / "feature_a.ts").exists()

    repo.commit_worktree("T-01", "feat(T-01): a")
    repo.commit_worktree("T-02", "feat(T-02): b")

    assert repo.worktree_changed_files("T-01") == ["src/feature_a.ts"]

    assert repo.merge_ticket("T-01").ok
    assert repo.merge_ticket("T-02").ok
    assert (repo.root / "src" / "feature_a.ts").is_file()
    assert (repo.root / "src" / "feature_b.ts").is_file()


def test_conflicting_merge_leaves_trunk_clean_and_replays_in_worktree(
    template: Path, tmp_path: Path
):
    repo = AppRepo.from_template(template, tmp_path / "proj" / "app")
    trunk_before = repo.git.head()

    repo.add_worktree("T-01")
    repo.add_worktree("T-02")
    (repo.worktree_path("T-01") / "src" / "shared.ts").write_text("export const shared = 'one';\n")
    (repo.worktree_path("T-02") / "src" / "shared.ts").write_text("export const shared = 'two';\n")
    repo.commit_worktree("T-01", "feat(T-01)")
    repo.commit_worktree("T-02", "feat(T-02)")

    assert repo.merge_ticket("T-01").ok
    result = repo.merge_ticket("T-02")

    assert not result.ok
    assert "src/shared.ts" in result.conflicts
    # Trunk must be untouched and clean after a failed merge.
    assert not repo.git.is_dirty()
    assert repo.git.head() != trunk_before  # T-01 landed
    # The conflict is now live in T-02's worktree for a dev role to resolve.
    conflicted = (repo.worktree_path("T-02") / "src" / "shared.ts").read_text()
    assert "<<<<<<<" in conflicted


def test_revert_last_merge_restores_trunk(template: Path, tmp_path: Path):
    repo = AppRepo.from_template(template, tmp_path / "proj" / "app")
    before = repo.git.head()
    repo.add_worktree("T-01")
    (repo.worktree_path("T-01") / "src" / "x.ts").write_text("export const x = 1;\n")
    repo.commit_worktree("T-01", "feat(T-01)")
    assert repo.merge_ticket("T-01").ok
    assert (repo.root / "src" / "x.ts").is_file()

    repo.revert_last_merge()
    assert repo.git.head() == before
    assert not (repo.root / "src" / "x.ts").exists()


def test_remove_worktree_is_idempotent(template: Path, tmp_path: Path):
    repo = AppRepo.from_template(template, tmp_path / "proj" / "app")
    repo.add_worktree("T-01")
    repo.remove_worktree("T-01", delete_branch=True)
    repo.remove_worktree("T-01", delete_branch=True)
    assert not repo.worktree_path("T-01").exists()


def test_create_project_makes_the_standard_tree(tmp_path: Path):
    p = create_project(tmp_path / "projects", "demo")
    for sub in ("research", "product", "design", "arch", "backlog", "qa", "release", "inbox"):
        assert (p / sub).is_dir()


def test_linked_dependencies_never_reach_trunk(template: Path, tmp_path: Path):
    """A symlinked node_modules must not be committed.

    `node_modules/` with a trailing slash matches a directory but not a symlink,
    so relying on the app's .gitignore would let a worktree commit the link -
    and the next merge would replace trunk's real dependencies with a link
    pointing at itself.
    """
    repo = AppRepo.from_template(template, tmp_path / "proj" / "app")
    deps = repo.root / "node_modules"
    (deps / "left-pad").mkdir(parents=True)
    (deps / "left-pad" / "index.js").write_text("module.exports = 1;\n")

    repo.add_worktree("T-01")
    repo.link_dependencies("T-01")
    worktree = repo.worktree_path("T-01")
    assert (worktree / "node_modules" / "left-pad" / "index.js").is_file()

    (worktree / "src" / "feature.ts").write_text("export const f = 1;\n")
    repo.commit_worktree("T-01", "feat(T-01)")

    # The link is not part of the change.
    assert "node_modules" not in repo.worktree_changed_files("T-01")

    assert repo.merge_ticket("T-01").ok
    assert deps.is_dir() and not deps.is_symlink(), "trunk lost its real dependencies"
    assert (deps / "left-pad" / "index.js").is_file()


def test_link_dependencies_is_idempotent_and_skips_a_missing_source(
    template: Path, tmp_path: Path
):
    repo = AppRepo.from_template(template, tmp_path / "proj" / "app")
    repo.add_worktree("T-01")

    repo.link_dependencies("T-01")  # nothing to link yet
    assert not (repo.worktree_path("T-01") / "node_modules").exists()

    (repo.root / "node_modules").mkdir()
    repo.link_dependencies("T-01")
    repo.link_dependencies("T-01")
    assert (repo.worktree_path("T-01") / "node_modules").is_symlink()
