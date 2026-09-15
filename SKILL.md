---
name: dlt-auditor
description: Run DLT Auditor stable audit designs and blind audit suites against target codebases from this repository. Use when the user asks to run, scaffold, resume, configure, or explain dlt-auditor audit execution, including host-native subagent mode, max, optimal, or custom prompt-pack tiers, Codex and Claude Code CLI execution backends, blind-suite integrity rules, worker-limit recovery, design selection, or the runtime-focused dlt-auditor workflow.
---

# DLT Auditor

Use this repository as the runtime for stable audit designs from `designs/` against target codebases. Run commands from this skill/repository root.

Do not add or reintroduce learning-loop features, benchmark ground truth, candidate scoring, scorecards, miss analysis, leaderboards, promotion workflows, or refinement systems unless the user explicitly asks to rebuild that separate system.

## Execution Modes

When invoked as a Skill inside an agent host (zCode or another):

- Prefer host-native execution: the host agent's own subagents run every audit prompt.
- Never start the local Codex or Claude CLI unless the user explicitly asks for a CLI execution backend.
- Never launch `zcode` from the shell to simulate subagents. Subagents are dispatched by the host agent itself.
- Inherit the host-selected model. Do not pin or override models for subagents.
- Default maximum concurrency is 3 subagents.

If the host has no subagent capability, degrade to sequential single-agent execution of the same prompts. Never silently fall back to local Codex/Claude CLI workers.

Direct CLI use (`bin/run-blind-suite` without a host agent) defaults to `--execution-backend codex`; pass `--execution-backend claude` for Claude Code, or `--execution-backend host` to scaffold a host-driven suite.

## Workspace

All audit output lives inside the target repository:

```text
<target-repo>/.dlt-auditor-work/<suite-name>/
```

Never scatter audit artifacts (`candidate-*.md`, `family-scan-*.md`, `FINAL_AUDIT_REPORT.md`, `repo-context.md`, `agent-logs/`) in the target repo root. By default dlt-auditor does not modify the target's `.gitignore`; it prints a hint instead. Only pass `--update-gitignore` if the user opts in.

Legacy suites under `dlt-auditor/runs/` still resume in place with a warning; never migrate or delete them automatically.

## Blind Integrity

During blind audit execution, keep audit workers separated from answer-key material.

Do not read known findings, benchmark ground truth, scorecards, miss analyses, result records, leaderboards, refinement plans, audit-output snapshots, candidate result archives, prior round folders, sibling suite outputs (including other suites under `.dlt-auditor-work/`), or stable `designs/*/runs/**` output.

Preserve generated suites when worker limits or external interruptions occur. Resume instead of recreating unless the user explicitly asks to replace the suite.

## Tiers

Treat "prompt packs" and "design packs" as the stable design folders under `designs/`.

```text
$dlt-auditor max ...
$dlt-auditor optimal ...
$dlt-auditor custom ...
```

If the target repository or suite name is missing, infer a reasonable suite name from the target basename, tier, and timestamp when possible. Ask only when the target repository path is missing or ambiguous.

### Max

Use every runnable design pack: `bin/run-blind-suite --list-designs`, then one blind suite repeating `--design <name>` per pack. Designs run sequentially, never in parallel with each other.

### Optimal

Select at most 5 packs by matching the target against each pack's `designs/<name>/design-profile.md` (ecosystem, languages, protocol type, execution/consensus model, VM) plus target repo metadata (README, package manifests, lockfiles, dependency names). Do not rely on directory-name guessing as the primary signal. If fewer than 5 packs clearly fit, run only the clear fits and say so.

### Custom

Use exactly the design packs the user names. Validate each exists under `designs/`; if misspelled, list available packs and ask for correction.

## Host-Native Execution Loop

Phase 1 — scaffold (never starts local Codex/Claude):

```bash
bin/run-blind-suite \
  --repo /path/to/target-repo \
  --suite-name <suite> \
  --design <design-name> \
  --execution-backend host
```

