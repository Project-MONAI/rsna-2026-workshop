"""Small, dependency-light experiment event API for local MIAgent workloads.

The launcher owns the MLflow run. Workloads use this module to emit parameters
and metrics into their durable run directory and TensorBoard event stream. The
launcher imports those events into the same MLflow run when the command exits.
This avoids passing MLflow credentials or a tracking-client lifecycle into each
model wrapper while still allowing live TensorBoard monitoring.
"""

from __future__ import annotations

import atexit
import json
import os
import re
import time
from pathlib import Path
from typing import Any, Mapping


_WRITERS: dict[Path, Any] = {}


def is_gpu_metric(name: str) -> bool:
    """Return whether a scalar is GPU resource telemetry, not a learning metric."""
    parts = [part for part in re.split(r"[^a-z0-9]+", str(name).lower()) if part]
    return "gpu" in parts or "cuda" in parts or "nvidia" in parts


def _run_dir() -> Path | None:
    value = os.environ.get("MIAgent_RUN_DIR")
    return Path(value) if value else None


def _write_json(path: Path, value: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n")


def _write_live_dice_dashboard(run_dir: Path, dice_metrics: Mapping[str, Any]) -> None:
    """Keep the active run's detail page synchronized with Dice events."""
    dashboard = run_dir / "tracking" / "dashboard.md"
    try:
        original = dashboard.read_text()
    except OSError:
        original = "# Local Run Dashboard\n"
    lines = [
        "<!-- live dice summary: begin -->",
        "## Latest Dice Summary",
        "",
        "| Split / label | Dice | Step |",
        "|---|---:|---:|",
    ]
    for name in sorted(dice_metrics):
        item = dice_metrics[name]
        if not isinstance(item, dict):
            continue
        try:
            value = float(item["value"])
            step = int(item["step"])
        except (KeyError, TypeError, ValueError):
            continue
        label = str(name).replace("training.dice", "train average", 1).replace(
            "validation.dice", "validation average", 1
        ).replace(".", " / ")
        lines.append(f"| {label} | {value:.4f} | {step} |")
    lines.append("<!-- live dice summary: end -->")
    generated = "\n".join(lines)
    begin, end = "<!-- live dice summary: begin -->", "<!-- live dice summary: end -->"
    start_index, end_index = original.find(begin), original.find(end)
    if start_index >= 0 and end_index >= start_index:
        updated = original[:start_index].rstrip() + "\n\n" + generated + original[end_index + len(end):]
    else:
        updated = original.rstrip() + "\n\n" + generated + "\n"
    dashboard.write_text(updated)


def _writer(run_dir: Path) -> Any:
    """Return one TensorBoard writer per run/process, never one per metric."""
    writer = _WRITERS.get(run_dir)
    if writer is None:
        from torch.utils.tensorboard import SummaryWriter

        writer = SummaryWriter(log_dir=str(run_dir / "tensorboard"))
        _WRITERS[run_dir] = writer
    return writer


def _close_writers() -> None:
    for writer in _WRITERS.values():
        try:
            writer.flush()
            writer.close()
        except Exception:
            pass
    _WRITERS.clear()


atexit.register(_close_writers)


def record_parameters(parameters: Mapping[str, Any]) -> None:
    """Merge JSON-serializable workload parameters into ``params.json``."""
    run_dir = _run_dir()
    if run_dir is None:
        return
    path = run_dir / "tracking" / "params.json"
    existing: dict[str, Any] = {}
    if path.exists():
        try:
            existing = json.loads(path.read_text())
        except json.JSONDecodeError:
            existing = {}
    existing.update({str(key): value for key, value in parameters.items()})
    _write_json(path, existing)


def record_parameter_descriptions(descriptions: Mapping[str, str]) -> None:
    """Merge human-readable explanations for workload parameters.

    These are rendered in the local run dashboard and appended to the MLflow
    run note by the container entrypoint. Parameters without an explicit
    explanation still receive a safe generic description.
    """
    run_dir = _run_dir()
    if run_dir is None:
        return
    path = run_dir / "tracking" / "parameter_descriptions.json"
    existing: dict[str, str] = {}
    if path.exists():
        try:
            value = json.loads(path.read_text())
            if isinstance(value, dict):
                existing = {str(key): str(item) for key, item in value.items()}
        except json.JSONDecodeError:
            pass
    existing.update({str(key): str(value) for key, value in descriptions.items()})
    _write_json(path, existing)


def record_tags(tags: Mapping[str, Any]) -> None:
    """Merge searchable MLflow tags emitted by a workload."""
    run_dir = _run_dir()
    if run_dir is None:
        return
    path = run_dir / "tracking" / "tags.json"
    existing: dict[str, Any] = {}
    if path.exists():
        try:
            existing = json.loads(path.read_text())
        except json.JSONDecodeError:
            existing = {}
    existing.update({str(key): str(value) for key, value in tags.items()})
    _write_json(path, existing)


def record_description(markdown: str) -> None:
    """Write the human-readable MLflow run description."""
    run_dir = _run_dir()
    if run_dir is None:
        return
    path = run_dir / "tracking" / "description.md"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(markdown.strip() + "\n")


def record_metric(name: str, value: float, step: int = 0) -> None:
    """Record a learning metric; GPU scalars are diverted to local telemetry."""
    record_metrics({name: value}, step=step)


def record_metrics(metrics: Mapping[str, float], step: int = 0) -> None:
    """Emit related learning scalars to the durable log and TensorBoard.

    GPU metrics are never written to the learning-metric stream or TensorBoard;
    accidental GPU keys are diverted to local ``telemetry.jsonl`` instead.
    """
    run_dir = _run_dir()
    if run_dir is None:
        return
    gpu_metrics = {str(name): value for name, value in metrics.items() if is_gpu_metric(str(name))}
    learning_metrics = {str(name): value for name, value in metrics.items() if not is_gpu_metric(str(name))}
    if gpu_metrics:
        record_telemetry(gpu_metrics, step=step)
    if not learning_metrics:
        return
    tracking_dir = run_dir / "tracking"
    tracking_dir.mkdir(parents=True, exist_ok=True)
    with (tracking_dir / "metrics.jsonl").open("a") as stream:
        for name, value in learning_metrics.items():
            event = {"name": str(name), "value": float(value), "step": int(step), "time": time.time()}
            stream.write(json.dumps(event, sort_keys=True) + "\n")
    dice_metrics: dict[str, dict[str, float | int]] = {}
    summary_path = tracking_dir / "dice_summary.json"
    try:
        existing = json.loads(summary_path.read_text()) if summary_path.exists() else {}
        if isinstance(existing, dict):
            dice_metrics = existing
    except (OSError, json.JSONDecodeError):
        dice_metrics = {}
    for name, value in learning_metrics.items():
        if str(name) in {"training.dice", "validation.dice"} or str(name).startswith(("training.dice.", "validation.dice.")):
            dice_metrics[str(name)] = {"value": float(value), "step": int(step)}
    if dice_metrics:
        _write_json(summary_path, dice_metrics)
        try:
            _write_live_dice_dashboard(run_dir, dice_metrics)
        except OSError:
            # Live details are observability-only and must not fail training.
            pass
    try:
        writer = _writer(run_dir)
        for name, value in learning_metrics.items():
            writer.add_scalar(str(name), float(value), int(step))
        writer.flush()
    except Exception:
        # Tracking must never turn a completed imaging workload into a failure.
        return
    # The report dashboard is deliberately light-weight, but its primary
    # learning curves should be live while a job is running rather than only
    # materializing after container exit. Raw telemetry stays off this path.
    if any(str(name) in {"training.loss", "training.dice", "validation.loss", "validation.dice"} for name in learning_metrics):
        try:
            from container_entrypoint import update_challenge_dashboard

            update_challenge_dashboard(run_dir)
        except Exception:
            # Report refreshes are convenience-only and must not perturb a
            # training step if the dashboard filesystem is temporarily busy.
            pass


def record_telemetry(metrics: Mapping[str, float], step: int = 0) -> None:
    """Persist hardware telemetry locally without dashboard logging.

    Raw resource samples stay in the run directory for capacity decisions and
    human-readable optimization reports. They are excluded from TensorBoard and
    are not uploaded to MLflow.
    """
    run_dir = _run_dir()
    if run_dir is None:
        return
    tracking_dir = run_dir / "tracking"
    tracking_dir.mkdir(parents=True, exist_ok=True)
    with (tracking_dir / "telemetry.jsonl").open("a") as stream:
        for name, value in metrics.items():
            event = {"name": str(name), "value": float(value), "step": int(step), "time": time.time()}
            stream.write(json.dumps(event, sort_keys=True) + "\n")


def record_image(name: str, image: Any, step: int = 0) -> Path | None:
    """Log a CHW image to TensorBoard and preserve a PNG as an MLflow artifact.

    Call this only for reviewable validation examples. The caller owns patient
    selection and must keep the count deliberately small.
    """
    run_dir = _run_dir()
    if run_dir is None:
        return None
    try:
        import numpy as np
        import torch
        from PIL import Image

        tensor = torch.as_tensor(image).detach().cpu().float()
        if tensor.ndim == 2:
            tensor = tensor.unsqueeze(0)
        if tensor.ndim != 3:
            raise ValueError("record_image expects a HW or CHW image")
        tensor = tensor.clamp(0.0, 1.0)
        writer = _writer(run_dir)
        writer.add_image(str(name), tensor, int(step))
        writer.flush()
        encoded_name = re.sub(r"[^A-Za-z0-9_.-]+", "_", str(name)).strip("_") or "image"
        output = run_dir / "tracking" / "images" / encoded_name / f"step_{int(step):06d}.png"
        output.parent.mkdir(parents=True, exist_ok=True)
        array = tensor.numpy()
        if array.shape[0] == 1:
            pixels = (array[0] * 255.0).round().astype(np.uint8)
        else:
            pixels = (np.moveaxis(array[:3], 0, -1) * 255.0).round().astype(np.uint8)
        Image.fromarray(pixels).save(output)
        record_artifact_hint(output)
        return output
    except Exception:
        # Image logging is observability, never a reason to fail validation.
        return None


def record_artifact_hint(path: str | Path) -> None:
    """Request upload of an existing run-relative artifact to MLflow."""
    run_dir = _run_dir()
    if run_dir is None:
        return
    candidate = Path(path)
    try:
        relative = candidate.resolve().relative_to(run_dir.resolve())
    except (OSError, ValueError):
        return
    hints = run_dir / "tracking" / "artifacts.jsonl"
    hints.parent.mkdir(parents=True, exist_ok=True)
    with hints.open("a") as stream:
        stream.write(json.dumps({"path": str(relative)}) + "\n")
