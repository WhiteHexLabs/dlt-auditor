"""Execution backend selection (plan sections 2, 4, 31, 32).

Three backends exist:

- ``host``   — scaffold + queue only; the host agent's own subagents execute.
               Never spawns codex/claude/zcode CLI processes.
- ``codex``  — subprocess Codex CLI workers via the design runner.
- ``claude`` — subprocess Claude Code workers via the design runner.

``--agent codex|claude`` is the deprecated spelling of the CLI backends and is
mapped onto ``--execution-backend``.
"""

from __future__ import annotations

from pathlib import Path

BACKENDS = ("host", "codex", "claude")
CLI_BACKENDS = ("codex", "claude")
DEFAULT_CLI_BACKEND = "codex"
AGENT_TO_BACKEND = {"codex": "codex", "claude": "claude"}

SERVICE_TIER_CHOICES = ("standard", "fast", "flex")
DEFAULT_SERVICE_TIER = "standard"
REASONING_EFFORT_CHOICES = ("low", "medium", "high", "xhigh")
DEFAULT_REASONING_EFFORT = "high"
DEFAULT_DEEP_REASONING_EFFORT = "xhigh"
DEFAULT_DEEP_PHASES = "canonicalize,validations,aggregate,final"
DEFAULT_PARALLEL_JOBS = 3
DEFAULT_TIMEOUT_SECONDS = 1800


class BackendError(ValueError):
    pass


def resolve_backend(*, execution_backend: str | None, agent: str | None) -> str:
    """Merge ``--execution-backend`` with the deprecated ``--agent``."""
    backend = (execution_backend or "").strip() or None
    mapped_agent = AGENT_TO_BACKEND.get((agent or "").strip()) if agent else None
    if agent and agent.strip() not in AGENT_TO_BACKEND:
        raise BackendError(f"unknown --agent: {agent} (expected codex or claude)")
    if backend and mapped_agent and backend != mapped_agent and backend != "host":
        raise BackendError(f"--agent {agent} conflicts with --execution-backend {execution_backend}")
    if backend == "host" and mapped_agent:
        raise BackendError(
            "--execution-backend host cannot be combined with --agent; the host backend never spawns CLI workers"
        )
    return backend or mapped_agent or DEFAULT_CLI_BACKEND


def backend_is_cli(backend: str) -> bool:
    return backend in CLI_BACKENDS


def worker_script(source_root: Path) -> Path:
    """Prefer the renamed runner; keep the legacy name for old copies."""
    root = Path(source_root)
    renamed = root / "bin" / "run-parallel-workers"
    if renamed.is_file():
        return renamed
    return root / "bin" / "run-parallel-codex"


def build_runner_command(
    *,
    backend: str,
    runner: Path,
    audit_run: Path,
    parallel_jobs: int,
    resume: bool,
    phase: str,
    model: str | None = None,
    service_tier: str = DEFAULT_SERVICE_TIER,
    reasoning_effort: str = DEFAULT_REASONING_EFFORT,
    deep_reasoning_effort: str = DEFAULT_DEEP_REASONING_EFFORT,
    deep_phases: str = DEFAULT_DEEP_PHASES,
    codex_path: str | None = None,
    claude_path: str | None = None,
    claude_add_dirs: list[Path] | None = None,
    timeout_seconds: int | None = None,
    skip_login_check: bool = False,
) -> list[str]:
    """Build the design-runner command for a CLI backend.

    Codex reasoning/service-tier overrides are only ever attached to the codex
    backend; the claude backend never carries them. The model flag is only
    attached when the user explicitly provided one (plan section 12).
    """
    if backend not in CLI_BACKENDS:
        raise BackendError(f"backend {backend} does not use CLI workers")
    command = [str(runner), str(audit_run), "--jobs", str(parallel_jobs), "--phase", phase, "--agent", backend]
    if resume:
        command.append("--resume")
    if model:
        command.extend(["--model", model])
    if backend == "codex":
        command.extend(["--service-tier", service_tier])
        command.extend(["--reasoning-effort", reasoning_effort])
        command.extend(["--deep-reasoning-effort", deep_reasoning_effort])
        command.extend(["--deep-phases", deep_phases])
        if codex_path:
            command.extend(["--codex-path", codex_path])
    if backend == "claude":
        if claude_path:
            command.extend(["--claude-path", claude_path])
        for add_dir in claude_add_dirs or []:
            command.extend(["--claude-add-dir", str(add_dir)])
    if timeout_seconds is not None:
        command.extend(["--timeout-seconds", str(timeout_seconds)])
    if skip_login_check:
        command.append("--skip-login-check")
    return command
