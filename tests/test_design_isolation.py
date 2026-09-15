"""Blind isolation between designs and path rules (plan sections 9-10, 19, 24)."""

from __future__ import annotations

import json
from pathlib import Path

from conftest import scaffold_host_suite


def test_every_prompt_carries_isolation_addendum(target_repo: Path, tmp_path: Path) -> None:
    suite_dir = scaffold_host_suite(target_repo, "iso-suite", ["monad-c4", "blast-cantina"], tmp_path)
    for item in ("01-monad-c4", "02-blast-cantina"):
        prompt_dir = suite_dir / "design-runs" / item / "agent-prompts"
        prompts = sorted(prompt_dir.glob("*.md"))
        assert prompts
        for prompt in prompts:
            text = prompt.read_text(encoding="utf-8")
            assert "Blind Suite Isolation Addendum" in text, prompt


def test_addendum_forbids_sibling_and_legacy_paths(target_repo: Path, tmp_path: Path) -> None:
    suite_dir = scaffold_host_suite(target_repo, "paths-suite", ["monad-c4", "blast-cantina"], tmp_path)
    work_root = target_repo / ".dlt-auditor-work"
    sample = (suite_dir / "design-runs" / "01-monad-c4" / "agent-prompts" / "00-protocol-mapper.md").read_text(
        encoding="utf-8"
    )
    assert str(suite_dir / "design-runs") in sample
    assert str(suite_dir / "design-workspaces") in sample
    assert str(work_root) in sample
    assert "designs/*/runs" in sample  # legacy stable-design output stays forbidden
    # The other design's run dir must not be listed as an allowed input.
    assert "02-blast-cantina" not in sample.split("Allowed inputs for this item:")[1].split("Forbidden")[0]


def test_parallel_tasks_own_exclusive_outputs(target_repo: Path, tmp_path: Path) -> None:
    suite_dir = scaffold_host_suite(target_repo, "owner-suite", ["monad-c4"], tmp_path)
    audit_run = suite_dir / "design-runs" / "01-monad-c4"
    from conftest import host_runner

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

    claimed = json.loads(host_runner(suite_dir, "next", "--limit", "2").stdout)["claimed"]
    assert len(claimed) == 2
    outputs = [Path(out) for task in claimed for out in task["outputs"]]
    assert all(out.name.startswith("family-scan-") for out in outputs)
    assert len({out.name for out in outputs}) == len(outputs), "scan outputs must be exclusive per worker"
    for task in claimed:
        assert "only write" in task["instruction"]


def test_validation_workers_own_exclusive_dossiers(tmp_path: Path) -> None:
    """The scheduler must generate one exclusive validation prompt per candidate."""
    import sys

    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
    from runtime import scheduler

    audit_run = tmp_path / "run"
    prompt_dir = audit_run / "agent-prompts"
    prompt_dir.mkdir(parents=True)
    (prompt_dir / "90-validate-candidates.md").write_text("base\n", encoding="utf-8")
    for name in ("candidate-F10-001.md", "candidate-F11-002.md"):
        (audit_run / name).write_text("# candidate\n", encoding="utf-8")
    tasks = scheduler.phase_tasks(audit_run, "validations")
    assert [task.name for task in tasks] == ["validate-candidate-F10-001", "validate-candidate-F11-002"]
    assert all(task.parallel for task in tasks)
    assert [task.outputs[0].name for task in tasks] == ["candidate-F10-001.md", "candidate-F11-002.md"]
    assert all((prompt_dir / "generated-validations" / f"{task.name}.md").is_file() for task in tasks)
