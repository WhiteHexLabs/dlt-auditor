# DLT Auditor v1

Runtime-only audit orchestration for trained, specialized DLT audit designs.

This repo intentionally keeps the pieces needed to run existing designs:

- `designs/` - runnable audit prompt packs, each with a `design-profile.md`.
- `corpus/` - shared historical vulnerability corpus used by corpus-aware designs.
- `bin/` - suite/scaffold/queue CLIs.
- `runtime/` - shared Python runtime (workspace, state, scheduler, backends, host queue).
- `tests/` - automated tests for workspace layout, backends, concurrency, resume, and design hygiene.

## How It Works

DLT Auditor runs trained, specialized prompt-pack designs against target repositories.

The main idea is that there is no single audit pipeline that tries to fit every project. Instead, the auditor has multiple prompt-pack designs, and each one is tuned toward a different project family, competition style, or vulnerability class. For a new target, you choose the design or designs that seem most relevant, then run them independently.

![Prompt-pack coverage map](docs/prompt-pack-coverage-map.jpg)

The diagram above is the mental model. A project can contain many different security vulnerabilities, and each prompt pack covers a different part of that space. Running more than one design can broaden coverage, but each design still runs in isolation so its output does not influence the others.

The designs are produced by starting with a default audit design and training it into a specialized prompt pack against a specific audit competition or target class. The AI runs the design, compares the output with confirmed findings, studies what it missed, and refines the prompts. That loop repeats until the prompt pack can identify all or almost all of the confirmed findings. The resulting prompt pack is what this repo runs.

The auditor also uses a dedicated corpus of DLT security fixes. It was built by scanning multiple DLT project GitHub histories and extracting security-relevant fixes, including public fixes, silent fixes, internally identified fixes, and fixes whose security relevance was not disclosed in the original project history. Corpus matches are used as search patterns and hypotheses for the current target. They are not evidence by themselves.

Each design lives under `designs/<name>/` and contains:

- `00_protocol_mapper.md` - map the target protocol and repository structure.
- `01_base_hunter.md` - hunt for issue families.
- `02_validation_and_impact.md` - validate reachability, attacker control, impact, and severity.
- `05_corpus_pattern_search.md` - retrieve historical corpus patterns as hypotheses.
- `design-profile.md` - ecosystem, languages, protocol/execution/consensus models, and focus surfaces used for `optimal` selection and scaffolded coverage seeds. Profile content is hypothesis context only; it is never evidence.
- `prompts/` - focused family scan prompts.
- `bin/dlt-ai-audit-system` - scaffold a concrete audit run.
- `bin/run-parallel-workers` - execute the generated prompts with Codex or Claude CLI workers (`run-parallel-codex` remains as a deprecated wrapper).

## Execution Modes

There are three execution backends:

```text
host    the calling agent host's own subagents execute every prompt;
        no local Codex/Claude CLI process is ever started
codex   subprocess Codex CLI workers (default for direct CLI use)
claude  subprocess Claude Code workers
```

- Skill invocation (`$dlt-auditor optimal|max|custom ...`) defaults to `host`.
- Direct CLI invocation defaults to `codex`; pass `--execution-backend claude` or `--execution-backend host` to change it.
- `--agent codex|claude` still works but is deprecated; it maps to the matching CLI backend.

### Host-Native Skill Mode

```bash
bin/run-blind-suite \
  --repo /path/to/target-repo \
  --suite-name my-suite \
  --design monad-c4 \
  --execution-backend host
```

This scaffolds the suite and a pending work queue, then the host agent drives its own subagents:

```bash
bin/host-runner <target>/.dlt-auditor-work/my-suite status
bin/host-runner <target>/.dlt-auditor-work/my-suite next --limit 3
bin/host-runner <target>/.dlt-auditor-work/my-suite complete <task-id>
bin/host-runner <target>/.dlt-auditor-work/my-suite fail <task-id> --reason "..."
bin/host-runner <target>/.dlt-auditor-work/my-suite advance
```

Properties of host-native mode:

