#!/usr/bin/env python3
"""Portable, explicit queue runner for challenge experiments.

The heartbeat never chooses scientific work. It executes only jobs explicitly
enqueued beneath an experiment's run folder, keeps a small durable process
record in ``runtime/heartbeats/``, and renders its queue into ``dashboard.md``.
It works with any harness because each queued job owns its exact command.
"""

from __future__ import annotations

import argparse
import json
import os
import signal
import subprocess
import sys
import time
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parent.parent
STOP_REQUESTED = False
DEFAULT_INTERVAL_SECONDS = 120
MAX_INTERVAL_SECONDS = 120


def env_file_value(name: str) -> str | None:
    """Read one non-exported setting from the repository's private .env."""
    try:
        lines = (ROOT / ".env").read_text().splitlines()
    except OSError:
        return None
    for raw_line in lines:
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        if key.strip() == name:
            return value.strip().strip('"').strip("'")
    return None


def runtime_dir() -> Path:
    value = os.environ.get("MIAgent_RUNTIME_DIR") or env_file_value("MIAgent_RUNTIME_DIR")
    return Path(value).expanduser().resolve() if value else ROOT.parent / "MIAgent_runtime_v35"


def normalize_interval(interval: int) -> int:
    """Keep local queue reconciliation responsive to dependent jobs."""
    if interval < 5:
        raise RuntimeError("interval must be at least 5 seconds")
    if interval > MAX_INTERVAL_SECONDS:
        print(
            f"requested interval {interval}s exceeds the local queue maximum; "
            f"using {MAX_INTERVAL_SECONDS}s",
            file=sys.stderr,
        )
        return MAX_INTERVAL_SECONDS
    return interval


def read_json(path: Path, fallback: dict[str, Any] | None = None) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text())
        return value if isinstance(value, dict) else (fallback or {})
    except (OSError, json.JSONDecodeError):
        return fallback or {}


def write_json(path: Path, value: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n")


def challenge_path(name: str) -> Path:
    path = (ROOT / "challenge" / name).resolve()
    if not path.is_dir() or path.parent != (ROOT / "challenge").resolve():
        raise RuntimeError(f"unknown challenge: {name}")
    return path


def heartbeat_dir(challenge: str) -> Path:
    return runtime_dir() / "heartbeats" / challenge


def heartbeat_state_path(challenge: str) -> Path:
    return heartbeat_dir(challenge) / "state.json"


def external_gpu_job_active() -> bool:
    """Keep the queue behind any miagent-local job launched outside heartbeat."""
    gpu_state = read_json(runtime_dir() / "locks" / "gpu0.state.json")
    return bool(gpu_state and pid_alive(gpu_state.get("host_pid")))


def pid_alive(pid: int | None) -> bool:
    if not pid or pid <= 0:
        return False
    try:
        os.kill(pid, 0)
    except OSError:
        return False
    return True


def job_paths(challenge: str) -> list[Path]:
    return sorted(challenge_path(challenge).glob("baselines/*/runs/*/job.json"))


def load_jobs(challenge: str) -> list[tuple[Path, dict[str, Any]]]:
    return [(path, read_json(path)) for path in job_paths(challenge)]


def relative_to_challenge(path: Path, challenge: str) -> str:
    try:
        return path.resolve().relative_to(challenge_path(challenge)).as_posix()
    except ValueError:
        return str(path)


def markdown_cell(value: object) -> str:
    return str(value).replace("|", "\\|").replace("\n", " ")


def render_dashboard(challenge: str) -> None:
    root = challenge_path(challenge)
    dashboard = root / "dashboard.md"
    if not dashboard.is_file():
        raise RuntimeError(f"missing dashboard: {dashboard}")
    jobs = load_jobs(challenge)
    lines = [
        "<!-- challenge heartbeat: begin -->",
        "## Runtime Queue",
        "",
        "This generated section reflects explicitly enqueued jobs. The heartbeat executes no work that is not represented by an experiment `job.json` and linked design.",
        "",
        "| Experiment | State | Command / purpose | Design |",
        "|---|---|---|---|",
    ]
    if jobs:
        for path, job in jobs:
            experiment = markdown_cell(job.get("experiment", path.parent.name))
            state = markdown_cell(job.get("state", "unknown"))
            purpose = markdown_cell(job.get("purpose", "not recorded"))
            design = str(job.get("design", ""))
            design_path = path.parent / design if design else None
            if design and design_path and design_path.is_file():
                design_cell = f"[design]({relative_to_challenge(design_path, challenge)})"
            else:
                design_cell = "not recorded"
            lines.append(f"| `{experiment}` | {state} | {purpose} | {design_cell} |")
    else:
        lines.append("| — | idle | no queued jobs | — |")
    state = read_json(heartbeat_state_path(challenge))
    if state:
        lines.extend(("", f"Heartbeat state: `{markdown_cell(state.get('status', 'unknown'))}`; last pulse `{markdown_cell(state.get('last_pulse_utc', 'not recorded'))}`."))
    lines.extend(("", "<!-- challenge heartbeat: end -->", ""))
    generated = "\n".join(lines)
    original = dashboard.read_text()
    begin, end = "<!-- challenge heartbeat: begin -->", "<!-- challenge heartbeat: end -->"
    start, finish = original.find(begin), original.find(end)
    if start >= 0 and finish >= start:
        updated = original[:start].rstrip() + "\n\n" + generated + original[finish + len(end):].lstrip()
    else:
        telemetry = original.find("<!-- MIAgent runtime telemetry: begin -->")
        if telemetry >= 0:
            updated = original[:telemetry].rstrip() + "\n\n" + generated + "\n" + original[telemetry:]
        else:
            updated = original.rstrip() + "\n\n" + generated
    dashboard.write_text(updated)


def utc_now() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())


