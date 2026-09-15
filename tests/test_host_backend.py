"""Host backend guarantees (plan sections 1, 4, 31, 34).

The host backend must never invoke the codex, claude, or zcode CLIs — verified
with fake executables on PATH that record every invocation.
"""

from __future__ import annotations

import json
from pathlib import Path

from conftest import FakeCli, host_runner, run_cli, scaffold_host_suite, write_minimal_mapper_outputs


def test_host_scaffold_and_mapper_never_calls_cli(
    target_repo: Path, tmp_path: Path, fake_cli: FakeCli
) -> None:
    suite_dir = scaffold_host_suite(target_repo, "host-suite", ["monad-c4"], tmp_path)
    assert fake_cli.invocations == []

    # Drive one full phase through the queue: claim, produce outputs, complete, advance.
    nxt = host_runner(suite_dir, "next", "--limit", "1")
    assert nxt.returncode == 0, nxt.stdout + nxt.stderr
    claimed = json.loads(nxt.stdout)["claimed"]
    assert len(claimed) == 1
    assert claimed[0]["id"] == "mapper/00-protocol-mapper"
    assert claimed[0]["parallel"] is False

    write_minimal_mapper_outputs(suite_dir / "design-runs" / "01-monad-c4")

    done = host_runner(suite_dir, "complete", "mapper/00-protocol-mapper")
    assert done.returncode == 0, done.stdout + done.stderr

    advanced = host_runner(suite_dir, "advance")
    assert advanced.returncode == 0, advanced.stdout + advanced.stderr
    assert json.loads(advanced.stdout)["to_phase"] == "corpus"

    status = host_runner(suite_dir, "status")
    assert fake_cli.invocations == []
    assert fake_cli.count("codex") == 0
    assert fake_cli.count("claude") == 0
    assert fake_cli.count("zcode") == 0


def test_complete_rejects_missing_artifacts(target_repo: Path, tmp_path: Path) -> None:
    suite_dir = scaffold_host_suite(target_repo, "gate-suite", ["monad-c4"], tmp_path)
    host_runner(suite_dir, "next", "--limit", "1")
    # mapper outputs were never written: completion must fail loudly (plan section 28).
    done = host_runner(suite_dir, "complete", "mapper/00-protocol-mapper")
    assert done.returncode == 2
    assert "completion artifacts missing" in done.stdout
    failed = host_runner(suite_dir, "fail", "mapper/00-protocol-mapper", "--reason", "subagent crashed")
    assert failed.returncode == 0, failed.stdout


def test_advance_blocked_while_tasks_pending(target_repo: Path, tmp_path: Path) -> None:
    suite_dir = scaffold_host_suite(target_repo, "block-suite", ["monad-c4"], tmp_path)
    blocked = host_runner(suite_dir, "advance")
    assert blocked.returncode == 2
    assert "pending/running tasks" in blocked.stdout


def test_limit_exhausted_blocks_advance_and_requeue_restores(
    target_repo: Path, tmp_path: Path
) -> None:
    suite_dir = scaffold_host_suite(target_repo, "limit-suite", ["monad-c4"], tmp_path)
    host_runner(suite_dir, "next", "--limit", "1")
    limited = host_runner(suite_dir, "limit-exhausted", "mapper/00-protocol-mapper")
    assert limited.returncode == 0, limited.stdout
    blocked = host_runner(suite_dir, "advance")
    assert blocked.returncode == 2
    assert "limit-exhausted" in blocked.stdout
    requeued = host_runner(suite_dir, "requeue", "mapper/00-protocol-mapper")
    assert requeued.returncode == 0, requeued.stdout
    status = json.loads(host_runner(suite_dir, "status").stdout)
    assert "mapper/00-protocol-mapper" in status["pending"]


def test_host_suite_manifest_records_backend(target_repo: Path, tmp_path: Path) -> None:
    suite_dir = scaffold_host_suite(target_repo, "meta-suite", ["monad-c4"], tmp_path)
    manifest = json.loads((suite_dir / "suite-manifest.json").read_text(encoding="utf-8"))
    assert manifest["settings"]["execution_backend"] == "host"
    assert manifest["work_root"] == str(target_repo / ".dlt-auditor-work")


def test_host_and_cli_agent_conflict_rejected(target_repo: Path, tmp_path: Path) -> None:
    result = run_cli(
        "python3",
        "bin/run-blind-suite",
        "--repo",
        target_repo,
        "--suite-name",
        "conflict-suite",
        "--design",
        "monad-c4",
        "--execution-backend",
        "host",
        "--agent",
        "codex",
        cwd=Path(__file__).resolve().parents[1],
        check=False,
    )
    assert result.returncode == 2
    assert "cannot be combined with --agent" in result.stderr