- Subagents inherit the host-selected model; nothing pins `gpt-*`/`claude-*` models.
- Default maximum concurrency is 3 subagents (override with `--parallel-jobs`).
- Sliding-window scheduling: the moment one subagent finishes and reports, the freed slot is refilled; the runner never waits for a whole batch.
- Serial phases (`mapper`, `corpus`, `canonicalize`, `aggregate`, `final`) run one task at a time; only `scans` and `validations` parallelize.
- Parallel workers own exclusive output files; shared artifacts are refreshed by later serial phases.
- If the host has no subagent capability, degrade to sequential single-agent execution. Never silently fall back to local Codex/Claude CLIs.

### Codex CLI Mode

```bash
bin/run-blind-suite \
  --repo /path/to/target-repo \
  --suite-name my-suite \
  --design monad-c4 \
  --execution-backend codex \
  --parallel-jobs 3 \
  --service-tier standard \
  --reasoning-effort high \
  --deep-reasoning-effort xhigh \
  --deep-phases canonicalize,validations,aggregate,final
```

No model is passed by default; the Codex CLI keeps its own configured model unless you pass `--model` explicitly.

### Claude Code Mode

```bash
bin/run-blind-suite \
  --repo /path/to/target-repo \
  --suite-name my-suite \
  --design monad-c4 \
  --execution-backend claude \
  --parallel-jobs 3
```

Claude Code uses its own CLI defaults; Codex service-tier and reasoning flags are never passed to Claude. The suite automatically grants Claude access to the target repo and copied design workspace with `--claude-add-dir`.

## Workspace Layout

All runtime artifacts live inside the target repository:

```text
<target-repo>/.dlt-auditor-work/
└── <suite-name>/
    ├── suite-manifest.json
    ├── README.md
    ├── state/                  # host work queue (work-queue.json)
    ├── design-workspaces/      # isolated copies of each design pack
    ├── design-runs/            # 01-<design>/, 02-<design>/ audit runs
    └── logs/
```

Single-design runs scaffolded with `bin/run-design` default to `<target-repo>/.dlt-auditor-work/runs/<run-name>/` (`--runs-dir` overrides).

The target repo root only ever gains the single `.dlt-auditor-work/` directory — no `candidate-*.md`, `family-scan-*.md`, `FINAL_AUDIT_REPORT.md`, `repo-context.md`, or `agent-logs/` files scatter anywhere else. dlt-auditor does not modify the target's `.gitignore` by default; it prints a hint instead. Pass `--update-gitignore` to opt in to appending `.dlt-auditor-work/`.

## Blind Suites And Phases

The blind-suite flow:

1. Select one or more designs with `--design`.
2. Copy each selected design into `<work>/design-workspaces/<design>/design/`, excluding old run output.
3. Scaffold an audit run under `<work>/design-runs/<NN>-<design>/`.
4. Inject blind-isolation instructions into every generated prompt.
5. Execute the phases in order: `mapper`, `corpus`, `scans`, `canonicalize`, `validations`, `aggregate`, `final`.
6. Store per-design results under the suite directory so runs can be resumed without mixing outputs. Designs run sequentially, never in parallel with each other.

The phases are:

- `mapper` - runs `00-protocol-mapper.md`; fills `repo-context.md`, seeds `feature-coverage.md`, and records concrete files, functions, state machines, trust boundaries, tests, and high-risk surfaces.
- `corpus` - runs `05-corpus-pattern-search.md`; searches `corpus/imports/`, records useful and rejected matches in `corpus-match-index.md`, and may create `corpus-pattern-candidates.md`.
- `scans` - runs every focused `scan-*.md` prompt, usually in parallel; each scan inspects one issue family and writes its own `family-scan-*.md`.
- `canonicalize` - runs `80-canonicalize-candidates.md`; deduplicates candidates across scans, assigns stable candidate IDs, updates `candidate-index.md`, and prepares candidates for validation.
- `validations` - runs validation prompts for candidate dossiers, usually in parallel; each validation tries to disprove the candidate first, then records reachability, attacker control, existing checks, impact, severity, and confidence. Each worker edits only its `candidate-<id>.md`.
- `aggregate` - runs `95-aggregate-validated-findings.md`; merges surviving validated candidates into the final report set and updates shared status files.
- `final` - runs `99-final-coverage-pass.md`; checks for uncovered protocol surfaces, weak evidence, unresolved placeholders, and finalizes the coverage/report artifacts.

