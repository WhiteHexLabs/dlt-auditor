"""Default concurrency and sliding-window scheduling (plan sections 7-8)."""

from __future__ import annotations

import json
import re
import sys
import time
from pathlib import Path

from conftest import REPO_ROOT, host_runner, run_cli, scaffold_host_suite

sys.path.insert(0, str(REPO_ROOT))

RUNNER = REPO_ROOT / "designs" / "monad-c4" / "bin" / "run-parallel-workers"


def test_default_parallel_jobs_is_three() -> None:
    from runtime.backends import DEFAULT_PARALLEL_JOBS

    assert DEFAULT_PARALLEL_JOBS == 3
    help_text = run_cli("python3", str(REPO_ROOT / "bin" / "run-blind-suite"), "--help").stdout
    assert "default: 3" in help_text
    # The design runner's argparse does not render defaults in --help, so assert the source.
    runner_source = RUNNER.read_text(encoding="utf-8")
    match = re.search(r'"--jobs",\s*\n\s*type=int,\s*\n\s*default=(\d+),', runner_source)
    assert match and match.group(1) == "3", "design runner --jobs default must stay 3"


def test_host_queue_window_is_capped_and_refilled(target_repo: Path, tmp_path: Path) -> None:
    suite_dir = scaffold_host_suite(target_repo, "window-suite", ["monad-c4"], tmp_path)

    # Advance to the scans phase via mapper + corpus.
    audit_run = suite_dir / "design-runs" / "01-monad-c4"
    host_runner(suite_dir, "next", "--limit", "1")
    (audit_run / "repo-context.md").write_text("mapped\n", encoding="utf-8")
    (audit_run / "feature-coverage.md").write_text("rows\n", encoding="utf-8")
    (audit_run / "verification-log.md").write_text("none\n", encoding="utf-8")
    host_runner(suite_dir, "complete", "mapper/00-protocol-mapper")
    host_runner(suite_dir, "advance")
    host_runner(suite_dir, "next", "--limit", "1")
    (audit_run / "corpus-match-index.md").write_text("indexed\n", encoding="utf-8")
    host_runner(suite_dir, "complete", "corpus/05-corpus-pattern-search")
    host_runner(suite_dir, "advance")

    status = json.loads(host_runner(suite_dir, "status").stdout)
    assert status["phase"] == "scans"
    assert len(status["pending"]) > 3

    # Asking for more than the window still claims at most 3.
    first = json.loads(host_runner(suite_dir, "next", "--limit", "9").stdout)
    assert len(first["claimed"]) == 3
    assert len(first["running"]) == 3

    # Completing exactly one task immediately frees exactly one slot: sliding window.
    done_id = first["claimed"][0]["id"]
    stem = done_id.split("/", 1)[1][len("scan-"):]
    (audit_run / f"family-scan-{stem}.md").write_text(f"# Family Scan {stem}\n\ncovered\n", encoding="utf-8")
    completed = host_runner(suite_dir, "complete", done_id)
    assert completed.returncode == 0, completed.stdout
    refill = json.loads(host_runner(suite_dir, "next", "--limit", "9").stdout)
    assert len(refill["claimed"]) == 1
    assert len(refill["running"]) == 3


def _make_timed_fake_codex(bindir: Path, events: Path) -> None:
    script = bindir / "codex"
    script.write_text(
        f"""#!/usr/bin/env bash
# Fake codex: sleeps 1.5s for prompts containing SLOWMARKER, else 0.2s.
out=""
prev=""
for arg in "$@"; do
  if [[ "$prev" == "--output-last-message" ]]; then out="$arg"; fi
  prev="$arg"
done
prompt="$(cat)"
now=$(python3 -c 'import time; print(f"{{time.monotonic():.3f}}")')
if [[ "$prompt" == *SLOWMARKER* ]]; then
  echo "$now start $out slow" >> {events}
  sleep 1.5
else
  echo "$now start $out fast" >> {events}
  sleep 0.2
fi
printf 'final message\\n' > "$out"
now=$(python3 -c 'import time; print(f"{{time.monotonic():.3f}}")')
echo "$now end $out" >> {events}
""",
        encoding="utf-8",
    )
    script.chmod(0o755)


def test_cli_runner_sliding_window(target_repo: Path, tmp_path: Path) -> None:
    """Three scans with --jobs 2 must refill a slot instead of waiting for the batch.

    Task A sleeps 1.5s; tasks B and C sleep 0.2s. Sliding window => C starts
    right after B finishes (~0.2s), long before A ends (~1.5s). Batch mode would
    run A+B first and start C only after BOTH finish (~1.5s).
    """
    run_dir = target_repo / ".dlt-auditor-work" / "runs" / "sliding"
    run_cli(str(REPO_ROOT / "designs" / "monad-c4" / "bin" / "dlt-ai-audit-system"), target_repo, "--run-name", "sliding")
    prompt_dir = run_dir / "agent-prompts"
    for extra in sorted(prompt_dir.glob("scan-*.md")):
        extra.unlink()
    for name, marker in (("scan-a", "SLOWMARKER"), ("scan-b", ""), ("scan-c", "")):
        (prompt_dir / f"{name}.md").write_text(f"prompt {marker}\n", encoding="utf-8")

    bindir = tmp_path / "timedbin"
    bindir.mkdir()
    events = tmp_path / "events.log"
    _make_timed_fake_codex(bindir, events)

    result = subprocess_run_with_path(
        str(RUNNER), str(run_dir), "--jobs", "2", "--phase", "scans", "--skip-login-check",
        "--timeout-seconds", "60", path_prefix=str(bindir)
    )
    assert result.returncode == 0, result.stdout + result.stderr

    rows = [line.split() for line in events.read_text(encoding="utf-8").splitlines()]
    starts = {row[2]: float(row[0]) for row in rows if row[1] == "start"}
    ends = {row[2]: float(row[0]) for row in rows if row[1] == "end"}
    slow_output = next(key for key, value in starts.items() if "scan-a" in key)
    fast_outputs = [key for key in starts if "scan-a" not in key]
    # The last fast worker must START while the slow worker is still running:
    # sliding-window refill, not wait-for-the-whole-batch.
    assert sorted(starts[key] for key in fast_outputs)[-1] < ends[slow_output] - 0.5


def subprocess_run_with_path(*args: str, path_prefix: str):
    import os
    import subprocess

    env = dict(os.environ)
    env["PATH"] = f"{path_prefix}{os.pathsep}{env.get('PATH', '')}"
    return subprocess.run([str(a) for a in args], capture_output=True, text=True, env=env, check=False)
