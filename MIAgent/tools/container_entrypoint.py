#!/usr/bin/env python3
"""Run one MIAgent workload and persist provenance plus local tracking data."""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
import os
import platform
import shutil
import subprocess
import sys
import time
from pathlib import Path
from typing import Any

try:
    from experiment_tracking import is_gpu_metric
except ModuleNotFoundError:  # Imported as ``tools.container_entrypoint`` in host tests.
    from tools.experiment_tracking import is_gpu_metric


EXECUTION_FILES = (
    "run.json",
    "logs/command.log",
    "tracking/dashboard.json",
    "tracking/dashboard.md",
    "tracking/params.json",
    "tracking/tags.json",
    "tracking/description.md",
    "tracking/parameter_descriptions.json",
    "tracking/metrics.jsonl",
    "tracking/dice_summary.json",
    "tracking/telemetry.jsonl",
    "tracking/artifacts.jsonl",
    "output.json",
    "summary.md",
)

def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", nargs=argparse.REMAINDER, help="Workload command after --.")
    args = parser.parse_args()
    if args.command[:1] == ["--"]:
        args.command = args.command[1:]
    if not args.command:
        parser.error("a workload command is required after --")
    return args


def run_dir() -> Path:
    value = os.environ.get("MIAgent_RUN_DIR")
    if not value:
        raise RuntimeError("MIAgent_RUN_DIR must be supplied by tools/miagent_local.py")
    path = Path(value)
    path.mkdir(parents=True, exist_ok=True)
    return path


def command_output(command: list[str]) -> str | None:
    try:
        return subprocess.check_output(command, text=True, stderr=subprocess.STDOUT).strip()
    except (OSError, subprocess.CalledProcessError):
        return None


def provenance(command: list[str]) -> dict[str, Any]:
    try:
        import monai
        import torch

        torch_version = torch.__version__
        cuda_available = torch.cuda.is_available()
        cuda_version = torch.version.cuda
        monai_version = monai.__version__
    except Exception as exc:  # pragma: no cover - preflight verifies imports
        torch_version = cuda_version = monai_version = None
        cuda_available = False
        import_error = repr(exc)
    else:
        import_error = None
    return {
        "started_at": time.time(),
        "command": command,
        "host": platform.node(),
        "python": sys.version,
        "cuda_visible_devices": os.environ.get("CUDA_VISIBLE_DEVICES"),
        "torch": torch_version,
        "torch_cuda": cuda_version,
        "cuda_available": cuda_available,
        "monai": monai_version,
        "nvidia_smi": command_output(["nvidia-smi", "--query-gpu=name,driver_version,memory.total", "--format=csv,noheader"]),
        "import_error": import_error,
        "challenge": os.environ.get("MIAgent_CHALLENGE"),
        "baseline": os.environ.get("MIAgent_BASELINE"),
        "experiment": os.environ.get("MIAgent_EXPERIMENT"),
        "gpu_mode": os.environ.get("MIAgent_GPU_MODE", "exclusive"),
        "gpu_budget_mb": os.environ.get("MIAgent_GPU_BUDGET_MB"),
    }


def read_json(path: Path, fallback: object) -> object:
    try:
        return json.loads(path.read_text())
    except (OSError, json.JSONDecodeError):
        return fallback


def archive_prior_execution(root: Path) -> Path | None:
    """Archive bounded stage evidence before reusing one scientific run folder."""
    prior = read_json(root / "run.json", {})
    if not isinstance(prior, dict) or prior.get("return_code") is None:
        return None
    dashboard = read_json(root / "tracking" / "dashboard.json", {})
    stage = str(dashboard.get("stage", "other")) if isinstance(dashboard, dict) else "other"
    finished = float(prior.get("finished_at") or prior.get("started_at") or time.time())
    stamp = datetime.fromtimestamp(finished, tz=timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    base = root / "execution_history" / f"{stamp}_{stage}"
    archive = base
    suffix = 2
    while archive.exists():
        archive = Path(f"{base}_{suffix}")
        suffix += 1
    copied: list[str] = []
    for relative in EXECUTION_FILES:
        source = root / relative
        if not source.is_file():
            continue
        destination = archive / relative
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, destination)
        copied.append(relative)
    archive.mkdir(parents=True, exist_ok=True)
    (archive / "archive_manifest.json").write_text(json.dumps({"stage": stage, "source_finished_at": finished, "files": copied}, indent=2, sort_keys=True) + "\n")
    for relative in EXECUTION_FILES:
        path = root / relative
        if path.is_file() and relative != "summary.md":
            path.unlink()
    return archive


