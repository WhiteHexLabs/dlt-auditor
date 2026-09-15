"""Workspace layout tests (plan sections 13-16)."""

from __future__ import annotations

from pathlib import Path

from conftest import REPO_ROOT, host_runner, run_cli, scaffold_host_suite


def test_suite_lives_under_target_work_dir(target_repo: Path, tmp_path: Path) -> None:
    suite_dir = scaffold_host_suite(target_repo, "ws-suite", ["monad-c4"], tmp_path)
    assert suite_dir.is_dir()
    for child in ("suite-manifest.json", "README.md", "state", "design-workspaces", "design-runs", "logs"):
        assert (suite_dir / child).exists(), child
    assert (suite_dir / "state" / "work-queue.json").is_file()


def test_no_stray_artifacts_in_target_root(target_repo: Path, tmp_path: Path) -> None:
    before = {p.name for p in target_repo.iterdir()}
    scaffold_host_suite(target_repo, "clean-suite", ["monad-c4"], tmp_path)
    after = {p.name for p in target_repo.iterdir()}
    assert after - before == {".dlt-auditor-work"}


def test_gitignore_untouched_by_default(target_repo: Path, tmp_path: Path) -> None:
    original = (target_repo / ".gitignore").read_text(encoding="utf-8")
    result = run_cli(
        "python3",
        REPO_ROOT / "bin" / "run-blind-suite",
        "--repo",
        target_repo,
        "--suite-name",
        "git-hint-suite",
        "--design",
        "monad-c4",
        "--execution-backend",
        "host",
        cwd=tmp_path,
        check=False,
    )
    assert "Hint: consider adding `.dlt-auditor-work/`" in result.stdout
    assert (target_repo / ".gitignore").read_text(encoding="utf-8") == original


def test_gitignore_updated_when_opted_in(target_repo: Path, tmp_path: Path) -> None:
    run_cli(
        "python3",
        REPO_ROOT / "bin" / "run-blind-suite",
        "--repo",
        target_repo,
        "--suite-name",
        "git-write-suite",
        "--design",
        "monad-c4",
        "--execution-backend",
        "host",
        "--update-gitignore",
        cwd=tmp_path,
    )
    content = (target_repo / ".gitignore").read_text(encoding="utf-8")
    assert ".dlt-auditor-work/" in content
    assert "node_modules" in content
    # Idempotent: a second run must not duplicate the entry.
    run_cli(
        "python3",
        REPO_ROOT / "bin" / "run-blind-suite",
        "--repo",
        target_repo,
        "--suite-name",
        "git-write-suite",
        "--design",
        "monad-c4",
        "--execution-backend",
        "host",
        "--force",
        "--update-gitignore",
        cwd=tmp_path,
    )
    assert (target_repo / ".gitignore").read_text(encoding="utf-8").count(".dlt-auditor-work/") == 1


def test_custom_work_root(target_repo: Path, tmp_path: Path) -> None:
    work_root = tmp_path / "elsewhere"
    run_cli(
        "python3",
        REPO_ROOT / "bin" / "run-blind-suite",
        "--repo",
        target_repo,
        "--suite-name",
        "moved-suite",
        "--design",
        "monad-c4",
        "--execution-backend",
        "host",
        "--work-root",
        work_root,
        cwd=tmp_path,
    )
    assert (work_root / "moved-suite" / "suite-manifest.json").is_file()


def test_audit_run_inside_design_runs(target_repo: Path, tmp_path: Path) -> None:
    suite_dir = scaffold_host_suite(target_repo, "layout-suite", ["monad-c4"], tmp_path)
    audit_run = suite_dir / "design-runs" / "01-monad-c4"
    assert (audit_run / "agent-prompts").is_dir()
    assert (audit_run / "item-manifest.json").is_file()
    status = host_runner(suite_dir, "status")
    assert '"audit_run"' in status.stdout


def test_single_design_defaults_to_target_work_root(target_repo: Path, tmp_path: Path) -> None:
    run_cli(
        str(REPO_ROOT / "designs" / "monad-c4" / "bin" / "dlt-ai-audit-system"),
        target_repo,
        "--run-name",
        "solo-run",
    )
    run_dir = target_repo / ".dlt-auditor-work" / "runs" / "solo-run"
    assert (run_dir / "agent-prompts" / "00-protocol-mapper.md").is_file()
    # --runs-dir still overrides for callers that want a custom layout.
    old_runs = tmp_path / "old-runs"
    run_cli(
        str(REPO_ROOT / "designs" / "monad-c4" / "bin" / "dlt-ai-audit-system"),
        target_repo,
        "--run-name",
        "legacy-run",
        "--runs-dir",
        old_runs,
    )
    assert (old_runs / "legacy-run" / "agent-prompts").is_dir()
