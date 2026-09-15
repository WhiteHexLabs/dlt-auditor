"""Blind suite scaffolding and manifests.

Moved out of ``bin/run-blind-suite`` so both the suite CLI and the host-native
queue driver can scaffold design items. Responsibilities kept separate from
execution: this module creates workspaces, copies designs, generates audit
runs, and records state; it never decides how workers run (plan section 3).
"""

from __future__ import annotations

import json
import shutil
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path

from .backends import DEFAULT_DEEP_PHASES, DEFAULT_DEEP_REASONING_EFFORT, DEFAULT_REASONING_EFFORT, DEFAULT_SERVICE_TIER
from .workspace import ensure_suite_layout, utc_now

ROOT = Path(__file__).resolve().parents[1]
DESIGNS_DIR = ROOT / "designs"
CORPUS_ROOT = ROOT / "corpus" / "imports"
LEGACY_RUNS_DIR = ROOT / "runs"
LIMIT_EXHAUSTED_EXIT_CODE = 3


@dataclass(frozen=True)
class DesignSource:
    name: str
    root: Path

    @property
    def command(self) -> Path:
        return self.root / "bin" / "dlt-ai-audit-system"


def slugify(value: str) -> str:
    chars = []
    for ch in value.lower().strip():
        chars.append(ch if ch.isalnum() else "-")
    slug = "".join(chars)
    while "--" in slug:
        slug = slug.replace("--", "-")
    return slug.strip("-") or "run"


def read_json(path: Path) -> dict:
    return json.loads(Path(path).read_text(encoding="utf-8"))


def write_json(path: Path, payload: dict) -> None:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def update_json(path: Path, **updates: object) -> dict:
    path = Path(path)
    payload = read_json(path) if path.is_file() else {}
    payload.update(updates)
    payload["updated_at_utc"] = utc_now()
    write_json(path, payload)
    return payload


def design_ignore(_dir: str, names: list[str]) -> set[str]:
    return {name for name in names if name in {"runs", "__pycache__"} or name.endswith(".pyc")}


def copy_design_tree(source: Path, destination: Path, force: bool) -> None:
    source = Path(source).resolve()
    destination = Path(destination).resolve()
    if source == destination:
        raise SystemExit(f"Source and destination are the same design folder: {source}")
    if destination.exists():
        if not force:
            raise SystemExit(f"Destination already exists: {destination}")
        shutil.rmtree(destination)
    shutil.copytree(source, destination, ignore=design_ignore)


def command_supports_flag(command: Path, flag: str) -> bool:
    try:
        return flag in Path(command).read_text(encoding="utf-8", errors="ignore")
    except OSError:
        return False


def load_design_source(design: str) -> DesignSource:
    name = slugify(design)
    root = DESIGNS_DIR / name
    if not root.is_dir():
        raise SystemExit(f"Design not found: {root}")
    source = DesignSource(name=name, root=root.resolve())
    if not source.command.is_file():
        raise SystemExit(f"Design command not found: {source.command}")
    return source


def load_suite_design_source(design_root: Path, design: str) -> DesignSource:
    source = DesignSource(name=slugify(design), root=Path(design_root).resolve())
    if not source.command.is_file():
        raise SystemExit(f"Suite design command not found: {source.command}")
    return source


def suite_item_dir(suite_dir: Path, index: int, design_name: str) -> Path:
    return Path(suite_dir) / "design-runs" / f"{index:02d}-{slugify(design_name)}"


def suite_design_copy_dir(suite_dir: Path, design_name: str) -> Path:
    return Path(suite_dir) / "design-workspaces" / slugify(design_name) / "design"


