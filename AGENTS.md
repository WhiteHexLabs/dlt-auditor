# DLT Auditor Instructions

This repository is the runtime-focused sibling of `dlt-ai-audit-system`.

Use it to run stable audit designs from `designs/` against target codebases. Do not add back the learning loop, benchmark ground truth, candidate scoring, scorecards, miss analysis, leaderboards, or promotion workflows unless the user explicitly asks to rebuild that separate system.

For one design, scaffold with:

```text
bin/run-design <design-name> /path/to/target-repo --run-name <run-name> --parallel-jobs 3
```

Then execute the generated design run with that design's `bin/run-parallel-workers` (`run-parallel-codex` is a deprecated wrapper). Use `--agent claude` when the user asks for Claude Code instead of Codex.

For multiple designs, use:

```text
bin/run-blind-suite --repo /path/to/target-repo --suite-name <suite-name> --design <design-name> --parallel-jobs 3
```

Suite output lives under `<target-repo>/.dlt-auditor-work/<suite-name>/`. Do not scatter audit artifacts anywhere else in the target repo. Do not modify the target's `.gitignore`; print the hint instead unless the user passes `--update-gitignore`.

When invoked as a Skill inside an agent host, default to host-native execution:

```text
bin/run-blind-suite ... --execution-backend host
```

then drive the host's own subagents with `bin/host-runner <suite-dir> next|complete|fail|advance` (default max concurrency 3, sliding-window refill, inherited host model). Never start the local Codex or Claude CLI in Skill mode unless the user explicitly asks for a CLI backend, and never silently fall back to a CLI backend.

If worker limits are exhausted, preserve the suite and resume it with:

```text
bin/run-blind-suite --suite-name <suite-name> --resume
```

Keep blind audit execution separated from answer-key material. During blind audit execution, do not read known findings, benchmark ground truth, scorecards, miss analyses, result records, leaderboards, refinement plans, audit-output snapshots, candidate result archives, prior round folders, sibling suite outputs (including other suites under `.dlt-auditor-work/`), or stable `designs/*/runs/**` output. Legacy suites under `runs/` resume in place with a warning; never migrate or delete them automatically.

Direct CLI execution defaults to Codex service tier `standard`, reasoning `high` for discovery phases, and reasoning `xhigh` for `canonicalize`, `validations`, `aggregate`, and `final` unless the user asks for a different split. For Claude Code, use `--execution-backend claude` and do not pass Codex reasoning or service-tier overrides.
