# miagent-template-source: challenge/challenge_template/shared/visualization/visualizer.py
# miagent-template-contract: active; keep the miagent-template-source loaded for creation/material updates; reload after resume or compaction
"""Supplied shared visualization for manifest-based NIfTI segmentation."""

from __future__ import annotations

import argparse
import html
import os
import sys
from pathlib import Path
from typing import Any, Mapping, Sequence


Artifact = str | Path
Artifacts = Artifact | Sequence[Artifact] | Mapping[str, Artifact]

TEMPLATE_STUB = False


def _repository_root() -> Path:
    return Path(__file__).resolve().parents[4]


def _as_mapping(artifacts: Artifacts | None, default_key: str) -> dict[str, Path]:
    if artifacts is None:
        return {}
    if isinstance(artifacts, (str, Path)):
        return {default_key: Path(artifacts)}
    if isinstance(artifacts, Mapping):
        return {str(key): Path(value) for key, value in artifacts.items()}
    return {f"{default_key}_{index}": Path(value) for index, value in enumerate(artifacts)}


def _first_path(paths: Mapping[str, Path], preferred: tuple[str, ...]) -> Path | None:
    for key in preferred:
        if key in paths:
            return paths[key]
    return next(iter(paths.values()), None)


def materialize_segmentation_reviews(manifest: Artifact, *, hu_offset: float = 0.0) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    """Create colocated error NIfTIs/review HTML before rendering a segmentation run."""
    tools_dir = _repository_root() / "tools"
    if str(tools_dir) not in sys.path:
        sys.path.insert(0, str(tools_dir))
    from segmentation_review import generate_manifest_reviews

    return generate_manifest_reviews(Path(manifest), hu_offset=hu_offset)


def visualize_case(
    inputs: Artifacts,
    prediction: Artifacts,
    output_dir: Artifact,
    *,
    ground_truth: Artifacts | None = None,
    case_id: str,
    intermediates: Mapping[str, Artifact] | None = None,
    metrics: Mapping[str, float] | None = None,
    metadata: Mapping[str, Any] | None = None,
) -> Path:
    """Render one segmentation case with the supplied NiiVue review."""
    input_paths = _as_mapping(inputs, "image")
    prediction_paths = _as_mapping(prediction, "prediction")
    truth_paths = _as_mapping(ground_truth, "ground_truth")
    image_path = _first_path(input_paths, ("image", "ct", "CT"))
    prediction_path = _first_path(prediction_paths, ("prediction", "mask"))
    truth_path = _first_path(truth_paths, ("ground_truth", "label", "truth"))
    if prediction_path is None:
        raise ValueError("prediction must contain at least one path")
    if image_path is None or truth_path is None:
        return prediction_path

    tools_dir = _repository_root() / "tools"
    if str(tools_dir) not in sys.path:
        sys.path.insert(0, str(tools_dir))
    from segmentation_review import generate_case_review

    Path(output_dir).mkdir(parents=True, exist_ok=True)
    result = generate_case_review(
        image=image_path,
        truth=truth_path,
        prediction=prediction_path,
        case_id=case_id,
        hu_offset=float((metadata or {}).get("hu_offset", 0.0)),
        metrics=metrics,
        experiment_name=str((metadata or {}).get("experiment") or "") or None,
    )
    return Path(result["review"])


def visualize_run(manifest: Artifact, output_html: Artifact, *, hu_offset: float = 0.0) -> Path:
    """Render an indexed run viewer from a normalized JSON manifest.

    NIfTI segmentation implementations begin by calling
    ``materialize_segmentation_reviews`` and link each returned review page.
    """
    manifest_path = Path(manifest).resolve()
    payload, reviews = materialize_segmentation_reviews(manifest_path, hu_offset=hu_offset)
    review_by_case = {str(item["case_id"]): Path(item["review"]) for item in reviews}
    output_path = Path(output_html)
    if not output_path.is_absolute():
        output_path = manifest_path.parent.parent / output_path
    output_path.parent.mkdir(parents=True, exist_ok=True)

    rows: list[str] = []
    for case in payload.get("cases", []):
        case_id = str(case.get("case_id", "unknown"))
        review = review_by_case.get(case_id)
        if review is None:
            continue
        href = os.path.relpath(review, output_path.parent)
        metrics = case.get("metrics") if isinstance(case.get("metrics"), Mapping) else {}
        dice = metrics.get("dice", metrics.get("mean_dice"))
        dice_text = f" — Dice {float(dice):.4f}" if dice is not None else ""
        rows.append(
            f'<li><a href="{html.escape(href)}">Case {html.escape(case_id)}</a>'
            f"{html.escape(dice_text)}</li>"
        )
    run_name = str(payload.get("run") or manifest_path.parent.parent.name)
    output_path.write_text(
        "<!doctype html><html><head><meta charset='utf-8'>"
        f"<title>{html.escape(run_name)} results</title>"
        "<style>body{font:16px system-ui;max-width:900px;margin:40px auto;"
        "background:#f8fafc;color:#172033}a{color:#075985}li{margin:12px 0}</style>"
        "</head><body>"
        f"<h1>{html.escape(run_name)} validation results</h1><ul>{''.join(rows)}</ul>"
        "</body></html>\n",
        encoding="utf-8",
    )
    return output_path


def main() -> None:
    parser = argparse.ArgumentParser(description="Render challenge results")
    parser.add_argument("--manifest", required=True)
    parser.add_argument("--output", required=True)
    parser.add_argument("--hu-offset", type=float, default=0.0)
    args = parser.parse_args()
    print(visualize_run(args.manifest, args.output, hu_offset=args.hu_offset))


if __name__ == "__main__":
    main()