def scaffold_audit_run(
    source: DesignSource,
    repo: Path,
    run_name: str,
    *,
    force: bool,
    previous_ref: str | None,
    current_ref: str | None,
    parallel_jobs: int,
    runs_dir: Path | None = None,
) -> tuple[Path, bool]:
    """Create one audit run via the design scaffolder.

    New design packs accept ``--runs-dir`` and place the audit run directly
    under ``<suite>/design-runs/<run-name>``. Old copied packs without the
    flag keep their legacy location inside the copied design tree; the caller
    treats both identically afterwards.
    """
    args = [str(source.command), str(repo), "--run-name", run_name]
    if force:
        args.append("--force")
    if previous_ref and command_supports_flag(source.command, "--previous-ref"):
        args.extend(["--previous-ref", previous_ref])
    if current_ref and command_supports_flag(source.command, "--current-ref"):
        args.extend(["--current-ref", current_ref])
    if command_supports_flag(source.command, "--corpus-root"):
        args.extend(["--corpus-root", str(CORPUS_ROOT)])
    if command_supports_flag(source.command, "--parallel-jobs"):
        args.extend(["--parallel-jobs", str(parallel_jobs)])
    supports_runs_dir = command_supports_flag(source.command, "--runs-dir")
    if runs_dir is not None and supports_runs_dir:
        args.extend(["--runs-dir", str(runs_dir)])
        legacy = False
    elif supports_runs_dir:
        # Legacy suite layout: keep the run inside the copied design tree.
        args.extend(["--runs-dir", str(source.root / "runs")])
        legacy = True
    # else: pre-legacy scaffolders already default to their own runs/ directory.

    completed = subprocess.run(args, text=True, capture_output=True, check=False)
    if completed.returncode != 0:
        print(completed.stdout, end="")
        print(completed.stderr, end="", file=sys.stderr)
        raise SystemExit(completed.returncode)

    audit_run = (Path(runs_dir) if runs_dir is not None and supports_runs_dir else source.root / "runs") / run_name
    if not audit_run.is_dir():
        raise SystemExit(f"Expected design run was not created: {audit_run}")
    return audit_run, legacy


def blind_suite_isolation_addendum(
    *,
    suite_dir: Path,
    original_design_dir: Path,
    design_root: Path,
    target: Path,
    audit_run: Path,
    corpus_root: Path,
) -> str:
    suite_dir = Path(suite_dir)
    work_root = suite_dir.parent
    return f"""# Blind Suite Isolation Addendum

This audit is one item in a blind multi-design suite.

Allowed inputs for this item:
- Target repository: `{target}`
- Active copied design directory: `{design_root}`
- Active audit run directory: `{audit_run}`
- Shared corpus root: `{corpus_root}`

Forbidden while producing this item's blind audit outputs:
- Do not read, search, summarize, or use the original stable design directory: `{original_design_dir}`
- Do not read stable design run output under: `{DESIGNS_DIR / "*" / "runs"}`
- Do not read any other suite item's copied design, run directory, findings, reports, logs, or agent outputs anywhere under: `{suite_dir / "design-runs"}` other than `{audit_run}`, or under sibling design workspaces in `{suite_dir / "design-workspaces"}`
- Do not read other suites or prior audit output under: `{work_root}` (other than this suite) or under `{LEGACY_RUNS_DIR}`
- Do not read known findings, answer keys, scorecards, miss analyses, result records, leaderboards, refinement plans, audit-output snapshots, candidate result archives, or prior round folders.

The copied design and active run directory above are allowed. All sibling suite workspaces and previous outputs are forbidden as evidence or examples. If you accidentally see forbidden material, do not use it; record the contamination risk in `verification-log.md` and continue only from target-code evidence.

"""


def add_blind_suite_isolation_to_prompts(
    *,
    suite_dir: Path,
    original_design_dir: Path,
    design_root: Path,
    target: Path,
    audit_run: Path,
    corpus_root: Path,
) -> None:
    addendum = blind_suite_isolation_addendum(
        suite_dir=suite_dir,
        original_design_dir=original_design_dir,
        design_root=design_root,
        target=target,
        audit_run=audit_run,
        corpus_root=corpus_root,
    )
    prompt_dir = Path(audit_run) / "agent-prompts"
    if not prompt_dir.is_dir():
        return
    for prompt_path in sorted(prompt_dir.glob("*.md")):
        try:
            existing = prompt_path.read_text(encoding="utf-8")
        except OSError:
            continue
        if "Blind Suite Isolation Addendum" in existing:
            continue
        prompt_path.write_text(addendum + existing, encoding="utf-8")


def default_settings(backend: str, parallel_jobs: int) -> dict:
    return {
        "execution_backend": backend,
        "parallel_jobs": parallel_jobs,
        "model": "",
        "service_tier": DEFAULT_SERVICE_TIER,
        "reasoning_effort": DEFAULT_REASONING_EFFORT,
        "deep_reasoning_effort": DEFAULT_DEEP_REASONING_EFFORT,
        "deep_phases": DEFAULT_DEEP_PHASES,
        "codex_path": "",
        "claude_path": "",
        "claude_add_dirs": [],
        "timeout_seconds": None,
        "skip_login_check": False,
        "previous_ref": "",
        "current_ref": "",
    }


def suite_item_summary(item_dir: Path) -> dict:
    manifest_path = Path(item_dir) / "item-manifest.json"
    if not manifest_path.is_file():
        return {"item_dir": str(item_dir), "status": "not_started", "audit_status": "not_started"}
    manifest = read_json(manifest_path)
    return {
        "design": manifest.get("design", ""),
        "item_dir": str(item_dir),
        "original_design_dir": manifest.get("original_design_dir", ""),
        "design_copy_dir": manifest.get("source_design_dir", ""),
        "audit_run": manifest.get("audit_run", ""),
        "status": manifest.get("status", ""),
        "audit_status": manifest.get("audit_status", ""),
    }


