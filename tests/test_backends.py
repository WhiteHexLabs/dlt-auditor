"""Execution backend selection and command construction (plan sections 2, 12, 32)."""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT))

from runtime.backends import (  # noqa: E402
    BackendError,
    build_runner_command,
    resolve_backend,
)


def test_default_backend_is_codex_for_cli() -> None:
    assert resolve_backend(execution_backend=None, agent=None) == "codex"


def test_deprecated_agent_maps_to_backend() -> None:
    assert resolve_backend(execution_backend=None, agent="claude") == "claude"
    assert resolve_backend(execution_backend=None, agent="codex") == "codex"
    assert resolve_backend(execution_backend="claude", agent="claude") == "claude"


def test_agent_backend_conflict_raises() -> None:
    with pytest.raises(BackendError):
        resolve_backend(execution_backend="codex", agent="claude")


def test_host_rejects_agent() -> None:
    with pytest.raises(BackendError):
        resolve_backend(execution_backend="host", agent="codex")


def test_codex_command_shape() -> None:
    command = build_runner_command(
        backend="codex",
        runner=Path("/runner"),
        audit_run=Path("/run"),
        parallel_jobs=3,
        resume=False,
        phase="all",
    )
    assert "--agent" in command and command[command.index("--agent") + 1] == "codex"
    assert "--jobs" in command and command[command.index("--jobs") + 1] == "3"
    assert "--service-tier" in command
    assert "--reasoning-effort" in command
    assert "--deep-reasoning-effort" in command
    assert "--model" not in command  # never override the CLI's own model by default


def test_codex_command_includes_model_only_when_explicit() -> None:
    command = build_runner_command(
        backend="codex",
        runner=Path("/runner"),
        audit_run=Path("/run"),
        parallel_jobs=3,
        resume=True,
        phase="scans",
        model="custom-model",
    )
    assert command[command.index("--model") + 1] == "custom-model"


def test_claude_command_has_no_codex_flags() -> None:
    command = build_runner_command(
        backend="claude",
        runner=Path("/runner"),
        audit_run=Path("/run"),
        parallel_jobs=3,
        resume=False,
        phase="all",
        claude_add_dirs=[Path("/target")],
    )
    assert "--agent" in command and command[command.index("--agent") + 1] == "claude"
    for flag in ("--service-tier", "--reasoning-effort", "--deep-reasoning-effort", "--deep-phases", "--codex-path"):
        assert flag not in command
    assert "--claude-add-dir" in command
    assert command[command.index("--claude-add-dir") + 1] == "/target"


def test_host_backend_cannot_build_cli_command() -> None:
    with pytest.raises(BackendError):
        build_runner_command(
            backend="host",
            runner=Path("/runner"),
            audit_run=Path("/run"),
            parallel_jobs=3,
            resume=False,
            phase="all",
        )


def test_runner_prefers_renamed_script(tmp_path: Path) -> None:
    from runtime.backends import worker_script

    legacy = tmp_path / "bin" / "run-parallel-codex"
    legacy.parent.mkdir()
    legacy.write_text("#!/bin/sh\n", encoding="utf-8")
    assert worker_script(tmp_path).name == "run-parallel-codex"
    renamed = tmp_path / "bin" / "run-parallel-workers"
    renamed.write_text("#!/bin/sh\n", encoding="utf-8")
    assert worker_script(tmp_path).name == "run-parallel-workers"
