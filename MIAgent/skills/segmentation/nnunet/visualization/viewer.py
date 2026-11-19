"""Portable, static HTML evidence viewer for nnU-Net segmentation runs."""

from __future__ import annotations

import html
import json
import shutil
from pathlib import Path
from typing import Any, Mapping, Sequence

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.colors import ListedColormap
import nibabel as nib
import numpy as np

from .training import render_training_curves


DEFAULT_COLORS = [
    (0.00, 0.00, 0.00, 0.00),
    (0.16, 0.64, 0.98, 0.62),
    (0.96, 0.45, 0.35, 0.62),
    (0.98, 0.78, 0.22, 0.62),
    (0.50, 0.30, 0.95, 0.62),
    (0.22, 0.78, 0.45, 0.62),
    (0.95, 0.35, 0.75, 0.62),
    (0.20, 0.84, 0.82, 0.62),
    (0.98, 0.58, 0.10, 0.62),
]
ERROR_COLORS = [
    (0, 0, 0, 0),
    (0.20, 0.85, 0.35, 0.70),
    (0.98, 0.20, 0.20, 0.78),
    (0.20, 0.45, 1.00, 0.78),
    (1.00, 0.78, 0.10, 0.82),
]


def _resolve_path(value: Any, key: str | None = None) -> Path:
    if isinstance(value, Mapping):
        if key and key in value:
            value = value[key]
        elif len(value) == 1:
            value = next(iter(value.values()))
        else:
            raise ValueError(f"Cannot resolve {key!r} from mapping keys {list(value)}")
    if isinstance(value, (list, tuple)):
        if len(value) != 1:
            raise ValueError("The static viewer currently renders one image modality per panel")
        value = value[0]
    return Path(value).expanduser().resolve()


def _resolve_modalities(value: Any, key: str = "image") -> list[tuple[str, Path]]:
    """Normalize one or more named image paths without discarding modalities."""
    if isinstance(value, Mapping) and key in value:
        value = value[key]
    if isinstance(value, Mapping):
        items = list(value.items())
    elif isinstance(value, (list, tuple)):
        items = [(f"modality {index}", item) for index, item in enumerate(value)]
    else:
        items = [("image", value)]
    if not items:
        raise ValueError("At least one image modality is required")
    return [(str(name), _resolve_path(path)) for name, path in items]


def _load_canonical(path: Path) -> tuple[np.ndarray, np.ndarray, tuple[float, ...]]:
    nii = nib.as_closest_canonical(nib.load(str(path)))
    return np.asarray(nii.dataobj), nii.affine, tuple(float(x) for x in nii.header.get_zooms()[:3])


def _native_geometry(path: Path) -> tuple[tuple[int, ...], np.ndarray, np.ndarray]:
    nii = nib.load(str(path))
    return tuple(nii.shape), nii.affine, nib.orientations.io_orientation(nii.affine)


def _window(image: np.ndarray) -> tuple[float, float]:
    finite = image[np.isfinite(image)]
    nonzero = finite[finite != 0]
    sample = nonzero if nonzero.size else finite
    if not sample.size:
        return 0.0, 1.0
    lo, hi = np.percentile(sample, [1, 99])
    return float(lo), float(hi if hi > lo else lo + 1.0)


