#!/usr/bin/env python3
"""Create colocated NIfTI error maps and interactive MIAgent review pages."""

from __future__ import annotations

import argparse
import html
import json
import os
from pathlib import Path
from typing import Any, Mapping
from urllib.parse import quote

from segmentation_difference import (
    assert_same_geometry,
    build_error_map,
    read_nifti_uint8,
    write_error_nifti,
)


def _nifti_stem(path: Path) -> str:
    name = path.name
    if name.endswith(".nii.gz"):
        return name[:-7]
    if name.endswith(".nii"):
        return name[:-4]
    raise ValueError(f"Prediction is not a NIfTI file: {path}")


def _case_stem(prediction: Path, case_id: str) -> str:
    stem = _nifti_stem(prediction)
    return stem[: -len("_prediction")] if stem.endswith("_prediction") else case_id


def _browser_reference(path: Path, page_dir: Path, data_root: Path) -> dict[str, str]:
    try:
        relative_data = path.resolve().relative_to(data_root.resolve())
    except ValueError:
        return {
            "kind": "relative",
            "path": quote(Path(os.path.relpath(path, page_dir)).as_posix(), safe="/._-"),
        }
    return {"kind": "data", "path": quote(relative_data.as_posix(), safe="/._-")}


def render_review_html(
    *,
    image: Path,
    truth: Path,
    prediction: Path,
    error: Path,
    output: Path,
    case_id: str,
    hu_offset: float,
    metrics: Mapping[str, Any] | None = None,
    experiment_name: str | None = None,
    counts: Mapping[str, int] | None = None,
    data_root: Path = Path("/data"),
) -> None:
    artifacts = {
        "image": _browser_reference(image, output.parent, data_root),
        "prediction": _browser_reference(prediction, output.parent, data_root),
        "truth": _browser_reference(truth, output.parent, data_root),
        "difference": _browser_reference(error, output.parent, data_root),
    }
    title = html.escape(str(case_id))
    experiment = html.escape(experiment_name or output.parents[1].name)
    metric_values = dict(metrics or {})
    dice = metric_values.get("dice")
    dice_text = f"{float(dice):.4f}" if isinstance(dice, (int, float)) else "not recorded"
    class_names = {
        1: "LV", 2: "RV", 3: "LA", 4: "RA", 5: "Myocardium",
        6: "Aorta", 7: "Pulmonary artery",
    }
    class_dice = " · ".join(
        f"{name}: {float(metric_values[f'dice_class_{index}']):.4f}"
        for index, name in class_names.items()
        if isinstance(metric_values.get(f"dice_class_{index}"), (int, float))
    ) or "Per-class Dice not recorded"
    count_values = dict(counts or {})
    error_counts = " · ".join(
        f"{label}: {int(count_values[key]):,}"
        for key, label in (
            ("true_positive", "correct foreground"),
            ("wrong_class", "wrong class"),
            ("false_negative", "FN"),
            ("false_positive", "FP"),
        )
        if key in count_values
    )
    artifacts_json = json.dumps(artifacts, ensure_ascii=True)
    hu_offset_json = json.dumps(float(hu_offset))
    output.write_text(f"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>Segmentation review: {title}</title>
  <style>
    * {{ box-sizing: border-box; }}
    html, body {{ width: 100%; height: 100%; margin: 0; overflow: hidden; background: #f8fafc; color: #111827; font: 14px system-ui, sans-serif; }}
    body {{ display: flex; flex-direction: column; }}
    header {{
      position: relative; z-index: 10; flex: 0 0 auto;
      padding: 9px 12px; background: #fff; border-bottom: 1px solid #cbd5e1;
      box-shadow: 0 1px 4px rgb(15 23 42 / 12%);
    }}
    .case-meta, .controls {{ display: flex; align-items: center; flex-wrap: wrap; gap: 8px 12px; }}
    .case-meta {{ margin-bottom: 8px; }}
    .case-meta strong {{ font-size: 16px; }}
    .badge {{ padding: 3px 7px; border-radius: 999px; background: #e2e8f0; }}
    details {{ width: 100%; color: #475569; font-size: 12px; }}
    summary {{ cursor: pointer; color: #1d4ed8; }}
    button, select, input[type="color"] {{ border: 1px solid #94a3b8; border-radius: 5px; padding: 5px 9px; }}
    button {{ color: #111827; background: #f8fafc; cursor: pointer; }}
    button:hover {{ background: #e2e8f0; }}
    button.active {{ color: white; background: #2563eb; border-color: #1d4ed8; }}
    select {{ color: #111827; background: white; }}
    label {{ display: inline-flex; align-items: center; gap: 6px; }}
    input[type="range"] {{ width: 120px; }}
    input[type="color"] {{ width: 38px; height: 30px; padding: 2px; }}
    #legend {{ margin-left: auto; flex: 0 0 auto; font-size: 12px; color: #334155; }}
    iframe {{ flex: 1 1 auto; min-height: 0; width: 100%; border: 0; background: #111827; }}
  </style>
</head>
<body>
  <header>
    <div class="case-meta">
      <strong>Case {title}</strong>
      <span class="badge">Experiment: {experiment}</span>
      <span class="badge">Mean Dice: {dice_text}</span>
      <details><summary>Case metrics</summary><div>{html.escape(class_dice)}</div><div>{html.escape(error_counts)}</div></details>
    </div>
    <div class="controls">
      <button type="button" data-mode="prediction" class="active">Prediction</button>
      <button type="button" data-mode="truth">Ground truth</button>
      <button type="button" data-mode="difference">Difference</button>
      <label for="window">CT contrast
        <select id="window">
          <option value="auto">Automatic</option>
          <option value="cardiac">Cardiac [-200, 800] HU</option>
          <option value="soft">Soft tissue [-160, 240] HU</option>
          <option value="lung">Lung [-1350, 150] HU</option>
          <option value="bone">Bone [-500, 1500] HU</option>
        </select>
      </label>
      <label for="opacity">Overlay opacity
        <input id="opacity" type="range" min="0" max="1" step="0.05" value="0.70">
        <output id="opacity-value" for="opacity">70%</output>
      </label>
      <label for="color-mode">Overlay colors
        <select id="color-mode">
          <option value="classes">Class colors</option>
          <option value="custom">Single custom color</option>
        </select>
      </label>
      <input id="custom-color" type="color" value="#22c55e" aria-label="Custom overlay color" hidden>
      <span id="legend">Prediction label overlay</span>
    </div>
  </header>
  <iframe id="viewer" title="Case {title} NiiVue segmentation review"></iframe>
  <script>
    const marker = "/files/";
    const markerIndex = window.location.pathname.indexOf(marker);
    const prefix = markerIndex >= 0 ? window.location.pathname.slice(0, markerIndex + 1) : "/miagent/";
    const artifactReferences = {artifacts_json};
    const artifacts = Object.fromEntries(Object.entries(artifactReferences).map(([key, value]) => {{
      if (value.kind === "data") return [key, new URL(`${{prefix}}data-files/${{value.path}}`, window.location.origin).pathname];
      return [key, new URL(value.path, window.location.href).pathname];
    }}));
    const overlays = {{ prediction: artifacts.prediction, truth: artifacts.truth, difference: artifacts.difference }};
    const palettes = {{ prediction: "heart", truth: "heart", difference: "errors" }};
    const legends = {{
      prediction: "Prediction label overlay",
      truth: "Ground-truth label overlay",
      difference: "Green correct · yellow wrong class · red FN · pink FP"
    }};
    const windows = {{ cardiac: [-200, 800], soft: [-160, 240], lung: [-1350, 150], bone: [-500, 1500] }};
    const classPalette = {{
      R: [0, 230, 55, 30, 240, 245, 150, 20], G: [0, 60, 180, 140, 155, 215, 80, 205],
      B: [0, 60, 75, 230, 35, 40, 200, 210], A: [0, 255, 255, 255, 255, 255, 255, 255],
      I: [0, 1, 2, 3, 4, 5, 6, 7], labels: ["background", "LV", "RV", "LA", "RA", "myocardium", "aorta", "pulmonary artery"]
    }};
    const errorPalette = {{
      R: [0, 0, 255, 255, 255], G: [0, 255, 64, 0, 255], B: [0, 0, 160, 0, 0],
      A: [0, 255, 255, 255, 255], I: [0, 1, 2, 3, 4],
      labels: ["background", "correct foreground", "false positive", "false negative", "wrong class"]
    }};
    const huOffset = {hu_offset_json};
    const viewer = document.getElementById("viewer");
    const windowSelect = document.getElementById("window");
    const opacity = document.getElementById("opacity");
    const opacityValue = document.getElementById("opacity-value");
    const colorMode = document.getElementById("color-mode");
    const customColor = document.getElementById("custom-color");
    let mode = "prediction";

    function viewerUrl() {{
      const target = new URL(`${{prefix}}nii`, window.location.origin);
      target.searchParams.set("images", artifacts.image);
      target.searchParams.set("overlays", overlays[mode]);
      target.searchParams.set("palette", palettes[mode]);
      target.searchParams.set("embedded", "1");
      return target.href;
    }}

    function sendWindow() {{
      const range = windows[windowSelect.value];
      const body = range ? {{ index: 0, min: range[0] + huOffset, max: range[1] + huOffset }} : {{ index: 0, min: null, max: null }};
      viewer.contentWindow?.postMessage({{ type: "miagentWindow", body }}, "*");
    }}

    function sendOpacity() {{
      opacityValue.value = `${{Math.round(Number(opacity.value) * 100)}}%`;
      viewer.contentWindow?.postMessage({{ type: "miagentOpacity", body: {{ index: 0, volume: 1, opacity: Number(opacity.value) }} }}, "*");
    }}

    function solidPalette(hex) {{
      const rgb = hex.match(/[a-f0-9]{{2}}/gi).map((value) => parseInt(value, 16));
      return {{
        R: [0, ...Array(7).fill(rgb[0])], G: [0, ...Array(7).fill(rgb[1])], B: [0, ...Array(7).fill(rgb[2])],
        A: [0, ...Array(7).fill(255)], I: [0, 1, 2, 3, 4, 5, 6, 7],
        labels: ["background", "label 1", "label 2", "label 3", "label 4", "label 5", "label 6", "label 7"]
      }};
    }}

    function sendPalette() {{
      const locked = mode === "difference";
      colorMode.disabled = locked;
      customColor.disabled = locked;
      customColor.hidden = colorMode.value !== "custom";
      const colormap = mode === "difference"
        ? errorPalette
        : (colorMode.value === "classes" ? classPalette : solidPalette(customColor.value));
      viewer.contentWindow?.postMessage({{ type: "miagentLabelColormap", body: {{ index: 0, volume: 1, colormap }} }}, "*");
    }}

    function loadMode(nextMode) {{
      mode = nextMode;
      document.querySelectorAll("[data-mode]").forEach((button) => button.classList.toggle("active", button.dataset.mode === mode));
      document.getElementById("legend").textContent = legends[mode];
      viewer.src = viewerUrl();
      sendPalette();
    }}

    document.querySelectorAll("[data-mode]").forEach((button) => button.addEventListener("click", () => loadMode(button.dataset.mode)));
    windowSelect.addEventListener("change", sendWindow);
    opacity.addEventListener("input", sendOpacity);
    colorMode.addEventListener("change", sendPalette);
    customColor.addEventListener("input", () => {{ colorMode.value = "custom"; sendPalette(); }});
    viewer.addEventListener("load", () => {{
      for (const delay of [250, 750, 1500, 3000]) window.setTimeout(() => {{ sendWindow(); sendOpacity(); sendPalette(); }}, delay);
    }});
    loadMode("prediction");
  </script>
</body>
</html>
""")


def generate_case_review(
    *, image: Path, truth: Path, prediction: Path, case_id: str, hu_offset: float = 0.0,
    metrics: Mapping[str, Any] | None = None, experiment_name: str | None = None,
    data_root: Path = Path("/data"),
) -> dict[str, Any]:
    for name, path in (("image", image), ("ground truth", truth), ("prediction", prediction)):
        if not path.is_file():
            raise FileNotFoundError(f"Missing {name}: {path}")
    base = _case_stem(prediction, case_id)
    error = prediction.parent / f"{base}_error.nii.gz"
    review = prediction.parent / f"{base}_review.html"
    target = read_nifti_uint8(truth)
    guess = read_nifti_uint8(prediction)
    assert_same_geometry(target, guess)
    error_voxels, counts = build_error_map(target.voxels, guess.voxels)
    write_error_nifti(target, error_voxels, error)
    render_review_html(
        image=image,
        truth=truth,
        prediction=prediction,
        error=error,
        output=review,
        case_id=case_id,
        hu_offset=hu_offset,
        metrics=metrics,
        experiment_name=experiment_name,
        counts=counts,
        data_root=data_root,
    )
    return {"case_id": case_id, "prediction": prediction, "error": error, "review": review, "counts": counts}


def generate_manifest_reviews(
    manifest: Path, hu_offset: float = 0.0, data_root: Path = Path("/data")
) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    payload = json.loads(manifest.read_text())
    experiment_name = str(payload.get("run") or manifest.parent.parent.name)
    results = []
    for case in payload["cases"]:
        case_id = str(case["case_id"])
        truth_value = case.get("label", case.get("ground_truth"))
        if truth_value is None:
            raise ValueError(f"Manifest case {case_id} has no label or ground_truth")
        image = (manifest.parent / case["image"]).resolve()
        truth = (manifest.parent / truth_value).resolve()
        prediction = (manifest.parent / case["prediction"]).resolve()
        result = generate_case_review(
            image=image,
            truth=truth,
            prediction=prediction,
            case_id=case_id,
            hu_offset=hu_offset,
            metrics=case.get("metrics") if isinstance(case.get("metrics"), dict) else None,
            experiment_name=experiment_name,
            data_root=data_root,
        )
        case["error"] = os.path.relpath(result["error"], manifest.parent)
        case["review"] = os.path.relpath(result["review"], manifest.parent)
        results.append(result)
    manifest.write_text(json.dumps(payload, indent=2) + "\n")
    return payload, results


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--hu-offset", type=float, default=0.0)
    args = parser.parse_args()
    _, results = generate_manifest_reviews(args.manifest.resolve(), args.hu_offset)
    print(json.dumps({
        "manifest": str(args.manifest.resolve()),
        "cases": [
            {
                "case_id": result["case_id"],
                "error": str(result["error"]),
                "review": str(result["review"]),
                "counts": result["counts"],
            }
            for result in results
        ],
    }, indent=2))


if __name__ == "__main__":
    main()
