"""Workspace resolution for audit suites.

Default layout (plan section 13/14): every runtime artifact lives under the
target repository at ``<target>/.dlt-auditor-work/<suite-name>/``. The legacy
layout under ``<dlt-auditor>/runs/<suite-name>/`` stays readable for resume so
historical suites are never destroyed (plan section 18), but new suites never
default to it.
"""

from __future__ import annotations

import datetime as dt
from dataclasses import dataclass
from pathlib import Path

WORK_DIR_NAME = ".dlt-auditor-work"
GITIGNORE_ENTRY = f"{WORK_DIR_NAME}/"


def utc_now() -> str:
    return dt.datetime.now(dt.UTC).strftime("%Y-%m-%dT%H:%M:%SZ")


@dataclass(frozen=True)
class WorkspaceResolution:
    work_root: Path
    suite_dir: Path
    legacy: bool
    message: str


def default_work_root(repo: Path) -> Path:
    return Path(repo) / WORK_DIR_NAME


def resolve_suite_dir(
    *,
    repo: Path,
    suite_name: str,
    work_root: Path | None = None,
    legacy_runs_dir: Path | None = None,
) -> WorkspaceResolution:
    """Resolve the directory for a suite.

    Prefers ``<work-root|repo/.dlt-auditor-work>/<suite-name>``. When that
    directory does not exist but the legacy ``<dlt-auditor>/runs/<suite-name>``
    does, returns the legacy directory with a warning so old suites can resume
    in place without migration.
    """
    resolved_root = Path(work_root).expanduser().resolve() if work_root else default_work_root(repo)
    suite_dir = resolved_root / suite_name
    if suite_dir.is_dir():
        return WorkspaceResolution(resolved_root, suite_dir, False, "")
    if legacy_runs_dir is not None:
        legacy_suite = Path(legacy_runs_dir).expanduser().resolve() / suite_name
        if legacy_suite.is_dir():
            return WorkspaceResolution(
                legacy_suite.parent,
                legacy_suite,
                True,
                f"Legacy suite detected: {legacy_suite}. Resuming in place under the legacy runs/ layout; "
                "new suites default to <target>/.dlt-auditor-work/.",
            )
    return WorkspaceResolution(resolved_root, suite_dir, False, "")


def gitignore_needs_entry(repo: Path) -> bool:
    gitignore = Path(repo) / ".gitignore"
    if not gitignore.is_file():
        return False
    try:
        lines = gitignore.read_text(encoding="utf-8").splitlines()
    except OSError:
        return False
    return not any(line.strip().rstrip("/") == WORK_DIR_NAME for line in lines)


def print_gitignore_hint(repo: Path) -> None:
    if gitignore_needs_entry(repo):
        print(f"Hint: consider adding `{GITIGNORE_ENTRY}` to {repo / '.gitignore'} so audit output stays untracked.")


def update_gitignore(repo: Path) -> bool:
    """Opt-in helper: append the work-dir entry to the target's .gitignore."""
    gitignore = Path(repo) / ".gitignore"
    if not gitignore_needs_entry(repo):
        return False
    existing = gitignore.read_text(encoding="utf-8")
    with gitignore.open("a", encoding="utf-8") as handle:
        if existing and not existing.endswith("\n"):
            handle.write("\n")
        handle.write(f"\n# dlt-auditor runtime output\n{GITIGNORE_ENTRY}\n")
    return True


def ensure_suite_layout(suite_dir: Path) -> None:
    """Create the standard suite subdirectories (plan section 14)."""
    for child in ("state", "design-workspaces", "design-runs", "logs"):
        (suite_dir / child).mkdir(parents=True, exist_ok=True)