def _focus(gt: np.ndarray, pred: np.ndarray) -> tuple[int, int, int]:
    support = gt != pred
    if not np.any(support):
        support = gt > 0
    if not np.any(support):
        return tuple(int(value // 2) for value in gt.shape)
    return tuple(int(np.median(np.where(support)[axis])) for axis in range(3))


def _plane(array: np.ndarray, axis: int, index: int) -> np.ndarray:
    return np.rot90(np.take(array, index, axis=axis))


def _aspect(spacing: tuple[float, ...], axis: int) -> float:
    remaining = [spacing[index] for index in range(3) if index != axis]
    # _plane applies np.rot90, so the second remaining axis becomes the
    # displayed row axis and the first becomes the column axis.
    return remaining[1] / remaining[0]


def _normalize_labels(labels: Mapping[int | str, str] | None, max_label: int) -> dict[int, str]:
    normalized = {int(key): str(value) for key, value in (labels or {}).items()}
    return normalized or {label: f"class {label}" for label in range(1, max_label + 1)}


def _colors(count: int, supplied: Sequence[Sequence[float]] | None) -> np.ndarray:
    if supplied:
        colors = np.asarray(supplied, dtype=float)
    else:
        colors = np.asarray(DEFAULT_COLORS, dtype=float)
    if len(colors) <= count:
        palette = plt.get_cmap("tab20")
        colors = np.vstack([colors, [(*palette(index % 20)[:3], 0.62) for index in range(len(colors), count + 1)]])
    colors[0] = (0, 0, 0, 0)
    return colors


def _metric_rows(metrics: Mapping[str, Any] | None, labels: Mapping[int, str]) -> str:
    if not metrics:
        return "<p>No metrics supplied.</p>"
    rows = []
    class_metrics = metrics.get("classes", metrics)
    if isinstance(class_metrics, Mapping):
        for key, value in class_metrics.items():
            if not isinstance(value, Mapping):
                continue
            name = labels.get(int(key), str(key)) if str(key).isdigit() else str(key)
            dice = value.get("Dice", value.get("dice", "—"))
            hd95 = value.get("HD95", value.get("hd95", "—"))
            dice_text = f"{float(dice):.4f}" if isinstance(dice, (int, float)) else str(dice)
            hd_text = f"{float(hd95):.3f}" if isinstance(hd95, (int, float)) else str(hd95)
            rows.append(f"<tr><td>{html.escape(name)}</td><td>{dice_text}</td><td>{hd_text}</td></tr>")
    return (
        "<table><thead><tr><th>Class</th><th>Dice</th><th>HD95</th></tr></thead>"
        f"<tbody>{''.join(rows)}</tbody></table>"
    )


def visualize_case(
    inputs,
    prediction,
    output_dir,
    *,
    ground_truth=None,
    case_id,
    intermediates=None,
    metrics=None,
    metadata=None,
    labels=None,
    colors=None,
):
    """Render canonical orthogonal image/GT/prediction/error panels for one case."""
    del intermediates
    image_paths = _resolve_modalities(inputs, "image")
    pred_path = _resolve_path(prediction, "mask")
    if ground_truth is None:
        raise ValueError("The diagnostic viewer requires ground truth")
    gt_path = _resolve_path(ground_truth, "mask")
    native_geometries = {
        str(path): _native_geometry(path)
        for path in [*(path for _, path in image_paths), gt_path, pred_path]
    }
    gt_native_shape, gt_native_affine, gt_orientation = native_geometries[str(gt_path)]
    for path_text, (shape, affine, orientation) in native_geometries.items():
        if shape != gt_native_shape:
            raise ValueError(f"{case_id}: native shape mismatch for {path_text}")
        if not np.allclose(affine, gt_native_affine, atol=1e-3, rtol=0):
            raise ValueError(f"{case_id}: native affine mismatch for {path_text}")
        if not np.array_equal(orientation, gt_orientation):
            raise ValueError(f"{case_id}: native orientation mismatch for {path_text}")
    loaded_images = [(name, path, *_load_canonical(path)) for name, path in image_paths]
    _, _, image, _, spacing = loaded_images[0]
    gt, _, _ = _load_canonical(gt_path)
    pred, _, _ = _load_canonical(pred_path)
    modality_shapes = {name: array.shape for name, _, array, _, _ in loaded_images}
    if any(array.shape != gt.shape for _, _, array, _, _ in loaded_images) or gt.shape != pred.shape:
        raise ValueError(f"{case_id}: shape mismatch modalities={modality_shapes}, gt={gt.shape}, pred={pred.shape}")
    gt = np.rint(gt).astype(np.int16)
    pred = np.rint(pred).astype(np.int16)
    max_label = int(max(gt.max(initial=0), pred.max(initial=0)))
    labels = _normalize_labels(labels, max_label)
    if min(gt.min(initial=0), pred.min(initial=0)) < 0 or max_label > max(labels, default=0):
        raise ValueError(f"{case_id}: observed labels do not match the viewer label map")
    palette = _colors(max_label, colors)
    label_cmap = ListedColormap(palette)
    error_cmap = ListedColormap(ERROR_COLORS)
    focus = _focus(gt, pred)
    windows = [_window(array) for _, _, array, _, _ in loaded_images]
    column_count = len(loaded_images) + 3
    fig, axes = plt.subplots(3, column_count, figsize=(3.75 * column_count, 11), constrained_layout=True)
    for axis, plane_name in enumerate(("sagittal", "coronal", "axial")):
        image_planes = [_plane(array, axis, focus[axis]) for _, _, array, _, _ in loaded_images]
        gt2, pred2 = (_plane(array, axis, focus[axis]) for array in (gt, pred))
        err = np.zeros_like(gt2, dtype=np.uint8)
        err[(gt2 > 0) & (gt2 == pred2)] = 1
        err[(gt2 == 0) & (pred2 > 0)] = 2
        err[(gt2 > 0) & (pred2 == 0)] = 3
        err[(gt2 > 0) & (pred2 > 0) & (gt2 != pred2)] = 4
        panels = [
            (name, image_planes[index], windows[index], None, None, 1)
            for index, (name, _, _, _, _) in enumerate(loaded_images)
        ]
        panels.extend(
            [
                ("ground truth", image_planes[0], windows[0], gt2, label_cmap, max_label),
                ("prediction", image_planes[0], windows[0], pred2, label_cmap, max_label),
                ("error: TP / FP / FN / wrong class", image_planes[0], windows[0], err, error_cmap, 4),
            ]
        )
        for column, (title, background, window, overlay, cmap, vmax) in enumerate(panels):
            ax = axes[axis, column]
            aspect = _aspect(spacing, axis)
            ax.imshow(
                background,
                cmap="gray",
                vmin=window[0],
                vmax=window[1],
                interpolation="nearest",
                aspect=aspect,
            )
            if overlay is not None:
                ax.imshow(
                    np.ma.masked_where(overlay == 0, overlay),
                    cmap=cmap,
                    vmin=0,
                    vmax=vmax,
                    interpolation="nearest",
                    aspect=aspect,
                )
            ax.set_title(f"{plane_name} · {title}", fontsize=9)
            ax.axis("off")
    metadata = dict(metadata or {})
    fig.suptitle(
        f"{case_id} · focus voxel {focus} · spacing {spacing} · "
        f"{metadata.get('checkpoint', 'checkpoint not supplied')}",
        fontsize=11,
    )
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    png_path = output_dir / f"{case_id}.png"
    fig.savefig(png_path, dpi=130)
    plt.close(fig)
    return {
        "case_id": case_id,
        "images": {name: str(path) for name, path in image_paths},
        "ground_truth": str(gt_path),
        "prediction": str(pred_path),
        "png": str(png_path.resolve()),
        "focus": focus,
        "spacing": spacing,
        "metrics": metrics or {},
        "metadata": metadata,
    }


def _training_section(
    payload: Mapping[str, Any],
    output_html: Path,
    assets: Path,
    training_logs: Sequence[str | Path] | None,
) -> str:
    training = dict(payload.get("training", {}))
    logs = list(training_logs or training.get("logs", []))
    curve_source = training.get("curve")
    curve_target = assets / "training_curves.png"
    data_target = assets / "training_curves.json"
    summary: Mapping[str, Any] = training.get("summary", {})
    if logs:
        result = render_training_curves(
            logs,
            curve_target,
            output_json=data_target,
            class_names=training.get("class_names"),
            title=training.get("title", "nnU-Net training diagnostics"),
        )
        summary = result["summary"]
    elif curve_source:
        source = Path(curve_source).expanduser().resolve()
        if source != curve_target.resolve():
            shutil.copy2(source, curve_target)
    elif not curve_target.is_file():
        return ""
    stats = [
        ("completed epochs", summary.get("epochs_parsed")),
        ("epoch range", f"{summary.get('first_epoch', '—')}–{summary.get('last_epoch', '—')}"),
        ("best mean pseudo-Dice", summary.get("best_mean_pseudo_dice")),
        ("best epoch", summary.get("best_mean_pseudo_dice_epoch")),
        ("median epoch", f"{summary['median_epoch_seconds']:.2f} s" if summary.get("median_epoch_seconds") else None),
    ]
    cards = "".join(
        f"<div class='stat'><span>{html.escape(label)}</span><strong>"
        f"{html.escape(f'{value:.4f}' if isinstance(value, float) else str(value))}</strong></div>"
        for label, value in stats
        if value is not None
    )
    relative = curve_target.relative_to(output_html.parent)
    sources = summary.get("log_sources", logs)
    source_text = "<br>".join(html.escape(str(item)) for item in sources)
    return (
        "<section id='training'><h2>Training diagnostics</h2>"
        "<p>These are nnU-Net internal training signals; official held-out metrics remain separate.</p>"
        f"<div class='stats'>{cards}</div><img src='{html.escape(str(relative))}' "
        "alt='nnU-Net loss, pseudo-Dice, learning-rate, and epoch-duration curves'>"
        f"<p class='paths'><b>training logs:</b><br>{source_text}</p></section>"
    )


def visualize_run(
    manifest,
    output_html,
    *,
    training_logs: Sequence[str | Path] | None = None,
    reuse_assets: bool = False,
):
    """Build a portable run viewer from a normalized manifest."""
    manifest_path = Path(manifest).resolve() if not isinstance(manifest, Mapping) else None
    payload = json.loads(manifest_path.read_text()) if manifest_path else dict(manifest)
    output_html = Path(output_html).resolve()
    assets = output_html.parent / "viewer_assets"
    assets.mkdir(parents=True, exist_ok=True)
    config = payload.get("viewer", {})
    configured_colors = config.get("colors") or []
    configured_labels = config.get("labels")
    if configured_labels:
        labels = _normalize_labels(configured_labels, len(configured_colors) - 1)
    else:
        label_ids = sorted(
            {
                int(key)
                for case in payload["cases"]
                for key in case.get("metrics", {}).get("classes", {})
                if str(key).isdigit() and int(key) > 0
            }
        )
        labels = {label: f"class {label}" for label in label_ids}
    colors = config.get("colors")
    rendered = []
    for case in payload["cases"]:
        cached = assets / f"{case['case_id']}.png"
        if reuse_assets and cached.is_file():
            rendered.append(
                {
                    "case_id": case["case_id"],
                    "images": {
                        name: str(path) for name, path in _resolve_modalities(case["inputs"], "image")
                    },
                    "ground_truth": str(_resolve_path(case["ground_truth"], "mask")),
                    "prediction": str(_resolve_path(case["prediction"], "mask")),
                    "png": str(cached.resolve()),
                    "metrics": case.get("metrics", {}),
                }
            )
        else:
            rendered.append(
                visualize_case(
                    case["inputs"],
                    case["prediction"],
                    assets,
                    ground_truth=case["ground_truth"],
                    case_id=case["case_id"],
                    metrics=case.get("metrics"),
                    metadata={**payload.get("provenance", {}), **case.get("metadata", {})},
                    labels=labels,
                    colors=colors,
                )
            )
    provenance = html.escape(json.dumps(payload.get("provenance", {}), indent=2, sort_keys=True))
    palette = _colors(max(labels, default=0), colors)
    legend = " · ".join(
        f"<span style='color:rgba({int(palette[label, 0] * 255)},{int(palette[label, 1] * 255)},"
        f"{int(palette[label, 2] * 255)},1)'>■</span> {label}: {html.escape(name)}"
        for label, name in labels.items()
    )
    cards = []
    for item in rendered:
        relative_png = Path(item["png"]).relative_to(output_html.parent)
        artifact_lines = "<br>".join(
            [
                *[
                    f"<b>image ({html.escape(name)}):</b> {html.escape(path)}"
                    for name, path in item["images"].items()
                ],
                f"<b>ground truth:</b> {html.escape(item['ground_truth'])}",
                f"<b>prediction:</b> {html.escape(item['prediction'])}",
            ]
        )
        cards.append(
            f"<section id='{html.escape(item['case_id'])}'><h2>{html.escape(item['case_id'])}</h2>"
            f"<img src='{html.escape(str(relative_png))}' alt='Orthogonal overlays for {html.escape(item['case_id'])}'>"
            f"{_metric_rows(item['metrics'], labels)}<p class='paths'>{artifact_lines}</p></section>"
        )
    index = " · ".join(f"<a href='#{html.escape(item['case_id'])}'>{html.escape(item['case_id'])}</a>" for item in rendered)
    training = _training_section(payload, output_html, assets, training_logs)
    title = html.escape(config.get("title", "nnU-Net segmentation evidence"))
    navigation = f"<a href='#training'>training</a> · {index}" if training else index
    document = f"""<!doctype html>
<html><head><meta charset="utf-8"><title>{title}</title>
<style>
:root {{color-scheme:dark}} body {{font-family:system-ui,sans-serif;margin:2rem;background:#111827;color:#e5e7eb}}
a {{color:#7dd3fc}} section {{background:#1f2937;padding:1rem;margin:1.5rem 0;border-radius:10px}}
img {{width:100%;max-width:1500px;background:white;border-radius:6px}} table {{border-collapse:collapse;margin:1rem 0}}
th,td {{border:1px solid #4b5563;padding:.35rem .7rem}} pre,.paths {{font-size:.8rem;overflow-wrap:anywhere}}
.stats {{display:flex;flex-wrap:wrap;gap:.75rem;margin:1rem 0}} .stat {{background:#111827;padding:.65rem .85rem;border-radius:7px}}
.stat span {{display:block;color:#9ca3af;font-size:.75rem}} .stat strong {{font-size:1rem}}
</style></head><body><h1>{title}</h1>
<p>{navigation}</p><p><b>Label legend:</b> {legend}</p>
<p><b>Error legend:</b> correct foreground green · foreground FP red · foreground FN blue · wrong foreground class yellow</p>
<h2>Provenance</h2><pre>{provenance}</pre>{training}{''.join(cards)}</body></html>"""
    output_html.write_text(document)
    return output_html
