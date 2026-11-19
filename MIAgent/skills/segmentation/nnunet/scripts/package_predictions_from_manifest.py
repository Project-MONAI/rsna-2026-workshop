#!/usr/bin/env python3
"""Package segmentation predictions from a generic manifest.

This supports a common CSV format:

case_id,predicted_mask_path

Challenge-specific packaging should adapt this script or its manifest template.
"""

from __future__ import annotations

import argparse
import csv
import json
import os
import shutil
from pathlib import Path
from typing import Any


def load_manifest(path: Path) -> dict[str, Any]:
    text = path.read_text()
    if path.suffix.lower() == ".json":
        return json.loads(text)
    try:
        import yaml
    except ImportError as exc:
        raise RuntimeError("YAML manifests require PyYAML. Use JSON or install PyYAML.") from exc
    return yaml.safe_load(text)


def link_or_copy(src: Path, dst: Path, mode: str, overwrite: bool) -> None:
    if not src.exists():
        raise FileNotFoundError(src)
    dst.parent.mkdir(parents=True, exist_ok=True)
    if dst.exists() or dst.is_symlink():
        if not overwrite:
            return
        dst.unlink()
    if mode == "copy":
        shutil.copy2(src, dst)
    elif mode == "symlink":
        os.symlink(src, dst)
    else:
        raise ValueError(mode)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--package-manifest", required=True, type=Path)
    args = parser.parse_args()

    package_manifest = load_manifest(args.package_manifest)
    conversion_manifest = load_manifest(Path(package_manifest["paths"]["test_manifest"]))
    submission = package_manifest["submission"]
    paths = package_manifest["paths"]

    pred_dir = Path(paths["prediction_dir"])
    submission_dir = Path(paths["submission_dir"])
    prediction_subdir = submission.get("prediction_subdir", "predictions")
    prediction_suffix = submission.get("prediction_suffix", "_pred")
    file_ending = submission.get("file_ending", conversion_manifest["dataset"]["file_ending"])
    mode = paths.get("mode", "symlink")
    overwrite = bool(paths.get("overwrite", False))

    rows = []
    for case in conversion_manifest["cases"].get("test", []) or []:
        case_id = str(case["id"])
        src = pred_dir / f"{case_id}{file_ending}"
        rel = Path(prediction_subdir) / f"{case_id}{prediction_suffix}{file_ending}"
        link_or_copy(src, submission_dir / rel, mode, overwrite)
        rows.append(
            {
                submission.get("case_id_column", "case_id"): case_id,
                submission.get("prediction_path_column", "predicted_mask_path"): str(rel),
            }
        )

    submission_dir.mkdir(parents=True, exist_ok=True)
    out_csv = submission_dir / "submission.csv"
    with out_csv.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=list(rows[0].keys()) if rows else [])
        writer.writeheader()
        writer.writerows(rows)
    print(f"wrote {out_csv}")


if __name__ == "__main__":
    main()