PARAMETER_DESCRIPTIONS = {
    "baseline": "Baseline implementation identifier within the challenge workspace.",
    "batch_size": "Source images loaded in each DataLoader batch before patch expansion.",
    "cache_rate": "Fraction of the dataset cached in host RAM by the preprocessing pipeline.",
    "challenge": "Challenge workspace identifier.",
    "command": "Exact workload command executed inside the container.",
    "context_slices": "Adjacent axial CT slices provided as 2.5D model input channels.",
    "crop": "Spatial crop or region of interest used for each training sample.",
    "effective_patches": "Forward-pass samples per optimizer update: batch size × patches per image.",
    "experiment": "Unique experiment/run identifier within its baseline.",
    "gpu": "GPU model, driver version, and total visible memory recorded at launch.",
    "gpu_mode": "Exclusive is the default; shared means a bounded low-memory workload was admitted alongside another shared workload.",
    "gpu_budget_mb": "Per-workload GPU-memory admission budget in MiB for a shared-GPU run; GPU telemetry records actual combined use.",
    "learning_rate": "Optimizer learning rate.",
    "optimizer": "Optimization algorithm used to update model weights.",
    "patches_per_image": "Stochastic crops sampled from each source image in a DataLoader item.",
    "train_cases": "Number of distinct patients assigned to the training split.",
    "train_steps_per_epoch": "Optimizer updates performed in one reported training epoch.",
    "validation_cases": "Number of distinct patients in the validation split.",
    "validation_interval_epochs": "Epoch interval between scheduled validation passes.",
    "wall_cap_seconds": "Maximum permitted elapsed wall-clock time for this workload.",
    "weight_decay": "L2-style regularization applied by the optimizer.",
    "runtime.wall_seconds": "End-to-end wall-clock seconds from container entrypoint start to workload exit.",
    "runtime.wall_time": "Human-readable end-to-end wall-clock duration.",
    "runtime.started_at_utc": "UTC timestamp when the container entrypoint started.",
    "runtime.finished_at_utc": "UTC timestamp when the workload completed.",
    "runtime.return_code": "Workload process exit code; zero denotes successful completion.",
    "torch": "PyTorch version in the workload container.",
    "torch_cuda": "CUDA version bundled with the workload PyTorch build.",
    "monai": "MONAI version in the workload container.",
}