def update_job(path: Path, **changes: Any) -> dict[str, Any]:
    job = read_json(path)
    job.update(changes)
    write_json(path, job)
    return job


def replacement_job(existing: dict[str, Any], replacement: dict[str, Any]) -> dict[str, Any]:
    """Preserve prior stage/job evidence when an experiment advances stages."""
    history = list(existing.get("execution_history", []))
    prior = {key: value for key, value in existing.items() if key != "execution_history"}
    if prior:
        history.append(prior)
    if history:
        replacement["execution_history"] = history
    return replacement


def job_key(path: Path, job: dict[str, Any]) -> str:
    return f"{job.get('baseline', path.parents[2].name)}/{job.get('experiment', path.parent.name)}"


def next_queued_job(challenge: str) -> tuple[Path, dict[str, Any]] | None:
    jobs = load_jobs(challenge)
    states = {job_key(path, job): str(job.get("state", "unknown")) for path, job in jobs}
    queued = []
    for path, job in jobs:
        if job.get("state") != "queued":
            continue
        dependencies = job.get("depends_on", [])
        if not isinstance(dependencies, list) or not all(isinstance(item, str) for item in dependencies):
            continue
        if all(states.get(item) == "completed" for item in dependencies):
            queued.append((path, job))
    return min(queued, key=lambda item: float(item[1].get("queued_at", 0.0)), default=None)


def pulse(
    challenge: str,
    active: dict[Path, tuple[subprocess.Popen[str] | None, bool, int]],
    *,
    launch_queued: bool = True,
    max_concurrent: int = 1,
) -> dict[Path, tuple[subprocess.Popen[str] | None, bool, int]]:
    state_path = heartbeat_state_path(challenge)
    state = read_json(state_path)
    state["last_pulse_utc"] = utc_now()
    for active_job_path, (process, _, pid) in list(active.items()):
        result = process.poll() if process is not None else None
        if process is None and not pid_alive(pid):
            run_record = read_json(active_job_path.parent / "run.json")
            recorded_return = run_record.get("return_code")
            result = int(recorded_return) if isinstance(recorded_return, int) else None
            if result is None:
                update_job(active_job_path, state="exited_unverified", finished_at=utc_now())
                active.pop(active_job_path)
                continue
        if result is not None:
            update_job(active_job_path, state="completed" if result == 0 else "failed", return_code=result, finished_at=utc_now())
            active.pop(active_job_path)

    # Preserve compatibility with a daemon started before parallel queue
    # support. A restarted daemon must not guess an unavailable return code.
    legacy_job_path = Path(state["active_job_path"]) if state.get("active_job_path") else None
    if not active and legacy_job_path and not pid_alive(state.get("active_job_pid")):
        # A daemon restart cannot recover the child return code. Preserve this
        # as evidence for a human rather than guessing success.
        update_job(legacy_job_path, state="exited_unverified", finished_at=utc_now())
        state.pop("active_job_path", None)
        state.pop("active_job_pid", None)

    while launch_queued and len(active) < max_concurrent and not state.get("active_job_path") and not external_gpu_job_active():
        candidate = next_queued_job(challenge)
        if candidate is None:
            break
        path, job = candidate
        command = job.get("command")
        if not isinstance(command, list) or not command or not all(isinstance(item, str) for item in command):
            update_job(path, state="blocked", blocker="job command must be a non-empty string list")
            continue
        shared = "--shared-gpu" in command
        if active and (not shared or not all(is_shared for _, is_shared, _ in active.values())):
            break
        log_path = path.parent / "logs" / "heartbeat-command.log"
        log_path.parent.mkdir(parents=True, exist_ok=True)
        log = log_path.open("a")
        process = subprocess.Popen(command, cwd=ROOT, stdout=log, stderr=subprocess.STDOUT, text=True, start_new_session=True)
        log.close()
        active[path] = (process, shared, process.pid)
        update_job(path, state="running", started_at=utc_now(), heartbeat_pid=os.getpid(), command_pid=process.pid)

    if active:
        state["active_jobs"] = [
            {"path": str(path), "pid": pid, "shared_gpu": shared}
            for path, (_, shared, pid) in active.items()
        ]
    else:
        state.pop("active_jobs", None)
    write_json(state_path, state)
    render_dashboard(challenge)
    return active


