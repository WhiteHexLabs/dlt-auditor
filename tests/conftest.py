"""Shared fixtures for dlt-auditor tests."""

from __future__ import annotations

import os
import subprocess
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]


def run_cli(*args: str, cwd: Path | None = None, check: bool = True) -> subprocess.CompletedProcess:
    return subprocess.run(
        [str(a) for a in args],
        cwd=str(cwd or REPO_ROOT),
        capture_output=True,
        text=True,
        check=check,
    )


@pytest.fixture
def target_repo(tmp_path: Path) -> Path:
    repo = tmp_path / "target-repo"
    repo.mkdir()
    run_cli("git", "init", "-q", cwd=repo)
    (repo / "README.md").write_text("# target repo\n", encoding="utf-8")
    (repo / "main.rs").write_text("fn main() {}\n", encoding="utf-8")
    (repo / ".gitignore").write_text("node_modules\n", encoding="utf-8")
    run_cli("git", "add", ".", cwd=repo)
    run_cli(
        "git", "-c", "user.email=test@test", "-c", "user.name=test", "commit", "-qm", "init", cwd=repo
    )
    return repo


class FakeCli:
    """Fake codex/claude/zcode executables on PATH that record every invocation."""

    def __init__(self, bindir: Path, marker: Path) -> None:
        self.bindir = bindir
        self.marker = marker

    @property
    def invocations(self) -> list[str]:
        if not self.marker.is_file():
            return []
        return [line for line in self.marker.read_text(encoding="utf-8").splitlines() if line.strip()]

    def count(self, name: str) -> int:
        return sum(1 for line in self.invocations if line.startswith(name))


@pytest.fixture
def fake_cli(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> FakeCli:
    bindir = tmp_path / "fakebin"
    bindir.mkdir()
    marker = tmp_path / "cli-invocations.log"
    for name in ("codex", "claude", "zcode"):
        script = bindir / name
        script.write_text(
            f"""#!/usr/bin/env bash
echo "{name} $*" >> "{marker}"
exit 0
""",
            encoding="utf-8",
        )
        script.chmod(0o755)
    monkeypatch.setenv("PATH", f"{bindir}{os.pathsep}{os.environ.get('PATH', '')}")
    return FakeCli(bindir, marker)


def scaffold_host_suite(target: Path, suite: str, designs: list[str], tmp: Path) -> Path:
    args = [
        "python3",
        str(REPO_ROOT / "bin" / "run-blind-suite"),
        "--repo",
        str(target),
        "--suite-name",
        suite,
    ]
    for design in designs:
        args.extend(["--design", design])
    args.extend(["--execution-backend", "host"])
    run_cli(*args, cwd=tmp)
    return target / ".dlt-auditor-work" / suite


def host_runner(suite_dir: Path, *args: str) -> subprocess.CompletedProcess:
    return run_cli("python3", str(REPO_ROOT / "bin" / "host-runner"), str(suite_dir), *args, check=False)


def write_minimal_mapper_outputs(audit_run: Path) -> None:
    (audit_run / "repo-context.md").write_text("# Repo Context\n\nmapped\n", encoding="utf-8")
    (audit_run / "feature-coverage.md").write_text("# Feature Coverage\n\nrows\n", encoding="utf-8")
    (audit_run / "verification-log.md").write_text("# Verification Log\n\nnone\n", encoding="utf-8")
