"""Host-native work queue (plan sections 4, 6, 8, 25-28).

The host backend never launches Codex, Claude, or zCode CLI processes. It
only maintains the pending/running/completed/failed task state and tells the
host agent which prompts to execute with its own subagents. The host agent
implements sliding-window concurrency: it claims tasks with ``next``, runs
them as subagents, reports each result with ``complete``/``fail``, and
immediately claims replacements — Python never waits for workers.

Task state is stored in the same runner-state layout the CLI worker runner
uses, so either backend can resume the other's suite.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from . import scheduler
from . import state as state_store
from .suite import (
    read_json,
    scaffold_suite_item,
    suite_item_dir,
    update_json,
    write_suite_manifest,
    write_suite_readme,
)
from .workspace import utc_now

TASK_SPLIT_ERROR = "task id must look like <phase>/<name>"


class HostQueueError(RuntimeError):
    pass


def _parse_task_id(task_id: str) -> tuple[str, str]:
    phase, sep, name = task_id.partition("/")
    if not sep or not phase or not name:
        raise HostQueueError(f"{TASK_SPLIT_ERROR}: {task_id}")
    return phase, name


def _task_ids(tasks: list[scheduler.TaskSpec]) -> list[str]:
    return [task.task_id for task in tasks]


def _item_manifest_path(suite_dir: Path, index: int, design: str) -> Path:
    return suite_item_dir(suite_dir, index, design) / "item-manifest.json"


def find_active_item(suite_dir: Path, manifest: dict) -> tuple[int, str, dict] | None:
    for index, design in enumerate(manifest.get("designs", []), start=1):
        item = read_json(_item_manifest_path(suite_dir, index, design))
        if item and item.get("audit_status") != "completed":
            return index, design, item
    return None


def _phase_done(audit_run: Path, phase: str, design_root: Path) -> bool:
    tasks = scheduler.phase_tasks(audit_run, phase, design_root=design_root)
    if not tasks:
        return True
    return all(state_store.task_is_completed(audit_run, phase, task.name) for task in tasks)


def _current_phase(audit_run: Path, design_root: Path) -> str:
    for phase in scheduler.PHASE_ORDER:
        if not _phase_done(audit_run, phase, design_root):
            return phase
    return scheduler.PHASE_ORDER[-1]


def _load_item_context(suite_dir: Path) -> dict:
    suite_dir = Path(suite_dir).resolve()
    manifest_path = suite_dir / "suite-manifest.json"
    manifest = read_json(manifest_path)
    if not manifest:
        raise HostQueueError(f"suite manifest not found: {manifest_path}")
    active = find_active_item(suite_dir, manifest)
    if active is None:
        raise HostQueueError("all suite items are already completed")
    index, design, item = active
    audit_run = Path(str(item.get("audit_run", ""))).expanduser().resolve()
    design_root = Path(str(item.get("source_design_dir", ""))).expanduser().resolve()
    if not audit_run.is_dir():
        raise HostQueueError(f"audit run directory missing: {audit_run}")
    settings = manifest.get("settings") or {}
    return {
        "suite_dir": suite_dir,
        "manifest": manifest,
        "manifest_path": manifest_path,
        "index": index,
        "design": design,
        "item": item,
        "item_manifest_path": _item_manifest_path(suite_dir, index, design),
        "audit_run": audit_run,
        "design_root": design_root,
        "max_concurrency": int(settings.get("parallel_jobs") or 3),
    }


def _queue_refresh(context: dict, recover: bool = False) -> dict:
    """Rebuild pending/running/completed lists for the current phase.

    With ``recover=True``, a ``running`` task without a completion marker means
    the previous host session died mid-task, so it returns to ``pending``
    (plan section 27). Normal loads keep running tasks so the active host
    session can still report them with complete/fail.
    """
    audit_run: Path = context["audit_run"]
    phase = context.get("phase")
    if phase is None:
        phase = _current_phase(audit_run, context["design_root"])
    tasks = scheduler.phase_tasks(audit_run, phase, design_root=context["design_root"])
    stored = state_store.read_queue(context["suite_dir"])
    stored_ids = stored if stored.get("design") == context["design"] else {}
    terminal_ids = {entry.get("id") for entry in (*stored_ids.get("failed", []), *stored_ids.get("limit_exhausted", []))}
    pending: list[str] = []
    running: list[str] = []
    completed: list[str] = []
    for task in tasks:
        task_state = state_store.read_task_state(audit_run, phase, task.name)
        status = (task_state or {}).get("status")
        if status == "completed":
            completed.append(task.task_id)
        elif status == "running":
            running.append(task.task_id)
        elif task.task_id not in terminal_ids:
            pending.append(task.task_id)
    if recover:
        for task_id in running:
            _, name = _parse_task_id(task_id)
            state_store.write_task_state(
                audit_run,
                phase,
                name,
                "pending",
                recovered_at_utc=utc_now(),
                note="recovered: previous host session ended while task was running",
            )
            pending.append(task_id)
        running = []
    pending.sort()
    failed = stored_ids.get("failed", [])
    limit_exhausted = stored_ids.get("limit_exhausted", [])
    return state_store.write_queue(
        context["suite_dir"],
        {
            "schema_version": state_store.QUEUE_SCHEMA_VERSION,
            "execution_backend": "host",
            "suite_dir": str(context["suite_dir"]),
            "design": context["design"],
            "item_index": context["index"],
            "audit_run": str(audit_run),
            "design_root": str(context["design_root"]),
            "max_concurrency": context["max_concurrency"],
            "phase": phase,
            "pending": pending,
            "running": running,
            "completed": completed,
            "failed": failed,
            "limit_exhausted": limit_exhausted,
        },
    )


def load_queue(suite_dir: Path, recover: bool = False) -> dict:
    context = _load_item_context(suite_dir)
    queue = state_store.read_queue(context["suite_dir"])
    if (
        queue
        and queue.get("design") == context["design"]
        and queue.get("phase") in scheduler.PHASE_ORDER
    ):
        return _queue_refresh(context | {"phase": queue["phase"]}, recover=recover)
    return _queue_refresh(context, recover=recover)


def _mark_item(context: dict, **updates: object) -> None:
    update_json(context["item_manifest_path"], **updates)


def _suite_update(context: dict, status: str, message: str) -> None:
    manifest = write_suite_manifest(
        context["suite_dir"],
        suite_name=context["manifest"]["suite_name"],
        target=Path(context["manifest"]["target_repo"]),
        designs=list(context["manifest"].get("designs", [])),
        status=status,
        settings=dict(context["manifest"].get("settings") or {}),
        created_at_utc=context["manifest"].get("created_at_utc"),
        message=message,
        work_root=Path(context["manifest"].get("work_root") or "") or None,
        legacy=bool(context["manifest"].get("legacy_layout")),
    )
    write_suite_readme(context["suite_dir"], manifest)


def command_next(suite_dir: Path, limit: int) -> dict:
    context = _load_item_context(suite_dir)
    queue = load_queue(suite_dir)
    phase = queue["phase"]
    serial = phase in scheduler.SERIAL_PHASES
    capacity = context["max_concurrency"] if not serial else 1
    running = queue["running"]
    room = max(capacity - len(running), 0)
    count = max(min(limit if limit > 0 else capacity, room), 0)
    claimed: list[dict] = []
    pending = list(queue["pending"])
    while count > 0 and pending:
        task_id = pending.pop(0)
        task_phase, name = _parse_task_id(task_id)
        spec = next(
            (task for task in scheduler.phase_tasks(context["audit_run"], task_phase, design_root=context["design_root"]) if task.name == name),
            None,
        )
        if spec is None:
            continue
        state_store.write_task_state(
            context["audit_run"],
            task_phase,
            name,
            "running",
            prompt=str(spec.prompt),
            outputs=[str(path) for path in spec.outputs],
            started_at_utc=utc_now(),
            model="inherit",
        )
        claimed.append(spec.to_dict() | {"instruction": _task_instruction(spec, context)})
        count -= 1
    if claimed:
        _mark_item(context, audit_status="running", status="audit_running")
    queue["pending"] = pending
    queue["running"] = running + [task["id"] for task in claimed]
    state_store.write_queue(suite_dir, queue)
    return {
        "claimed": claimed,
        "phase": phase,
        "parallel": not serial,
        "max_concurrency": context["max_concurrency"],
        "pending": pending,
        "running": queue["running"],
        "hint": (
            "run each claimed prompt with a host subagent (model inherits the host selection); "
            "after each subagent finishes, report with complete/fail and call next again "
            "(sliding window: never wait for all workers before claiming more)"
            if claimed
            else "no task claimed; if pending/running are empty and outputs exist, run `advance`"
        ),
    }


def _task_instruction(spec: scheduler.TaskSpec, context: dict) -> str:
    outputs = ", ".join(f"`{path}`" for path in spec.outputs) or "the outputs named in the prompt"
    return (
        f"Run a host-native subagent on prompt `{spec.prompt}` with the model inherited from the host. "
        f"The subagent may read the target repo, the active design copy, the active audit run, and corpus inputs; "
        f"it must only write {outputs}. Never launch the codex or claude CLI."
    )


def _find_task(context: dict, phase: str, name: str) -> scheduler.TaskSpec | None:
    return next(
        (task for task in scheduler.phase_tasks(context["audit_run"], phase, design_root=context["design_root"]) if task.name == name),
        None,
    )


def _finish_task(suite_dir: Path, task_id: str, status: str, reason: str, note: str = "") -> dict:
    context = _load_item_context(suite_dir)
    queue = load_queue(suite_dir)
    if task_id not in queue["running"]:
        raise HostQueueError(f"task is not running in the current queue: {task_id}")
    phase, name = _parse_task_id(task_id)
    spec = _find_task(context, phase, name)
    problems: list[str] = []
    if status == "completed":
        if spec is None:
            problems.append(f"task no longer discoverable in phase {phase}")
        else:
            problems = scheduler.verify_task_outputs(spec)
        if problems:
            raise HostQueueError(
                "completion artifacts missing for "
                + task_id
                + ": "
                + "; ".join(problems)
                + " — fix the outputs, or report `fail` with a reason"
            )
    extra: dict = {"completed_at_utc": utc_now()}
    if note:
        extra["note"] = note
    if reason:
        extra["reason"] = reason
    state_store.write_task_state(context["audit_run"], phase, name, status, **extra)
    queue["running"] = [item for item in queue["running"] if item != task_id]
    if status == "completed":
        queue["completed"] = sorted(set(queue.get("completed", []) + [task_id]))
    elif status == "failed":
        queue["failed"] = [entry for entry in queue.get("failed", []) if entry.get("id") != task_id] + [
            {"id": task_id, "reason": reason or "unspecified"}
        ]
    elif status == "limit_exhausted":
        queue["limit_exhausted"] = [
            entry for entry in queue.get("limit_exhausted", []) if entry.get("id") != task_id
        ] + [{"id": task_id, "reason": reason or "worker limits exhausted"}]
    state_store.write_queue(suite_dir, queue)
    if status == "limit_exhausted":
        _mark_item(context, audit_status="limit_exhausted", status="limit_exhausted")
        _suite_update(context, "limit_exhausted", f"Host workers reported exhausted limits on {task_id}.")
    return {"task": task_id, "status": status, "queue": _public_queue(queue)}


def _public_queue(queue: dict) -> dict:
    return {key: queue.get(key, []) for key in ("phase", "pending", "running", "completed", "failed", "limit_exhausted")}


def command_advance(suite_dir: Path) -> dict:
    context = _load_item_context(suite_dir)
    queue = load_queue(suite_dir)
    phase = queue["phase"]
    if queue["pending"] or queue["running"]:
        raise HostQueueError(
            f"phase `{phase}` still has pending/running tasks: {queue['pending'] + queue['running']}"
        )
    if queue.get("limit_exhausted"):
        raise HostQueueError(
            f"phase `{phase}` has limit-exhausted tasks: requeue or resolve them before advancing"
        )
    problems = scheduler.verify_phase_outputs(context["audit_run"], phase, design_root=context["design_root"])
    failed = queue.get("failed", [])
    if problems:
        raise HostQueueError("output completeness check failed: " + "; ".join(problems))
    next_phase = scheduler.next_phase(phase)
    if next_phase is not None:
        state_store.write_queue(suite_dir, queue | {"phase": next_phase})
        return {"advanced": True, "from_phase": phase, "to_phase": next_phase, "failed_recorded": failed}

    _mark_item(
        context,
        audit_status="completed",
        status="audit_completed",
        audit_completed_at_utc=utc_now(),
    )
    manifest = context["manifest"]
    remaining = [
        design
        for index, design in enumerate(manifest.get("designs", []), start=1)
        if read_json(_item_manifest_path(suite_dir, index, design)).get("audit_status") != "completed"
    ]
    if remaining:
        next_design = remaining[0]
        next_index = manifest.get("designs", []).index(next_design) + 1
        next_manifest_path = _item_manifest_path(suite_dir, next_index, next_design)
        if next_manifest_path.is_file():
            next_item = read_json(next_manifest_path)
        else:
            _, _, audit_run_next = scaffold_suite_item(
                suite_dir=suite_dir,
                index=next_index,
                design_name=next_design,
                target=Path(manifest["target_repo"]),
                settings=dict(manifest.get("settings") or {}),
                force=False,
                legacy_layout=bool(manifest.get("legacy_layout")),
            )
            next_item = read_json(next_manifest_path)
            next_item["audit_run"] = str(audit_run_next)
        state_store.write_queue(
            suite_dir,
            queue
            | {
                "design": next_design,
                "item_index": next_index,
                "audit_run": next_item.get("audit_run", ""),
                "design_root": next_item.get("source_design_dir", ""),
                "phase": scheduler.PHASE_ORDER[0],
                "pending": [],
                "running": [],
                "completed": [],
                "failed": [],
                "limit_exhausted": [],
            },
        )
        _suite_update(context, "running", f"Completed `{context['design']}`; continuing with `{next_design}`.")
        return {"advanced": True, "completed_design": context["design"], "next_design": next_design, "to_phase": scheduler.PHASE_ORDER[0]}
    state_store.write_queue(
        suite_dir,
        queue | {"phase": "completed", "pending": [], "running": [], "failed": [], "limit_exhausted": []},
    )
    _suite_update(context, "completed", "Blind suite completed via host-native execution.")
    return {"advanced": True, "completed_design": context["design"], "suite_completed": True}


def command_requeue(suite_dir: Path, task_id: str) -> dict:
    context = _load_item_context(suite_dir)
    queue = load_queue(suite_dir)
    phase, name = _parse_task_id(task_id)
    known = [entry for entry in (*queue.get("failed", []), *queue.get("limit_exhausted", [])) if entry.get("id") == task_id]
    if not known:
        raise HostQueueError(f"task is not in failed/limit_exhausted state: {task_id}")
    state_store.write_task_state(context["audit_run"], phase, name, "pending", requeued_at_utc=utc_now())
    queue["failed"] = [entry for entry in queue.get("failed", []) if entry.get("id") != task_id]
    queue["limit_exhausted"] = [entry for entry in queue.get("limit_exhausted", []) if entry.get("id") != task_id]
    queue["pending"] = sorted(set(queue.get("pending", []) + [task_id]))
    state_store.write_queue(suite_dir, queue)
    return {"task": task_id, "status": "pending", "queue": _public_queue(queue)}


def command_status(suite_dir: Path) -> dict:
    context = _load_item_context(suite_dir)
    queue = load_queue(suite_dir)
    return {
        "suite_dir": str(context["suite_dir"]),
        "design": context["design"],
        "item_index": context["index"],
        "audit_run": str(context["audit_run"]),
        "phase": queue["phase"],
        "max_concurrency": context["max_concurrency"],
        "execution_backend": "host",
        **_public_queue(queue),
    }


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="host-runner",
        description=(
            "Drive a host-native blind suite: claim prompts for host subagents, report "
            "results, and advance phases. Never launches Codex/Claude CLI workers."
        ),
    )
    parser.add_argument("suite_dir", help="Suite directory under the target's .dlt-auditor-work/")
    sub = parser.add_subparsers(dest="command", required=True)
    p_next = sub.add_parser("next", help="Claim the next tasks for host subagents.")
    p_next.add_argument("--limit", type=int, default=0, help="Maximum tasks to claim (default: fill the concurrency window).")
    p_complete = sub.add_parser("complete", help="Mark a running task completed after its subagent finished.")
    p_complete.add_argument("task_id")
    p_complete.add_argument("--note", default="")
    p_fail = sub.add_parser("fail", help="Mark a running task failed with an explicit reason.")
    p_fail.add_argument("task_id")
    p_fail.add_argument("--reason", required=True)
    p_limit = sub.add_parser("limit-exhausted", help="Report host worker limits as exhausted for a task.")
    p_limit.add_argument("task_id")
    p_limit.add_argument("--reason", default="")
    p_requeue = sub.add_parser("requeue", help="Move a failed or limit-exhausted task back to pending.")
    p_requeue.add_argument("task_id")
    sub.add_parser("recover", help="Reset stale running tasks to pending.")
    p_advance = sub.add_parser("advance", help="Verify phase outputs and move to the next phase or design.")
    sub.add_parser("status", help="Print the current queue as JSON.")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    suite_dir = Path(args.suite_dir).expanduser().resolve()
    try:
        if args.command == "next":
            payload = command_next(suite_dir, args.limit)
        elif args.command == "complete":
            payload = _finish_task(suite_dir, args.task_id, "completed", "", args.note)
        elif args.command == "fail":
            payload = _finish_task(suite_dir, args.task_id, "failed", args.reason)
        elif args.command == "limit-exhausted":
            payload = _finish_task(suite_dir, args.task_id, "limit_exhausted", args.reason)
        elif args.command == "requeue":
            payload = command_requeue(suite_dir, args.task_id)
        elif args.command == "recover":
            payload = {"queue": _public_queue(load_queue(suite_dir, recover=True)), "recovered": True}
        elif args.command == "advance":
            payload = command_advance(suite_dir)
        else:
            payload = command_status(suite_dir)
    except HostQueueError as exc:
        print(json.dumps({"ok": False, "error": str(exc)}, indent=2))
        return 2
    print(json.dumps(payload | {"ok": True}, indent=2, default=str))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
