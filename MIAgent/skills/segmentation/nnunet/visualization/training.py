"""Parse nnU-Net text logs and render compact diagnostic training curves."""

from __future__ import annotations

import json
import re
from pathlib import Path
from statistics import median
from typing import Any, Iterable

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np


_PATTERNS = {
    "epoch": re.compile(r": Epoch (\d+)\s*$"),
    "learning_rate": re.compile(r": Current learning rate: ([-+0-9.eE]+)\s*$"),
    "train_loss": re.compile(r": train_loss ([-+0-9.eE]+)\s*$"),
    "val_loss": re.compile(r": val_loss ([-+0-9.eE]+)\s*$"),
    "pseudo_dice": re.compile(r": Pseudo dice (\[.*\])\s*$"),
    "epoch_time": re.compile(r": Epoch time: ([-+0-9.eE]+) s\s*$"),
}


def _parse_logged_scalar(value: str) -> float:
    """Parse Python floats and NumPy scalar reprs emitted by newer nnU-Net."""
    cleaned = value.strip()
    wrapped = re.fullmatch(r"(?:np\.)?float(?:16|32|64)?\(([-+0-9.eE]+)\)", cleaned)
    if wrapped:
        cleaned = wrapped.group(1)
    return np.nan if cleaned.lower() == "nan" else float(cleaned)


def _json_safe(value: Any) -> Any:
    if isinstance(value, float) and not np.isfinite(value):
        return None
    if isinstance(value, list):
        return [_json_safe(item) for item in value]
    if isinstance(value, dict):
        return {key: _json_safe(item) for key, item in value.items()}
    return value


def parse_training_logs(log_paths: Iterable[str | Path]) -> list[dict[str, Any]]:
    """Return one record per epoch, with later resume logs winning duplicates."""
    epochs: dict[int, dict[str, Any]] = {}
    for source_index, raw_path in enumerate(log_paths):
        path = Path(raw_path).expanduser().resolve()
        current: dict[str, Any] | None = None
        for line in path.read_text(errors="replace").splitlines():
            epoch_match = _PATTERNS["epoch"].search(line)
            if epoch_match:
                epoch = int(epoch_match.group(1))
                current = {
                    "epoch": epoch,
                    "source": str(path),
                    "source_index": source_index,
                }
                epochs[epoch] = current
                continue
            if current is None:
                continue
            for field in ("learning_rate", "train_loss", "val_loss", "epoch_time"):
                match = _PATTERNS[field].search(line)
                if match:
                    current[field] = float(match.group(1))
                    break
            else:
                match = _PATTERNS["pseudo_dice"].search(line)
                if match:
                    raw_values = match.group(1).strip()[1:-1]
                    values = [_parse_logged_scalar(value) for value in raw_values.split(",") if value.strip()]
                    current["pseudo_dice"] = [float(value) for value in values]
                    current["mean_pseudo_dice"] = float(np.nanmean(values)) if values else None
    return [
        epochs[epoch]
        for epoch in sorted(epochs)
        if any(key in epochs[epoch] for key in ("train_loss", "val_loss", "pseudo_dice"))
    ]


def summarize_training(records: list[dict[str, Any]]) -> dict[str, Any]:
    if not records:
        raise ValueError("No completed nnU-Net epochs found in the supplied logs")
    dice_records = [item for item in records if item.get("mean_pseudo_dice") is not None]
    durations = [item["epoch_time"] for item in records if "epoch_time" in item]
    best = max(dice_records, key=lambda item: item["mean_pseudo_dice"]) if dice_records else None
    return {
        "epochs_parsed": len(records),
        "first_epoch": records[0]["epoch"],
        "last_epoch": records[-1]["epoch"],
        "best_mean_pseudo_dice": best["mean_pseudo_dice"] if best else None,
        "best_mean_pseudo_dice_epoch": best["epoch"] if best else None,
        "latest_train_loss": records[-1].get("train_loss"),
        "latest_val_loss": records[-1].get("val_loss"),
        "latest_mean_pseudo_dice": records[-1].get("mean_pseudo_dice"),
        "median_epoch_seconds": median(durations) if durations else None,
        "log_sources": list(dict.fromkeys(item["source"] for item in records)),
    }


