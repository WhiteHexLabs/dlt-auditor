"""Shared runtime helpers for dlt-auditor.

Splits suite orchestration into focused modules:

- ``workspace``: work-root resolution, legacy ``runs/`` fallback, gitignore hints.
- ``state``: per-task runner state and the host work queue.
- ``scheduler``: audit phase ordering, task discovery, and output gating.
- ``backends``: execution backend selection and CLI worker command building.
- ``hostqueue``: the host-native queue protocol driven by the host agent.
"""
