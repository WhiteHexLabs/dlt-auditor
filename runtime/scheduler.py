"""Audit phase scheduling shared by host and CLI executions (plan section 6).

Fixed order: mapper -> corpus -> scans -> canonicalize -> validations ->
aggregate -> final. ``mapper``, ``corpus``, ``canonicalize``, ``aggregate``,
and ``final`` are serial; ``scans`` and ``validations`` run as sliding-window
parallel phases. Parallel workers own exclusive output files only; shared
outputs are refreshed by later serial phases (plan sections 9-10).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

PHASE_ORDER = ("mapper", "corpus", "scans", "canonicalize", "validations", "aggregate", "final")
SERIAL_PHASES = ("mapper", "corpus", "canonicalize", "aggregate", "final")
PARALLEL_PHASES = ("scans", "validations")

SERIAL_PROMPTS = {
    "mapper": "00-protocol-mapper.md",
    "corpus": "05-corpus-pattern-search.md",
    "canonicalize": "80-canonicalize-candidates.md",
    "aggregate": "95-aggregate-validated-findings.md",
    "final": "99-final-coverage-pass.md",
}

# Primary outputs used as completion artifacts when gating a phase advance
# (plan section 28). Serial phases list their shared outputs; parallel tasks
# carry their exclusive output per task.
SERIAL_OUTPUTS = {
    "mapper": ("repo-context.md", "feature-coverage.md", "verification-log.md"),
    "corpus": ("corpus-match-index.md",),
    "canonicalize": ("candidate-index.md", "rejected-candidates.md"),
    "aggregate": ("candidate-index.md", "rejected-candidates.md", "FINAL_AUDIT_REPORT.md"),
    "final": ("final-coverage-report.md",),
}


@dataclass
class TaskSpec:
    phase: str
    name: str
    prompt: Path
    outputs: list[Path] = field(default_factory=list)
    templates: list[Path | None] = field(default_factory=list)
    parallel: bool = False

    @property
    def task_id(self) -> str:
        return f"{self.phase}/{self.name}"

    def to_dict(self) -> dict:
        return {
            "id": self.task_id,
            "phase": self.phase,
            "parallel": self.parallel,
            "prompt": str(self.prompt),
            "outputs": [str(path) for path in self.outputs],
        }


def next_phase(phase: str) -> str | None:
    if phase not in PHASE_ORDER:
        raise ValueError(f"unknown phase: {phase}")
    index = PHASE_ORDER.index(phase)
    if index + 1 >= len(PHASE_ORDER):
        return None
    return PHASE_ORDER[index + 1]


def validation_prompt_text(base_prompt: Path, candidate_path: Path) -> str:
    return f"""# Validate Candidate: {candidate_path.name}

Use these inputs:
- `{base_prompt}`
- `{candidate_path}`

Only edit this candidate dossier:
- `{candidate_path}`

Instructions:
1. Read the candidate dossier and the validation prompt.
2. Try to kill the finding first.
3. Fill or revise the candidate dossier with reachability, attacker control, existing checks, compensating controls, impact, severity, and confidence.
4. Do not edit unrelated run files.
5. If the candidate is invalid, mark it clearly and explain the killer evidence.
"""


def phase_tasks(audit_run: Path, phase: str, *, design_root: Path | None = None) -> list[TaskSpec]:
    """Enumerate the tasks of one phase for an audit run.

    ``design_root`` points at the active copied design and supplies template
    baselines used for artifact verification. Validation prompts are generated
    on demand, mirroring the CLI runner.
    """
    audit_run = Path(audit_run)
    prompt_dir = audit_run / "agent-prompts"
    templates_dir = Path(design_root) / "templates" if design_root else None

    def template(name: str) -> Path | None:
        if templates_dir is None:
            return None
        candidate = templates_dir / name
        return candidate if candidate.is_file() else None

    if phase in SERIAL_PHASES:
        prompt = prompt_dir / SERIAL_PROMPTS[phase]
        outputs = [audit_run / name for name in SERIAL_OUTPUTS[phase]]
        templates = [template(f"{name.replace('.md', '')}-template.md") for name in SERIAL_OUTPUTS[phase]]
        if not prompt.is_file():
            return []
        return [TaskSpec(phase, prompt.stem, prompt, outputs, templates, parallel=False)]

    if phase == "scans":
        tasks: list[TaskSpec] = []
        for prompt in sorted(prompt_dir.glob("scan-*.md")):
            stem = prompt.stem[len("scan-"):]
            output = audit_run / f"family-scan-{stem}.md"
            tasks.append(
                TaskSpec(phase, prompt.stem, prompt, [output], [template("family-scan-template.md")], parallel=True)
            )
        return tasks

    if phase == "validations":
        tasks = []
        for candidate in sorted(audit_run.glob("candidate-*.md")):
            if candidate.name == "candidate-index.md":
                continue
            prompt = prompt_dir / "generated-validations" / f"validate-{candidate.stem}.md"
            if not prompt.is_file():
                prompt.parent.mkdir(parents=True, exist_ok=True)
                prompt.write_text(
                    validation_prompt_text(prompt_dir / "90-validate-candidates.md", candidate), encoding="utf-8"
                )
            tasks.append(
                TaskSpec(phase, f"validate-{candidate.stem}", prompt, [candidate], [template("candidate-template.md")], parallel=True)
            )
        return tasks

    raise ValueError(f"unknown phase: {phase}")


def _output_ready(path: Path, template_path: Path | None) -> tuple[bool, str]:
    if not path.is_file():
        return False, f"missing output: {path}"
    try:
        content = path.read_text(encoding="utf-8")
    except OSError as exc:
        return False, f"unreadable output {path}: {exc}"
    if not content.strip():
        return False, f"empty output: {path}"
    if template_path is not None:
        try:
            if content.strip() == template_path.read_text(encoding="utf-8").strip():
                return False, f"template-only output: {path}"
        except OSError:
            pass
    return True, ""


def verify_task_outputs(task: TaskSpec) -> list[str]:
    """Return a list of artifact problems for a completed task (empty = OK)."""
    problems: list[str] = []
    for output, template_path in zip(task.outputs, task.templates):
        ready, reason = _output_ready(output, template_path)
        if not ready:
            problems.append(reason)
    return problems


def verify_phase_outputs(audit_run: Path, phase: str, *, design_root: Path | None = None) -> list[str]:
    """Verify expected outputs of a phase exist and are not placeholders."""
    problems: list[str] = []
    for task in phase_tasks(audit_run, phase, design_root=design_root):
        problems.extend(verify_task_outputs(task))
    if phase == "scans":
        for path in sorted(Path(audit_run).glob("family-scan-*.md")):
            if path.stat().st_size == 0:
                problems.append(f"empty output: {path}")
    return problems