This creates `<target>/.dlt-auditor-work/<suite>/`, copies each design into `design-workspaces/`, scaffolds audit runs under `design-runs/`, and initializes `state/work-queue.json`.

Phase 2 — drive the queue with your own subagents:

```bash
bin/host-runner <suite-dir> status
bin/host-runner <suite-dir> next --limit 3
```

Fixed phase order: `mapper`, `corpus`, `scans`, `canonicalize`, `validations`, `aggregate`, `final`. `mapper`/`corpus`/`canonicalize`/`aggregate`/`final` are serial (one task at a time); `scans` and `validations` are parallel.

For every task returned by `next`:

1. Launch one subagent with the task's `prompt` file content as its instructions. The subagent inherits the host model — never pass a model override.
2. The subagent may read the target repo, the active design copy, the active audit run directory, and explicit corpus inputs. It must write only the task's listed `outputs`.
3. Parallel workers own exclusive files: a scan worker edits only its `family-scan-<id>.md`; a validation worker edits only its `candidate-<id>.md`. Shared files (`candidate-index.md`, `rejected-candidates.md`, `FINAL_AUDIT_REPORT.md`, `feature-coverage.md`) are refreshed only by later serial phases.
4. When a subagent finishes, report immediately:

```bash
bin/host-runner <suite-dir> complete <task-id>
bin/host-runner <suite-dir> fail <task-id> --reason "..."
```

5. Then call `next` again right away — sliding window: refill the slot the moment one worker finishes; never wait for the whole batch. Keep at most 3 subagents active (or the user's override).

When a phase has no pending/running tasks, verify and advance:

```bash
bin/host-runner <suite-dir> advance
```

`advance` fails loudly if expected outputs are missing or still template-only; fix or explicitly `fail` the task with a reason first. After the final phase of a design, `advance` scaffolds the next design item automatically; designs never run in parallel.

If host worker limits are exhausted: `bin/host-runner <suite-dir> limit-exhausted <task-id>`, stop, and tell the user to resume later.

## Resume and Recovery

After an interruption (either CLI or Skill):

```bash
bin/run-blind-suite --repo /path/to/target-repo --suite-name <suite> --resume
```

Resume re-reads `suite-manifest.json` and per-task state under each run's `agent-logs/runner-state/`, skips completed tasks, requeues pending/failed tasks, and resets stale `running` tasks to `pending`. For host suites, resume with `--execution-backend host` and continue the host loop; the queue skips everything already completed.

## One Design (CLI mode)

Scaffold a single design run:

```bash
bin/run-design <design-name> /path/to/target-repo --run-name <run-name> --parallel-jobs 3
```

The run lands under `<target-repo>/.dlt-auditor-work/runs/<run-name>/`. Execute it with the design's runner:

```bash
designs/<design-name>/bin/run-parallel-workers designs/<design-name>/runs/<run-name> --jobs 3 --agent codex --service-tier standard --reasoning-effort high --deep-reasoning-effort xhigh --deep-phases canonicalize,validations,aggregate,final
```

`run-parallel-codex` remains as a deprecated wrapper of `run-parallel-workers`. If worker limits are exhausted, preserve the run and resume with `--resume`.

## Blind Suites (CLI mode)

```bash
bin/run-blind-suite --repo /path/to/target-repo --suite-name <suite> --design <design-name> --parallel-jobs 3 --execution-backend codex --service-tier standard --reasoning-effort high --deep-reasoning-effort xhigh --deep-phases canonicalize,validations,aggregate,final
```

Claude Code workers:

```bash
bin/run-blind-suite --repo /path/to/target-repo --suite-name <suite> --design <design-name> --parallel-jobs 3 --execution-backend claude
```

For Claude Code, do not pass Codex reasoning or service-tier overrides. `--agent codex|claude` still works but is deprecated in favor of `--execution-backend`. Use `--scaffold-only` to prepare isolated runs without launching workers, and `--force` only when the user explicitly wants to replace an existing suite or run.