def write_suite_manifest(
    suite_dir: Path,
    *,
    suite_name: str,
    target: Path,
    designs: list[str],
    status: str,
    settings: dict,
    created_at_utc: str | None = None,
    message: str = "",
    work_root: Path | None = None,
    legacy: bool = False,
) -> dict:
    manifest_path = Path(suite_dir) / "suite-manifest.json"
    previous = read_json(manifest_path) if manifest_path.is_file() else {}
    payload = {
        "schema_version": 1,
        "kind": "blind-suite",
        "suite_name": suite_name,
        "target_repo": str(target),
        "work_root": str(work_root or Path(suite_dir).parent),
        "legacy_layout": legacy,
        "designs": designs,
        "status": status,
        "message": message,
        "settings": settings,
        "items": [
            suite_item_summary(suite_item_dir(suite_dir, index, design))
            for index, design in enumerate(designs, start=1)
        ],
        "created_at_utc": created_at_utc or previous.get("created_at_utc") or utc_now(),
        "updated_at_utc": utc_now(),
    }
    write_json(manifest_path, payload)
    return payload


def write_suite_readme(suite_dir: Path, manifest: dict) -> None:
    suite_dir = Path(suite_dir)
    backend = (manifest.get("settings") or {}).get("execution_backend", "")
    design_lines = "\n".join(f"- `{design}`" for design in manifest.get("designs", [])) or "- none"
    settings_lines = "\n".join(
        f"- {key}: `{value}`" for key, value in sorted((manifest.get("settings") or {}).items())
    )
    item_lines = [
        f"- `{item.get('design', '')}`: `{item.get('audit_status', '')}` at `{item.get('item_dir', '')}`"
        for item in manifest.get("items", [])
    ]
    items = "\n".join(item_lines) or "- none"
    resume_command = (
        f"bin/run-blind-suite --repo {manifest.get('target_repo', '')} --suite-name {suite_dir.name} --resume"
    )
    host_hint = ""
    if backend == "host":
        host_hint = f"""
## Host Execution

Drive the host-native queue with:

```bash
bin/host-runner {suite_dir} status
bin/host-runner {suite_dir} next --limit 3
```

The host backend never launches local Codex or Claude CLI workers.
"""
    (suite_dir / "README.md").write_text(
        f"""# Blind Design Suite: {manifest.get("suite_name", suite_dir.name)}

- Target repo: `{manifest.get("target_repo", "")}`
- Work root: `{manifest.get("work_root", "")}`
- Execution backend: `{backend}`
- Status: `{manifest.get("status", "")}`
- Updated UTC: {manifest.get("updated_at_utc", "")}

## Designs

{design_lines}

## Settings

{settings_lines}

## Items

{items}
{host_hint}
## Resume

```bash
{resume_command}
```

Each design is copied into this suite with old `runs/` output excluded before execution. During an item run, workers may use only the target repository, the copied active design, the active audit run directory, and explicitly named corpus files.
""",
        encoding="utf-8",
    )


