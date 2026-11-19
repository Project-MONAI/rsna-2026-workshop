#!/usr/bin/env python3
"""Validate and publish one NV-Segment CT inference for the MIAgent NiiVue viewer."""

from __future__ import annotations

import argparse
import json
import shutil
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import quote

import nibabel as nib
import numpy as np


SKILL_CONFIG = {
    "nv_segment_ct": {
        "name": "NV-Segment-CT",
        "mapping": {
            115: (1, "heart"),
            6: (2, "aorta"),
            108: (3, "left atrial appendage"),
            119: (4, "pulmonary vein"),
        },
        "required_label": 115,
    },
    "nv_segment_ctmr": {
        "name": "NV-Segment-CTMR",
        "mapping": {
            151: (1, "left ventricle"),
            152: (2, "right ventricle"),
            149: (3, "left atrium"),
            153: (4, "right atrium"),
            154: (5, "left-ventricle myocardium"),
            6: (6, "aorta"),
            171: (7, "pulmonary artery"),
        },
        "required_label": 151,
    },
}


def require(condition: bool, message: str) -> None:
    if not condition:
        raise SystemExit(f"publish-nv-inference: {message}")


def inference_root(path: Path) -> Path:
    for candidate in (path, *path.parents):
        if candidate.name == "inference_tmp":
            return candidate
    raise SystemExit("publish-nv-inference: run directory must be under inference_tmp")