def run_daemon(challenge: str, interval: int, max_concurrent: int) -> int:
    global STOP_REQUESTED

    interval = normalize_interval(interval)
    if max_concurrent < 1:
        raise RuntimeError("max concurrent jobs must be at least 1")

    def stop_handler(_signum: int, _frame: object) -> None:
        globals()["STOP_REQUESTED"] = True

    signal.signal(signal.SIGTERM, stop_handler)
    signal.signal(signal.SIGINT, stop_handler)
    state_path = heartbeat_state_path(challenge)
    state = read_json(state_path)
    state.update({"status": "running", "heartbeat_pid": os.getpid(), "interval_seconds": interval, "max_concurrent": max_concurrent, "started_at": utc_now()})
    write_json(state_path, state)
    active: dict[Path, tuple[subprocess.Popen[str] | None, bool, int]] = {}
    recovery_items = list(state.get("active_jobs", []))
    known_paths = {str(item.get("path")) for item in recovery_items if isinstance(item, dict)}
    for path, job in load_jobs(challenge):
        if job.get("state") != "running" or str(path) in known_paths:
            continue
        recovery_items.append({
            "path": str(path),
            "pid": job.get("command_pid"),
            "shared_gpu": "--shared-gpu" in job.get("command", []),
        })
    for item in recovery_items:
        if not isinstance(item, dict) or not item.get("path"):
            continue
        path = Path(str(item["path"]))
        try:
            pid = int(item.get("pid"))
        except (TypeError, ValueError):
            continue
        if read_json(path).get("state") == "running" and pid_alive(pid):
            active[path] = (None, bool(item.get("shared_gpu")), pid)
    while not STOP_REQUESTED:
        active = pulse(challenge, active, max_concurrent=max_concurrent)
        for _ in range(interval):
            if STOP_REQUESTED:
                break
            time.sleep(1)
    state = read_json(state_path)
    state.update({"status": "stopped", "stopped_at": utc_now()})
    state.pop("heartbeat_pid", None)
    write_json(state_path, state)
    render_dashboard(challenge)
    return 0


def command_enqueue(args: argparse.Namespace) -> int:
    root = challenge_path(args.challenge)
    baseline = args.baseline
    experiment = args.experiment
    run_dir = root / "baselines" / baseline / "runs" / experiment
    design = run_dir / args.design
    if not design.is_file():
        raise RuntimeError(f"queued job requires an existing design: {design}")
    command = list(args.command)
    if command[:1] == ["--"]:
        command = command[1:]
    if not command:
        raise RuntimeError("enqueue requires a command after --")
    path = run_dir / "job.json"
    existing = read_json(path) if path.exists() else {}
    if existing.get("state") == "running":
        raise RuntimeError(f"cannot replace running job: {path}")
    payload = {"challenge": args.challenge, "baseline": baseline, "experiment": experiment, "design": args.design, "purpose": args.purpose, "depends_on": list(args.depends_on), "command": command, "state": "queued", "queued_at": time.time(), "queued_at_utc": utc_now()}
    write_json(path, replacement_job(existing, payload))
    render_dashboard(args.challenge)
    return 0


