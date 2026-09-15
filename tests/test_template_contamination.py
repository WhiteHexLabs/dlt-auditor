"""Design-pack template contamination checks (plan sections 20-22).

Guards against copy-paste leftovers from other projects: XRPL-only markers must
not appear anywhere, and project-name tokens must stay inside their own packs.
"""

from __future__ import annotations

import re
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
DESIGNS = REPO_ROOT / "designs"

# Unambiguously XRPL-specific markers: none of the packs in this repo target XRPL.
XRPL_MARKERS = ("XRP Ledger", "XRPL", "April 2026", "MPT DEX", "Confidential MPT")

# token -> packs allowed to contain it (case-insensitive, word boundary).
PROJECT_TOKENS = {
    "monad": {"monad-c4"},
    "nibiru": {"nibiru-c4"},
    "omni": {"omni-cantina"},
    "fuel": {
        "fuel-core-attackathon",
        "fuel-rs-attackathon",
        "fuel-ts-attackathon",
        "fuel-vm-attackathon",
    },
    "blast": {"blast-cantina"},
}

# Generic security vocabulary that must not be flagged.
ALLOWED_BLAST_PHRASES = ("blast_radius", "blast radius")

SCANNED_SUFFIXES = (".md",)
SCANNED_NAMES = ("dlt-ai-audit-system", "run-parallel-workers", "run-parallel-codex", "search-corpus", "design-profile.md")


def _scanned_files(pack: Path):
    for path in sorted(pack.rglob("*")):
        if path.is_dir():
            continue
        if path.name in SCANNED_NAMES or path.suffix in SCANNED_SUFFIXES:
            if "__pycache__" in path.parts or "runs" in path.parts:
                continue
            yield path


def _strip_allowed(text: str) -> str:
    lowered = text.lower()
    for phrase in ALLOWED_BLAST_PHRASES:
        lowered = lowered.replace(phrase, "")
    return lowered


def test_no_xrpl_markers_in_any_pack() -> None:
    violations = []
    for pack in sorted(DESIGNS.iterdir()):
        if not pack.is_dir():
            continue
        for path in _scanned_files(pack):
            content = path.read_text(encoding="utf-8", errors="ignore")
            for marker in XRPL_MARKERS:
                if marker.lower() in content.lower():
                    violations.append(f"{path.relative_to(DESIGNS)}: {marker}")
    assert not violations, "XRPL template contamination found:\n" + "\n".join(violations)


def test_project_tokens_stay_in_their_packs() -> None:
    violations = []
    for pack in sorted(DESIGNS.iterdir()):
        if not pack.is_dir():
            continue
        for path in _scanned_files(pack):
            content = _strip_allowed(path.read_text(encoding="utf-8", errors="ignore").lower())
            for token, allowed in PROJECT_TOKENS.items():
                if pack.name in allowed:
                    continue
                if re.search(rf"\b{token}\b", content):
                    violations.append(f"{path.relative_to(DESIGNS)}: {token}")
    assert not violations, "cross-project token contamination found:\n" + "\n".join(violations)


def _focus_surfaces(text: str) -> list[str]:
    match = re.search(r"## Focus Surfaces\n(.*?)(?=\n## |\Z)", text, re.S)
    if not match:
        return []
    return [line[2:].strip() for line in match.group(1).splitlines() if line.startswith("- ")]


def test_every_pack_has_design_profile_with_focus_surfaces() -> None:
    for pack in sorted(DESIGNS.iterdir()):
        if not pack.is_dir():
            continue
        profile = pack / "design-profile.md"
        assert profile.is_file(), f"{pack.name}: design-profile.md missing"
        text = profile.read_text(encoding="utf-8")
        assert "hypothesis" in text.lower(), f"{pack.name}: profile must state it is hypothesis context only"
        surfaces = _focus_surfaces(text)
        assert surfaces, f"{pack.name}: no focus surfaces listed"


def test_scaffolded_coverage_comes_from_profile(target_repo: Path) -> None:
    """The scaffolder must seed coverage from the profile, not hardcoded surfaces."""
    import subprocess

    subprocess.run(
        [str(DESIGNS / "monad-c4" / "bin" / "dlt-ai-audit-system"), str(target_repo), "--run-name", "profile-check"],
        check=True,
        capture_output=True,
        text=True,
    )
    run_dir = target_repo / ".dlt-auditor-work" / "runs" / "profile-check"
    autonomous = (run_dir / "agent-prompts" / "00-RUN-AUTONOMOUS-MAX-AUDIT.md").read_text(encoding="utf-8")
    assert "Design profile `monad-c4`" in autonomous
    assert "MonadBFT" in autonomous
    assert "hypothesis context" in autonomous
    coverage = (run_dir / "feature-coverage.md").read_text(encoding="utf-8")
    assert "MonadBFT" in coverage
    for marker in XRPL_MARKERS:
        assert marker.lower() not in coverage.lower()
        assert marker.lower() not in autonomous.lower()