def viewer_path(path: Path) -> str:
    return "/".join(quote(part) for part in path.parts)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run-dir", required=True, type=Path)
    parser.add_argument("--image", type=Path, help="Original CT under /data, or a prepared image inside the run directory; no copy is made.")
    parser.add_argument("--data-root", type=Path, default=Path("/data"))
    parser.add_argument("--overlay", choices=("global", "heart"), default="global")
    parser.add_argument("--hu-offset", type=float, default=0, help="Explicit display offset, not an intensity conversion.")
    args = parser.parse_args()

    run_dir = args.run_dir.expanduser().resolve()
    root = inference_root(run_dir)
    require(run_dir.parent == root, "run directory must be a direct child of inference_tmp")
    image_path = (args.image or run_dir / "image.nii.gz").expanduser().resolve()
    result_path = run_dir / "result.json"
    require(image_path.is_file(), f"missing input image: {image_path}")
    data_root = args.data_root.expanduser().resolve()
    require(image_path.is_relative_to(data_root) or image_path.is_relative_to(run_dir),
            "input image must be under the data root or inside the run directory")
    require(np.isfinite(args.hu_offset), "HU display offset must be finite")
    require(result_path.is_file(), f"missing skill result: {result_path}")

    try:
        result = json.loads(result_path.read_text())
    except (OSError, json.JSONDecodeError) as exc:
        raise SystemExit(f"publish-nv-inference: invalid result.json: {exc}") from exc

    skill = str(result.get("skill") or "")
    require(skill in SKILL_CONFIG, "result is not from a supported NV-Segment skill")
    config = SKILL_CONFIG[skill]
    mapping = config["mapping"]
    invocation = result.get("invocation") or {}
    output = result.get("output") or {}
    geometry = output.get("geometry") or {}
    if skill == "nv_segment_ctmr":
        require(invocation.get("exit_code") == 0, "NV-Segment invocation did not exit successfully")
    require(output.get("any_label_present") is True, "prediction has no foreground labels")
    require(output.get("label_set_valid") is True, "prediction contains invalid label IDs")
    require(geometry.get("shape_match") is True, "prediction shape differs from the input")
    require(geometry.get("spacing_match") is True, "prediction spacing differs from the input")
    require(geometry.get("affine_match") is True, "prediction affine differs from the input")

    source_mask = Path(str(output.get("path") or "")).expanduser().resolve()
    require(source_mask.is_file(), "skill output mask does not exist")
    try:
        source_mask.relative_to(run_dir)
    except ValueError as exc:
        raise SystemExit("publish-nv-inference: skill output must remain inside the run directory") from exc

    global_path = run_dir / "prediction_global.nii.gz"
    image_img = nib.load(str(image_path))
    mask_img = nib.load(str(source_mask))
    require(image_img.shape == mask_img.shape, "actual image and mask shapes differ")
    require(np.allclose(image_img.affine, mask_img.affine, rtol=0, atol=1e-4),
            "actual image and mask affines differ")
    mask = np.asarray(mask_img.dataobj)
    require(np.isfinite(mask).all() and np.equal(mask, np.floor(mask)).all() and (mask >= 0).all(),
            "mask must contain finite nonnegative integer label IDs")
    require(np.any(mask > 0), "actual prediction contains no foreground")
    if source_mask != global_path:
        shutil.copy2(source_mask, global_path)
    remapped = np.zeros(mask.shape, dtype=np.uint8)
    counts: dict[str, int] = {}
    for global_id, (viewer_id, name) in mapping.items():
        selected = mask == global_id
        count = int(np.count_nonzero(selected))
        remapped[selected] = viewer_id
        counts[name] = count

    required_name = mapping[config["required_label"]][1]
    if args.overlay == "heart":
        require(counts[required_name] > 0, f"required {required_name} label is absent")
    heart_path = run_dir / "prediction_heart.nii.gz"
    header = mask_img.header.copy()
    header.set_data_dtype(np.uint8)
    if args.overlay == "heart":
        nib.save(nib.Nifti1Image(remapped, mask_img.affine, header), str(heart_path))

    relative_run = run_dir.relative_to(root)
    run_url = viewer_path(Path("inference_tmp") / relative_run)
    if image_path.is_relative_to(data_root):
        image_url = "data-files/" + viewer_path(image_path.relative_to(data_root))
    else:
        image_url = "files/" + viewer_path(Path("inference_tmp") / image_path.relative_to(root))
    overlay_path = heart_path if args.overlay == "heart" else global_path
    prediction_url = f"files/{run_url}/{overlay_path.name}"
    query = (
        f"images={quote(image_url, safe='/')}&"
        f"overlays={quote(prediction_url, safe='/')}&"
        f"huOffset={args.hu_offset}"
    )
    if args.overlay == "heart":
        query += "&palette=heart"
    redirect = f"../../../nii?{query}"
    (run_dir / "result_viewer.html").write_text(
        "<!doctype html>\n"
        "<html><head><meta charset=\"utf-8\"><title>NV-Segment inference</title></head>\n"
        f"<body><p>Opening NiiVue… <a href=\"{redirect}\">Open manually</a></p>\n"
        f"<script>window.location.replace({json.dumps(redirect)});</script></body></html>\n"
    )

    manifest = {
        "created_at_utc": datetime.now(timezone.utc).isoformat(),
        "purpose": f"educational single-case {config['name']} inference",
        "skill": skill,
        "clinical_use": False,
        "input": str(image_path),
        "input_url": image_url,
        "image_copied": False,
        "hu_display_offset": args.hu_offset,
        "prediction_global": "prediction_global.nii.gz",
        "prediction_viewer": overlay_path.name,
        "result": "result.json",
        "viewer": "result_viewer.html",
        "global_to_viewer": {
            str(global_id): {"viewer_id": viewer_id, "anatomy": name}
            for global_id, (viewer_id, name) in mapping.items()
        } if args.overlay == "heart" else {},
        "validation": {
            "invocation_exit_code": invocation.get("exit_code"),
            "foreground_present": output.get("any_label_present"),
            "label_set_valid": output.get("label_set_valid"),
            "shape_matches": geometry.get("shape_match"),
            "spacing_matches": geometry.get("spacing_match"),
            "affine_matches": geometry.get("affine_match"),
        },
        "foreground_voxels": counts if args.overlay == "heart" else {
            str(int(label)): int(np.count_nonzero(mask == label))
            for label in np.unique(mask) if label > 0
        },
        "ground_truth_used": False,
    }
    (run_dir / "manifest.json").write_text(json.dumps(manifest, indent=2) + "\n")
    (run_dir / "README.md").write_text(
        f"# {run_dir.name}\n\n"
        f"Single-case educational {config['name']} inference. No ground-truth label was used.\n\n"
        "Open `result_viewer.html` in the inference file viewer to inspect the CT and prediction overlay.\n\n"
        "This output is not clinically validated and must not be used for diagnosis or treatment.\n"
    )
    print(json.dumps(manifest, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