Blind isolation means a worker may use only the target repository, its copied active design, its active run directory, and explicitly named corpus files. It must not read sibling suite items, other suites under `.dlt-auditor-work/`, legacy `runs/` output, stable `designs/*/runs/**` outputs, previous audit outputs, answer keys, or any other material not explicitly allowed by the generated prompt.

## Concurrency

The default is 3 concurrent workers everywhere (`--parallel-jobs` / `--jobs`). Both the CLI runner and the host queue use sliding-window (FIRST_COMPLETED) scheduling: when one worker finishes, the next task starts immediately instead of waiting for the whole batch.

## Resume

After an interruption or worker-limit exhaustion:

```bash
bin/run-blind-suite --repo /path/to/target-repo --suite-name my-suite --resume
```

Resume re-reads the suite manifest and per-task state (each run's `agent-logs/runner-state/`), skips completed tasks, requeues pending/failed tasks, and resets stale `running` tasks to `pending`. Host suites resume with `--execution-backend host` and continue the `bin/host-runner` loop; the queue skips everything already completed. Add `--scaffold-only` to prepare isolated runs without launching any workers.

## Legacy Runs

Suites created before the work-root change live under `dlt-auditor/runs/<suite-name>/`. Resuming such a suite emits a legacy warning and continues in place without migration or deletion. New suites always default to `<target>/.dlt-auditor-work/`.

## Use As A Skill

This repo is also an agent skill (zCode, Codex, others). The root `SKILL.md` and `agents/openai.yaml` let the host load the DLT Auditor operating rules, choose prompt packs, and run the existing commands in `bin/`.

Install or link this repo as the `dlt-auditor` skill, for example:

```bash
ln -s /path/to/dlt-auditor ~/.zcode/skills/dlt-auditor
```

Then invoke it from host prompts with one of three tiers:

```text
Use $dlt-auditor max on /path/to/target-repo with suite name target-max-01.
Use $dlt-auditor optimal on /path/to/target-repo with suite name target-optimal-01.
Use $dlt-auditor custom on /path/to/target-repo with suite name target-custom-01 using design packs monad-c4 and fuel-core-attackathon.
```

- `max` runs every available prompt pack under `designs/`.
- `optimal` matches the target against each pack's `design-profile.md` and runs at most 5 best-fitting packs.
- `custom` runs exactly the packs named by the user.

Skill invocation defaults to host-native execution: the host's own subagents run the prompts, models are inherited from the host selection, and no local Codex/Claude CLI is started. These tiers are skill behavior, not shell subcommands.

## List Designs

```bash
bin/run-blind-suite --list-designs
```

## Run One Design

Scaffold a run for a single design:

```bash
bin/run-design fuel-core-attackathon /path/to/target-repo \
  --run-name my-audit-run \
  --parallel-jobs 3
```

The run scaffolds under `<target-repo>/.dlt-auditor-work/runs/my-audit-run/`. Execute it with that design's parallel runner:

```bash
designs/fuel-core-attackathon/bin/run-parallel-workers \
  <target-repo>/.dlt-auditor-work/runs/my-audit-run \
  --jobs 3 \
  --service-tier standard \
  --reasoning-effort high \
  --deep-reasoning-effort xhigh \
  --deep-phases canonicalize,validations,aggregate,final
```

To execute that run with Claude Code instead:

```bash
designs/fuel-core-attackathon/bin/run-parallel-workers \
  <target-repo>/.dlt-auditor-work/runs/my-audit-run \
  --agent claude \
  --jobs 3 \
  --claude-add-dir /path/to/target-repo
```

## Search The Corpus

```bash
bin/search-corpus \
  --query "transaction decoder unbounded list resource accounting" \
  --family resource_accounting_and_limits \
  --top-k 10
```

Corpus matches are hypothesis generators only. A finding still needs target-code reachability, attacker capability, a missing property, and concrete impact.

## Development

Run the test suite with:

```bash
python3 -m pytest tests/ -x -q
```

The tests cover workspace isolation under `.dlt-auditor-work/`, host-backend guarantees (no Codex/Claude/zcode CLI invocations), CLI backend command construction, default concurrency and sliding-window behavior, resume semantics, blind isolation between designs, and design-pack template contamination checks.