def render_training_curves(
    log_paths: Iterable[str | Path],
    output_png: str | Path,
    *,
    output_json: str | Path | None = None,
    class_names: Iterable[str] | None = None,
    title: str = "nnU-Net training diagnostics",
) -> dict[str, Any]:
    """Parse logs, create a four-panel curve, and optionally save machine-readable data."""
    records = parse_training_logs(log_paths)
    summary = summarize_training(records)
    epochs = np.asarray([item["epoch"] for item in records])

    fig, axes = plt.subplots(2, 2, figsize=(14, 9), constrained_layout=True)
    ax = axes[0, 0]
    for field, label, color in (
        ("train_loss", "train loss", "#38bdf8"),
        ("val_loss", "validation loss", "#fb7185"),
    ):
        points = [(item["epoch"], item[field]) for item in records if field in item]
        if points:
            ax.plot(*zip(*points), label=label, color=color, linewidth=1.5)
    ax.set(title="Loss", xlabel="epoch", ylabel="loss")
    ax.legend()
    ax.grid(alpha=0.22)

    ax = axes[0, 1]
    dice = [item for item in records if item.get("mean_pseudo_dice") is not None]
    if dice:
        ax.plot(
            [item["epoch"] for item in dice],
            [item["mean_pseudo_dice"] for item in dice],
            label="mean",
            color="#a78bfa",
            linewidth=2.2,
        )
        names = list(class_names or [])
        width = max(len(item.get("pseudo_dice", [])) for item in dice)
        if names and len(names) == width:
            for index, name in enumerate(names):
                points = [
                    (item["epoch"], item["pseudo_dice"][index])
                    for item in dice
                    if len(item["pseudo_dice"]) > index
                ]
                ax.plot(*zip(*points), label=name, alpha=0.38, linewidth=0.8)
    ax.set(title="Validation pseudo-Dice", xlabel="epoch", ylabel="Dice", ylim=(0, 1))
    ax.legend(ncol=3, fontsize=7)
    ax.grid(alpha=0.22)

    ax = axes[1, 0]
    lr = [(item["epoch"], item["learning_rate"]) for item in records if "learning_rate" in item]
    if lr:
        ax.plot(*zip(*lr), color="#fbbf24", linewidth=1.6)
    ax.set(title="Learning rate", xlabel="epoch", ylabel="learning rate")
    ax.grid(alpha=0.22)

    ax = axes[1, 1]
    durations = [(item["epoch"], item["epoch_time"]) for item in records if "epoch_time" in item]
    if durations:
        ax.plot(*zip(*durations), color="#34d399", alpha=0.45, linewidth=0.9)
        window = min(25, len(durations))
        if window > 1:
            values = np.asarray([point[1] for point in durations])
            smooth = np.convolve(values, np.ones(window) / window, mode="valid")
            ax.plot(
                [point[0] for point in durations][window - 1 :],
                smooth,
                color="#059669",
                label=f"{window}-epoch mean",
                linewidth=2,
            )
            ax.legend()
    ax.set(title="Epoch duration", xlabel="epoch", ylabel="seconds")
    ax.grid(alpha=0.22)

    fig.suptitle(
        f"{title} · epochs {int(epochs.min())}–{int(epochs.max())} · "
        f"{summary['epochs_parsed']} completed epochs",
        fontsize=13,
    )
    output_png = Path(output_png).expanduser().resolve()
    output_png.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(output_png, dpi=150, facecolor="white")
    plt.close(fig)

    payload = {"summary": summary, "epochs": records}
    if output_json is not None:
        output_json = Path(output_json).expanduser().resolve()
        output_json.parent.mkdir(parents=True, exist_ok=True)
        output_json.write_text(json.dumps(_json_safe(payload), indent=2, allow_nan=False) + "\n")
    return payload
