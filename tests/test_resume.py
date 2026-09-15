"""Resume semantics for host and CLI executions (plan sections 17-18, 25-27)."""

from __future__ import annotations

import json
from pathlib import Path

from conftest import REPO_ROOT, host_runner, run_cli, scaffold_host_suite, write_minimal_mapper_outputs

RUNNER = REPO_ROOT / "designs" / "monad-c4" / "bin" / "run-parallel-workers"


def _reach_scans(suite_dir: Path, audit_run: Path) -> None:
    host_runner(suite_dir, "next", "--limit", "1")
    write_minimal_mapper_outputs(audit_run)
    host_runner(suite_dir, "complete", "mapper/00-protocol-mapper")
    host_runner(suite_dir, "advance")
    host_runner(suite_dir, "next", "--limit", "1")
    (audit_run / "corpus-match-index.md").write_text("indexed\n", encoding="utf-8")
    host_runner(suite_dir, "complete", "corpus/05-corpus-pattern-search")
    host_runner(suite_dir, "advance")


def test_host_resume_resets_running_keeps_completed(target_repo: Path, tmp_path: Path) -> None:
    suite_dir = scaffold_host_suite(target_repo, "resume-suite", ["monad-c4"], tmp_path)
    audit_run = suite_dir / "design-runs" / "01-monad-c4"
    _reach_scans(suite_dir, audit_run)

    # scan A and B completed; scan C claimed but "crashed" (left running).
    claimed = json.loads(host_runner(suite_dir, "next", "--limit", "3").stdout)["claimed"]
    for task in claimed[:2]:
        stem = task["id"].split("/", 1)[1][len("scan-"):]
        (audit_run / f"family-scan-{stem}.md").write_text(f"# scan {stem}\ncovered\n", encoding="utf-8")
        host_runner(suite_dir, "complete", task["id"])
    crashed_id = claimed[2]["id"]
    crashed_stem = crashed_id.split("/", 1)[1][len("scan-"):]

    # Simulate a crashed host session: resume via the suite CLI with host backend.
    result = run_cli(
        "python3",
        REPO_ROOT / "bin" / "run-blind-suite",
        "--repo",
        target_repo,
        "--suite-name",
        "resume-suite",
        "--resume",
        "--execution-backend",
        "host",
        cwd=tmp_path,
        check=False,
    )
    assert result.returncode == 0, result.stdout + result.stderr

    status = json.loads(host_runner(suite_dir, "status").stdout)
    assert status["phase"] == "scans"
    assert crashed_id in status["pending"], "stale running task must return to pending"
    assert crashed_id not in status["completed"]
    assert len(status["completed"]) == 2, "completed scans must not be requeued"

    # The crashed scan can be re-claimed and completed.
    re_claim = json.loads(host_runner(suite_dir, "next", "--limit", "1").stdout)["claimed"]
    assert re_claim and re_claim[0]["id"] == crashed_id
    (audit_run / f"family-scan-{crashed_stem}.md").write_text("# retry\ncovered\n", encoding="utf-8")
    done = host_runner(suite_dir, "complete", crashed_id)
    assert done.returncode == 0, done.stdout


def test_cli_runner_resume_skips_completed_scans(target_repo: Path, tmp_path: Path) -> None:
    run_cli(
        str(REPO_ROOT / "designs" / "monad-c4" / "bin" / "dlt-ai-audit-system"),
        target_repo,
        "--run-name",
        "cli-resume",
    )
    run_dir = target_repo / ".dlt-auditor-work" / "runs" / "cli-resume"
    prompt_dir = run_dir / "agent-prompts"
    for extra in sorted(prompt_dir.glob("scan-*.md")):
        extra.unlink()
    for name in ("scan-a", "scan-b"):
        (prompt_dir / f"{name}.md").write_text("prompt\n", encoding="utf-8")

    # Fake codex that succeeds and records each exec invocation.
    bindir = tmp_path / "resumebin"
    bindir.mkdir()
    marker = tmp_path / "exec.log"
    fake = bindir / "codex"
    fake.write_text(
        f"""#!/usr/bin/env bash
out=""
prev=""
for arg in "$@"; do
  if [[ "$prev" == "--output-last-message" ]]; then out="$arg"; fi
  prev="$arg"
done
cat >/dev/null
printf 'done\\n' > "$out"
echo "exec $out" >> "{marker}"
""",
        encoding="utf-8",
    )
    fake.chmod(0o755)

    import os
    import subprocess

    env = dict(os.environ)
    env["PATH"] = f"{bindir}{os.pathsep}{env.get('PATH', '')}"
    first = subprocess.run(
        [str(RUNNER), str(run_dir), "--jobs", "2", "--phase", "scans", "--skip-login-check"],
        capture_output=True, text=True, env=env, check=False,
    )
    assert first.returncode == 0, first.stdout + first.stderr
    count_after_first = len(marker.read_text(encoding="utf-8").splitlines())
    assert count_after_first == 2

    # Resume must skip both completed scans: no new invocations.
    second = subprocess.run(
        [str(RUNNER), str(run_dir), "--jobs", "2", "--phase", "scans", "--skip-login-check", "--resume"],
        capture_output=True, text=True, env=env, check=False,
    )
    assert second.returncode == 0, second.stdout + second.stderr
    assert "resume skip completed prompts: 2" in second.stdout
    assert len(marker.read_text(encoding="utf-8").splitlines()) == count_after_first


def test_legacy_suite_resumes_in_place(target_repo: Path) -> None:
    legacy_root = REPO_ROOT / "runs"
    suite = legacy_root / "legacy-test-suite"
    suite.mkdir(parents=True, exist_ok=True)
    (suite / "suite-manifest.json").write_text(
        json.dumps(
            {
                "suite_name": "legacy-test-suite",
                "target_repo": str(target_repo),
                "designs": ["monad-c4"],
                "status": "limit_exhausted",
                "settings": {"execution_backend": "host", "parallel_jobs": 3},
            }
        ),
        encoding="utf-8",
    )
    try:
        result = run_cli(
            "python3",
            REPO_ROOT / "bin" / "run-blind-suite",
            "--repo",
            target_repo,
            "--suite-name",
            "legacy-test-suite",
            "--resume",
            "--execution-backend",
            "host",
            check=False,
        )
        assert result.returncode == 0, result.stdout + result.stderr
        assert "Legacy suite detected" in result.stderr
        assert (suite / "state" / "work-queue.json").is_file()
        assert not (target_repo / ".dlt-auditor-work" / "legacy-test-suite").exists()
    finally:
        import shutil

        shutil.rmtree(suite)