def command_start(args: argparse.Namespace) -> int:
    challenge_path(args.challenge)
    interval = normalize_interval(args.interval)
    state_path = heartbeat_state_path(args.challenge)
    existing = read_json(state_path)
    if existing.get("status") == "running" and pid_alive(existing.get("heartbeat_pid")):
        raise RuntimeError(f"heartbeat already running as PID {existing['heartbeat_pid']}")
    log_path = heartbeat_dir(args.challenge) / "heartbeat.log"
    log_path.parent.mkdir(parents=True, exist_ok=True)
    with log_path.open("a") as log:
        process = subprocess.Popen([sys.executable, str(Path(__file__).resolve()), "run", "--challenge", args.challenge, "--interval", str(interval), "--max-concurrent", str(args.max_concurrent)], cwd=ROOT, stdin=subprocess.DEVNULL, stdout=log, stderr=subprocess.STDOUT, text=True, start_new_session=True)
    write_json(state_path, {"status": "starting", "heartbeat_pid": process.pid, "interval_seconds": interval, "max_concurrent": args.max_concurrent, "started_at": utc_now()})
    print(f"Started heartbeat PID {process.pid}; log: {log_path}")
    return 0


def command_stop(args: argparse.Namespace) -> int:
    state_path = heartbeat_state_path(args.challenge)
    state = read_json(state_path)
    pid = state.get("heartbeat_pid")
    if pid_alive(pid):
        os.kill(int(pid), signal.SIGTERM)
    state.update({"status": "stopping" if pid else "stopped", "stop_requested_at": utc_now()})
    write_json(state_path, state)
    render_dashboard(args.challenge)
    print("Heartbeat stop requested. Active job, if any, is intentionally left running.")
    return 0


def command_status(args: argparse.Namespace) -> int:
    state = read_json(heartbeat_state_path(args.challenge))
    print(json.dumps({"heartbeat": state or {"status": "not_started"}, "jobs": [job for _, job in load_jobs(args.challenge)]}, indent=2, sort_keys=True))
    return 0


def command_once(args: argparse.Namespace) -> int:
    """Refresh dashboard/state without starting an experiment."""
    state = read_json(heartbeat_state_path(args.challenge))
    # A manual refresh must not replace the durable identity of a live daemon.
    # Otherwise subsequent status/stop calls point at the short-lived `once`
    # process even though the daemon is still monitoring active jobs.
    if state.get("status") == "running" and pid_alive(state.get("heartbeat_pid")):
        pulse(args.challenge, {}, launch_queued=False)
        return 0
    state.update({"status": "manual_pulse", "heartbeat_pid": os.getpid()})
    write_json(heartbeat_state_path(args.challenge), state)
    pulse(args.challenge, {}, launch_queued=False)
    return 0


def parser() -> argparse.ArgumentParser:
    result = argparse.ArgumentParser(description=__doc__)
    commands = result.add_subparsers(dest="action", required=True)
    for name, handler in (("start", command_start), ("stop", command_stop), ("status", command_status), ("once", command_once)):
        child = commands.add_parser(name)
        child.add_argument("--challenge", required=True)
        if name == "start":
            child.add_argument("--interval", type=int, default=DEFAULT_INTERVAL_SECONDS)
            child.add_argument("--max-concurrent", type=int, default=1)
        child.set_defaults(handler=handler)
    run = commands.add_parser("run", help="Foreground daemon used by start.")
    run.add_argument("--challenge", required=True)
    run.add_argument("--interval", type=int, default=DEFAULT_INTERVAL_SECONDS)
    run.add_argument("--max-concurrent", type=int, default=1)
    run.set_defaults(handler=lambda args: run_daemon(args.challenge, args.interval, args.max_concurrent))
    enqueue = commands.add_parser("enqueue", help="Queue one explicitly designed experiment.")
    enqueue.add_argument("--challenge", required=True)
    enqueue.add_argument("--baseline", required=True)
    enqueue.add_argument("--experiment", required=True)
    enqueue.add_argument("--design", default="design.md")
    enqueue.add_argument("--purpose", required=True)
    enqueue.add_argument("--depends-on", action="append", default=[], help="Require a canonical baseline/experiment job to complete first; repeatable.")
    enqueue.add_argument("command", nargs=argparse.REMAINDER)
    enqueue.set_defaults(handler=command_enqueue)
    return result


def main() -> int:
    args = parser().parse_args()
    try:
        return int(args.handler(args))
    except RuntimeError as exc:
        print(f"challenge-heartbeat: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
