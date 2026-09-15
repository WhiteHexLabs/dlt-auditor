"""Task state and host work-queue persistence.

Per-task state lives beside each audit run at
``<audit-run>/agent-logs/runner-state/<phase>/<task>.json`` using the same
schema as the CLI worker runner, so host-native and CLI executions of the same
suite can resume each other's work (plan sections 25-27).
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from .workspace import utc_now

TASK_STATUSES = ("pending", "running", "completed", "failed", "blocked", "limit_exhausted")
QUEUE_SCHEMA_VERSION = 1


def sanitize_name(value: str) -> str:
    return "".join(ch if ch.isalnum() or ch in "._-" else "-" for ch in value).strip("-") or "worker"


def runner_state_dir(audit_run: Path) -> Path:
    return Path(audit_run) / "agent-logs" / "runner-state"


def task_state_path(audit_run: Path, phase: str, task: str) -> Path:
    return runner_state_dir(audit_run) / phase / f"{sanitize_name(task)}.json"


def read_task_state(audit_run: Path, phase: str, task: str) -> dict[str, Any] | None:
    path = task_state_path(audit_run, phase, task)
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None


def write_task_state(audit_run: Path, phase: str, task: str, status: str, **extra: Any) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "phase": phase,
        "task": sanitize_name(task),
        "status": status,
        "updated_at_utc": utc_now(),
    }
    payload.update(extra)
    path = task_state_path(audit_run, phase, task)
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp_path = path.with_suffix(".tmp")
    tmp_path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    tmp_path.replace(path)
    return payload


def task_is_completed(audit_run: Path, phase: str, task: str) -> bool:
    state = read_task_state(audit_run, phase, task)
    return bool(state and state.get("status") == "completed")


def read_json_dict(path: Path) -> dict[str, Any]:
    try:
        payload = json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    return payload if isinstance(payload, dict) else {}


def queue_path(suite_dir: Path) -> Path:
    return Path(suite_dir) / "state" / "work-queue.json"


def read_queue(suite_dir: Path) -> dict[str, Any]:
    return read_json_dict(queue_path(suite_dir))


def write_queue(suite_dir: Path, payload: dict[str, Any]) -> dict[str, Any]:
    payload = dict(payload)
    payload["updated_at_utc"] = utc_now()
    path = queue_path(suite_dir)
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp_path = path.with_suffix(".tmp")
    tmp_path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    tmp_path.replace(path)
    return payload