def scaffold_suite_item(
    *,
    suite_dir: Path,
    index: int,
    design_name: str,
    target: Path,
    settings: dict,
    force: bool,
    legacy_layout: bool = False,
) -> tuple[Path, Path, Path]:
    """Scaffold one suite item. Returns (item_dir, design_copy, audit_run)."""
    original_source = load_design_source(design_name)
    item_dir = suite_item_dir(suite_dir, index, design_name)
    design_copy = suite_design_copy_dir(suite_dir, design_name)
    if item_dir.exists() and any(item_dir.iterdir()) and not force:
        raise SystemExit(f"Suite item already exists: {item_dir}")
    if item_dir.exists() and force:
        shutil.rmtree(item_dir)
    if design_copy.exists() and force:
        shutil.rmtree(design_copy.parent)
    if not design_copy.is_dir():
        copy_design_tree(original_source.root, design_copy, False)

    item_dir.mkdir(parents=True, exist_ok=True)
    suite_source = load_suite_design_source(design_copy, design_name)
    run_name = item_dir.name
    audit_run, _legacy_run = scaffold_audit_run(
        suite_source,
        target,
        run_name,
        force=force,
        previous_ref=str(settings.get("previous_ref") or "") or None,
        current_ref=str(settings.get("current_ref") or "") or None,
        parallel_jobs=int(settings.get("parallel_jobs") or 3),
        runs_dir=None if legacy_layout else Path(suite_dir) / "design-runs",
    )
    add_blind_suite_isolation_to_prompts(
        suite_dir=suite_dir,
        original_design_dir=original_source.root,
        design_root=design_copy,
        target=target,
        audit_run=audit_run,
        corpus_root=CORPUS_ROOT,
    )
    manifest = {
        "schema_version": 1,
        "kind": "blind-suite-item",
        "suite_name": Path(suite_dir).name,
        "repo": str(target),
        "design": design_name,
        "original_design_dir": str(original_source.root),
        "source_design_dir": str(design_copy.resolve()),
        "item_index": index,
        "item_label": f"{index:02d}-{design_name}",
        "audit_run": str(audit_run),
        "audit_status": "not_started",
        "audit_resume_supported": True,
        "settings": settings,
        "created_at_utc": utc_now(),
        "status": "scaffolded",
    }
    write_json(item_dir / "item-manifest.json", manifest)
    (item_dir / "RUN.md").write_text(
        f"""# Blind Suite Item: {design_name}

- Suite: `{suite_dir}`
- Target repo: `{target}`
- Original design: `{original_source.root}`
- Copied design: `{design_copy.resolve()}`
- Active audit run: `{audit_run}`

This item is isolated from prior suite results. Do not read sibling suite workspaces, other suites under `{Path(suite_dir).parent}`, legacy `{LEGACY_RUNS_DIR}`, or stable `designs/*/runs/**` output while producing findings.

Resume the suite if needed:

```bash
bin/run-blind-suite --repo {target} --suite-name {Path(suite_dir).name} --resume
```
""",
        encoding="utf-8",
    )
    return item_dir, design_copy, audit_run


def scaffold_suite(
    *,
    suite_dir: Path,
    suite_name: str,
    target: Path,
    designs: list[str],
    settings: dict,
    resume: bool,
    force: bool,
    legacy_layout: bool = False,
) -> dict:
    """Create the suite workspace and scaffold any missing design items."""
    ensure_suite_layout(suite_dir)
    created_at = None if resume else utc_now()
    manifest = write_suite_manifest(
        suite_dir,
        suite_name=suite_name,
        target=target,
        designs=designs,
        status="scaffolded",
        settings=settings,
        created_at_utc=created_at,
        work_root=Path(suite_dir).parent,
        legacy=legacy_layout,
    )
    write_suite_readme(suite_dir, manifest)
    for index, design_name in enumerate(designs, start=1):
        item_dir = suite_item_dir(suite_dir, index, design_name)
        if (item_dir / "item-manifest.json").is_file():
            continue
        if item_dir.exists() and any(item_dir.iterdir()) and not force:
            raise SystemExit(f"Suite item already exists: {item_dir}")
        scaffold_suite_item(
            suite_dir=suite_dir,
            index=index,
            design_name=design_name,
            target=target,
            settings=settings,
            force=force,
            legacy_layout=legacy_layout,
        )
    manifest = write_suite_manifest(
        suite_dir,
        suite_name=suite_name,
        target=target,
        designs=designs,
        status="scaffolded",
        settings=settings,
        created_at_utc=created_at,
        message="Suite scaffolded without launching workers.",
        work_root=Path(suite_dir).parent,
        legacy=legacy_layout,
    )
    write_suite_readme(suite_dir, manifest)
    return manifest


def list_designs() -> list[str]:
    return [
        path.name
        for path in sorted(DESIGNS_DIR.iterdir())
        if (path / "bin" / "dlt-ai-audit-system").is_file()
    ]


def load_design_profile(design_root: Path) -> dict:
    """Read ``design-profile.md`` from a design pack.

    Returns keys: name, ecosystem, languages, protocol_type, execution_model,
    consensus_model, vm, focus_surfaces (list), preservation_notes (list).
    All values are hypothesis context only (plan sections 21-22).
    """
    path = Path(design_root) / "design-profile.md"
    profile: dict = {
        "name": Path(design_root).name,
        "keys": {},
        "focus_surfaces": [],
        "preservation_notes": [],
    }
    if not path.is_file():
        return profile
    section: str | None = None
    section_map = {
        "focus surfaces": "focus_surfaces",
        "hypothesis preservation notes": "preservation_notes",
    }
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if line.startswith("## "):
            title = line[3:].strip().lower()
            field = section_map.get(title)
            section = field if field else None
            continue
        if not line.startswith("- "):
            continue
        item = line[2:].strip()
        if section:
            profile[section].append(item)
        elif ":" in item:
            key, _, value = item.partition(":")
            normalized = key.strip().lower().replace(" ", "_")
            if len(normalized) <= 40:
                profile["keys"][normalized] = value.strip()
    return profile
