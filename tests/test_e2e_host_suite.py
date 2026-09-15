"""End-to-end host-native suite completion across multiple designs (plan sections 6, 24, 36)."""

from __future__ import annotations

import json
from pathlib import Path

from conftest import host_runner, run_cli, scaffold_host_suite


def _drive_serial_phase(suite_dir: Path, audit_run: Path, phase: str, outputs: dict[str, str]) -> dict:
    claimed: list[dict] = []
    for _ in range(len(PHASES) + 2):  # skip empty intermediate phases (e.g. validations with no candidates)
        payload = json.loads(host_runner(suite_dir, "next", "--limit", "1").stdout)
        claimed = payload["claimed"]
        if claimed:
            break
        advanced = host_runner(suite_dir, "advance")
        assert advanced.returncode == 0, advanced.stdout
    assert claimed and claimed[0]["phase"] == phase, f"{phase}: {claimed}"
    for name, content in outputs.items():
        (audit_run / name).write_text(content, encoding="utf-8")
    done = host_runner(suite_dir, "complete", claimed[0]["id"])
    assert done.returncode == 0, done.stdout
    advanced = host_runner(suite_dir, "advance")
    assert advanced.returncode == 0, f"{phase}: {advanced.stdout}"
    return json.loads(advanced.stdout)


PHASES = ("mapper", "corpus", "scans", "canonicalize", "validations", "aggregate", "final")


def _drive_scans_phase(suite_dir: Path, audit_run: Path) -> None:
    while True:
        payload = json.loads(host_runner(suite_dir, "next", "--limit", "3").stdout)
        if not payload["claimed"]:
            break
        for task in payload["claimed"]:
            stem = task["id"].split("/", 1)[1][len("scan-"):]
            (audit_run / f"family-scan-{stem}.md").write_text(
                f"# Family Scan {stem}\n\nmodules reviewed, candidates recorded\n", encoding="utf-8"
            )
            done = host_runner(suite_dir, "complete", task["id"])
            assert done.returncode == 0, done.stdout
    advanced = host_runner(suite_dir, "advance")
    assert advanced.returncode == 0, advanced.stdout
    assert json.loads(advanced.stdout)["to_phase"] == "canonicalize"


def test_host_suite_completes_all_designs_sequentially(target_repo: Path, tmp_path: Path) -> None:
    suite_dir = scaffold_host_suite(target_repo, "e2e-suite", ["monad-c4", "fuel-rs-attackathon"], tmp_path)

    for expected_design in ("monad-c4", "fuel-rs-attackathon"):
        audit_run = suite_dir / "design-runs" / (f"0{1 if expected_design == 'monad-c4' else 2}-{expected_design}")
        _drive_serial_phase(
            suite_dir,
            audit_run,
            "mapper",
            {
                "repo-context.md": "# Repo Context\nmapped\n",
                "feature-coverage.md": "# Feature Coverage\nrows\n",
                "verification-log.md": "# Verification Log\nnone\n",
            },
        )
        _drive_serial_phase(suite_dir, audit_run, "corpus", {"corpus-match-index.md": "# Index\nnone\n"})
        _drive_scans_phase(suite_dir, audit_run)
        _drive_serial_phase(
            suite_dir,
            audit_run,
            "canonicalize",
            {"candidate-index.md": "# Candidates\nnone\n", "rejected-candidates.md": "# Rejected\nnone\n"},
        )
        # No candidate dossiers exist, so validations has no tasks and is skipped.
        _drive_serial_phase(
            suite_dir,
            audit_run,
            "aggregate",
            {
                "candidate-index.md": "# Candidates\nnone\n",
                "rejected-candidates.md": "# Rejected\nnone\n",
                "FINAL_AUDIT_REPORT.md": "# Final Audit Report\nno surviving findings\n",
            },
        )
        result = _drive_serial_phase(
            suite_dir,
            audit_run,
            "final",
            {"final-coverage-report.md": "# Coverage\ncomplete\n"},
        )
        if expected_design == "monad-c4":
            assert result.get("next_design") == "fuel-rs-attackathon"
            assert result.get("to_phase") == "mapper"

    manifest = json.loads((suite_dir / "suite-manifest.json").read_text(encoding="utf-8"))
    assert manifest["status"] == "completed"
    for item in manifest["items"]:
        assert item["audit_status"] == "completed", item

    # Fully completed suites have no active item left.
    final_status = host_runner(suite_dir, "status")
    assert final_status.returncode == 2
    assert "already completed" in final_status.stdout