def utc_timestamp(seconds: float | None) -> str:
    if seconds is None:
        return "not recorded"
    return datetime.fromtimestamp(float(seconds), tz=timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")


def format_wall_time(seconds: float) -> str:
    elapsed = max(0.0, float(seconds))
    total = round(elapsed)
    hours, remainder = divmod(total, 3600)
    minutes, seconds = divmod(remainder, 60)
    return f"{hours:d}:{minutes:02d}:{seconds:02d} ({elapsed:.1f} s)"


def markdown_cell(value: object) -> str:
    if isinstance(value, (dict, list, tuple)):
        text = json.dumps(value, sort_keys=True)
    else:
        text = str(value)
    return text.replace("|", "\\|").replace("\n", "<br>")


def parameter_label(name: str) -> str:
    return name.replace("_", " ").replace(".", " · ")


def parameter_description(name: str, supplied: dict[str, str]) -> str:
    return supplied.get(name) or PARAMETER_DESCRIPTIONS.get(name) or "Workload-declared parameter; see the experiment description for its role."


def parameter_summary(parameters: dict[str, object]) -> str:
    priority = ("model", "crop", "context_slices", "batch_size", "patches_per_image", "effective_patches", "learning_rate", "cache_rate")
    keys = [key for key in priority if key in parameters]
    if not keys:
        metadata = {"challenge", "baseline", "experiment", "command", "gpu", "torch", "torch_cuda", "monai"}
        keys = [key for key in sorted(parameters) if key not in metadata and not key.startswith("runtime.")][:4]
    if not keys:
        return "no workload parameters emitted"
    return "; ".join(f"{parameter_label(key)}={markdown_cell(parameters[key])}" for key in keys)


def build_mlflow_note(details: dict[str, Any], description: str, parameters: dict[str, object], parameter_notes: dict[str, str]) -> str:
    lines = [
        "## MIAgent run",
        "",
        f"**Stage:** `{os.environ.get('MIAgent_STAGE', 'other')}`  ",
        f"**Wall time:** `{format_wall_time(float(details['wall_seconds']))}`  ",
        f"**Command:** `{' '.join(map(str, details['command']))}`",
    ]
    if description:
        lines.extend(("", description.strip()))
    lines.extend(("", "## Parameters", "", "| Parameter | Value | Description |", "|---|---|---|"))
    for name in sorted(parameters):
        lines.append(
            f"| `{markdown_cell(name)}` | `{markdown_cell(parameters[name])}` | {markdown_cell(parameter_description(name, parameter_notes))} |"
        )
    return "\n".join(lines) + "\n"


def write_run_dashboard(root: Path, details: dict[str, Any], description: str, parameters: dict[str, object], parameter_notes: dict[str, str]) -> None:
    """Persist a self-contained, human-readable run record for the report UI."""
    tracking = root / "tracking"
    tracking.mkdir(parents=True, exist_ok=True)
    status = "completed" if details.get("return_code") == 0 else "failed"
    payload = {
        "challenge": details.get("challenge"),
        "baseline": details.get("baseline"),
        "experiment": details.get("experiment"),
        "stage": os.environ.get("MIAgent_STAGE", "other"),
        "status": status,
        "return_code": details.get("return_code"),
        "started_at": details.get("started_at"),
        "finished_at": details.get("finished_at"),
        "wall_seconds": details.get("wall_seconds"),
        "wall_time": format_wall_time(float(details["wall_seconds"])),
        "command": details.get("command"),
        "parameter_summary": parameter_summary(parameters),
        "parameters": parameters,
    }
    (tracking / "dashboard.json").write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n")
    lines = [
        "# Local Run Dashboard",
        "",
        "| Field | Value |",
        "|---|---|",
        f"| Status | {status} (return code `{details.get('return_code')}`) |",
        f"| Stage | `{payload['stage']}` |",
        f"| Wall time | **{payload['wall_time']}** |",
        f"| Started | {utc_timestamp(details.get('started_at'))} |",
        f"| Finished | {utc_timestamp(details.get('finished_at'))} |",
        f"| Command | `{markdown_cell(' '.join(map(str, details.get('command') or [])))}` |",
    ]
    if description:
        lines.extend(("", "## Experiment Description", "", description.strip()))
    lines.extend(("", "## Parameters", "", "| Parameter | Value | Description |", "|---|---|---|"))
    for name in sorted(parameters):
        lines.append(
            f"| `{markdown_cell(name)}` | `{markdown_cell(parameters[name])}` | {markdown_cell(parameter_description(name, parameter_notes))} |"
        )
    dice_summary = read_json(tracking / "dice_summary.json", {})
    if isinstance(dice_summary, dict) and dice_summary:
        lines.extend(("", "## Latest Dice Summary", "", "| Split / label | Dice | Step |", "|---|---:|---:|"))
        for name in sorted(dice_summary):
            item = dice_summary[name]
            if not isinstance(item, dict):
                continue
            try:
                value = float(item["value"])
                step = int(item["step"])
            except (KeyError, TypeError, ValueError):
                continue
            label = name.replace("training.dice", "train average", 1).replace("validation.dice", "validation average", 1).replace(".", " / ")
            lines.append(f"| {markdown_cell(label)} | {value:.4f} | {step} |")
    (tracking / "dashboard.md").write_text("\n".join(lines) + "\n")


def update_challenge_dashboard(root: Path) -> None:
    """Refresh a generated telemetry table without disturbing authored content."""
    try:
        challenge_root = root.parents[3]
    except IndexError:
        return
    dashboard = challenge_root / "dashboard.md"
    if not dashboard.is_file():
        return
    records: list[dict[str, Any]] = []
    for path in challenge_root.glob("baselines/*/runs/*/tracking/dashboard.json"):
        value = read_json(path, None)
        if isinstance(value, dict):
            value["_path"] = path
            records.append(value)
    records.sort(key=lambda value: float(value.get("finished_at") or value.get("started_at") or 0), reverse=True)
    def latest_metric(tracking: Path, name: str) -> str:
        """Return the latest finite scalar written by the workload, if any."""
        value: float | None = None
        metrics_path = tracking / "metrics.jsonl"
        try:
            for raw_line in metrics_path.read_text().splitlines():
                item = json.loads(raw_line)
                if item.get("name") != name:
                    continue
                candidate = float(item.get("value"))
                if candidate == candidate and candidate not in (float("inf"), float("-inf")):
                    value = candidate
        except (OSError, ValueError, TypeError, json.JSONDecodeError):
            return "—"
        return "—" if value is None else f"{value:.4f}"

    lines = [
        "<!-- MIAgent runtime telemetry: begin -->",
        "## Local Runtime Telemetry",
        "",
        "Automatically generated by the container launcher. Wall time is end-to-end container elapsed time; detailed parameter descriptions are linked per run.",
        "",
        "| Exp | Stage | Status | Train Dice | Val Dice | Wall time | Parameter summary | Details |",
        "|---|---|---|---:|---:|---|---|---|",
    ]
    for value in records:
        path = Path(str(value["_path"]))
        rel = path.parent.relative_to(challenge_root).as_posix()
        experiment = str(value.get("experiment", "experiment"))
        # Keep the overview scannable. The full, immutable run identifier is
        # retained on the linked detail page and in MLflow.
        experiment_label = experiment.split("_", 1)[0] if experiment.startswith("exp") else experiment
        lines.append(
            f"| `{markdown_cell(experiment_label)}` | `{markdown_cell(value.get('stage', 'other'))}` | {markdown_cell(value.get('status', 'unknown'))} | {latest_metric(path.parent, 'training.dice')} | {latest_metric(path.parent, 'validation.dice')} | {markdown_cell(value.get('wall_time', 'not recorded'))} | {markdown_cell(value.get('parameter_summary', 'not recorded'))} | [details]({rel}/dashboard.md) |"
        )
    if not records:
        lines.append("| — | — | no completed container workload yet | — | — | — | — | — |")
    lines.extend(("", "<!-- MIAgent runtime telemetry: end -->", ""))
    generated = "\n".join(lines)
    original = dashboard.read_text()
    begin, end = "<!-- MIAgent runtime telemetry: begin -->", "<!-- MIAgent runtime telemetry: end -->"
    start_index, end_index = original.find(begin), original.find(end)
    if start_index >= 0 and end_index >= start_index:
        updated = original[:start_index].rstrip() + "\n\n" + generated + original[end_index + len(end):].lstrip()
    else:
        updated = original.rstrip() + "\n\n" + generated
    dashboard.write_text(updated)


def run_workload(command: list[str], log_path: Path) -> int:
    with log_path.open("w") as log:
        process = subprocess.Popen(
            command,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            bufsize=1,
            start_new_session=True,
        )
        pid_file_value = os.environ.get("MIAgent_WORKLOAD_PID_FILE", "").strip()
        pid_file = Path(pid_file_value) if pid_file_value else None
        if pid_file:
            pid_file.parent.mkdir(parents=True, exist_ok=True)
            pid_file.write_text(f"{process.pid}\n")
        try:
            assert process.stdout is not None
            for line in process.stdout:
                print(line, end="", flush=True)
                log.write(line)
                log.flush()
            return process.wait()
        finally:
            if pid_file:
                try:
                    pid_file.unlink()
                except FileNotFoundError:
                    pass


def log_tracking_artifacts(root: Path) -> None:
    # Kept local so the lightweight dashboard helpers remain importable from
    # the host launcher, where MLflow is intentionally not installed.
    import mlflow

    for path in (
        root / "run.json",
        root / "logs" / "command.log",
        root / "tracking" / "params.json",
        root / "tracking" / "tags.json",
        root / "tracking" / "description.md",
        root / "tracking" / "parameter_descriptions.json",
        root / "tracking" / "dashboard.json",
        root / "tracking" / "dashboard.md",
        root / "tracking" / "metrics.jsonl",
        root / "output.json",
        root / "summary.md",
        root / "result_viewer.html",
    ):
        if path.is_file():
            mlflow.log_artifact(str(path), artifact_path="run")
    hints = root / "tracking" / "artifacts.jsonl"
    if hints.is_file():
        for line in hints.read_text().splitlines():
            try:
                item = json.loads(line)
            except json.JSONDecodeError:
                continue
            if not isinstance(item, dict):
                continue
            path = root / str(item.get("path", ""))
            if path.is_file():
                # Preserve run-relative parent paths: two validation patients
                # can both emit step_000005.png without colliding in MLflow.
                try:
                    relative_parent = path.resolve().relative_to(root.resolve()).parent
                except ValueError:
                    relative_parent = Path()
                mlflow.log_artifact(str(path), artifact_path=str(Path("artifacts") / relative_parent))


def main() -> int:
    import mlflow

    args = parse_args()
    root = run_dir()
    (root / "logs").mkdir(exist_ok=True)
    archive_prior_execution(root)
    details = provenance(args.command)
    (root / "run.json").write_text(json.dumps(details, indent=2, sort_keys=True) + "\n")

    tracking_uri = os.environ.get("MLFLOW_TRACKING_URI", "http://tracker:5000")
    mlflow.set_tracking_uri(tracking_uri)
    campaign = os.environ.get("MIAgent_CAMPAIGN", "").strip()
    experiment_name = "/".join(
        value for value in ("MIAgent", campaign, details.get("challenge"), details.get("baseline")) if value
    )
    mlflow.set_experiment(experiment_name or "MIAgent")
    with mlflow.start_run(run_name=str(details.get("experiment") or root.name)):
        params = {
            "challenge": details.get("challenge"),
            "baseline": details.get("baseline"),
            "experiment": details.get("experiment"),
            "command": " ".join(args.command),
            "torch": details.get("torch"),
            "torch_cuda": details.get("torch_cuda"),
            "monai": details.get("monai"),
            "gpu": details.get("nvidia_smi"),
            "gpu_mode": details.get("gpu_mode"),
            "gpu_budget_mb": details.get("gpu_budget_mb"),
        }
        mlflow.log_params({key: str(value) for key, value in params.items() if value is not None})
        mlflow.set_tags(
            {
                "miagent.challenge": str(details.get("challenge") or ""),
                "miagent.baseline": str(details.get("baseline") or ""),
                "miagent.stage": str(os.environ.get("MIAgent_STAGE") or "other"),
                "miagent.campaign": campaign,
                "miagent.containerized": "true",
            }
        )
        return_code = run_workload(args.command, root / "logs" / "command.log")
        details["finished_at"] = time.time()
        details["return_code"] = return_code
        details["wall_seconds"] = details["finished_at"] - details["started_at"]
        (root / "run.json").write_text(json.dumps(details, indent=2, sort_keys=True) + "\n")
        emitted_params = read_json(root / "tracking" / "params.json", {})
        if isinstance(emitted_params, dict):
            mlflow.log_params({str(key): str(value) for key, value in emitted_params.items()})
        else:
            emitted_params = {}
        runtime_params = {
            "runtime.wall_seconds": round(float(details["wall_seconds"]), 3),
            "runtime.wall_time": format_wall_time(float(details["wall_seconds"])),
            "runtime.started_at_utc": utc_timestamp(details["started_at"]),
            "runtime.finished_at_utc": utc_timestamp(details["finished_at"]),
            "runtime.return_code": return_code,
        }
        mlflow.log_params({key: str(value) for key, value in runtime_params.items()})
        emitted_tags = read_json(root / "tracking" / "tags.json", {})
        if isinstance(emitted_tags, dict):
            mlflow.set_tags({str(key): str(value) for key, value in emitted_tags.items()})
        description = root / "tracking" / "description.md"
        description_text = description.read_text() if description.is_file() else ""
        parameter_notes = read_json(root / "tracking" / "parameter_descriptions.json", {})
        if not isinstance(parameter_notes, dict):
            parameter_notes = {}
        all_parameters = {key: value for key, value in params.items() if value is not None}
        all_parameters.update(emitted_params)
        all_parameters.update(runtime_params)
        mlflow.set_tag("mlflow.note.content", build_mlflow_note(details, description_text, all_parameters, parameter_notes))
        metric_events = root / "tracking" / "metrics.jsonl"
        if metric_events.is_file():
            for line in metric_events.read_text().splitlines():
                try:
                    event = json.loads(line)
                    if is_gpu_metric(str(event["name"])):
                        continue
                    mlflow.log_metric(str(event["name"]), float(event["value"]), step=int(event.get("step", 0)))
                except (KeyError, TypeError, ValueError, json.JSONDecodeError):
                    continue
        mlflow.log_metric("runtime.return_code", return_code)
        mlflow.log_metric("runtime.wall_seconds", details["finished_at"] - details["started_at"])
        write_run_dashboard(root, details, description_text, all_parameters, parameter_notes)
        update_challenge_dashboard(root)
        log_tracking_artifacts(root)
    return return_code


if __name__ == "__main__":
    raise SystemExit(main())
