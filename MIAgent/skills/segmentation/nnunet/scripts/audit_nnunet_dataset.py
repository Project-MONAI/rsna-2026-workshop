#!/usr/bin/env python3
"""Audit pairing, geometry, finiteness, and labels in an nnU-Net raw dataset."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

import nibabel as nib
import numpy as np


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--dataset", type=Path, required=True)
    parser.add_argument("--archive", type=Path)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()

    dataset_json = json.loads((args.dataset / "dataset.json").read_text())
    channels = sorted(int(key) for key in dataset_json["channel_names"])
    labels = sorted(int(value) for value in dataset_json["labels"].values())
    expected_labels = set(labels)
    label_paths = sorted((args.dataset / "labelsTr").glob("*.nii.gz"))
    expected_cases = int(dataset_json["numTraining"])
    if len(label_paths) != expected_cases:
        raise ValueError(f"expected {expected_cases} labels, found {len(label_paths)}")

    spacings: list[list[float]] = []
    shapes: list[list[int]] = []
    observed_labels: set[int] = set()
    case_ids: list[str] = []
    for label_path in label_paths:
        case_id = label_path.name.removesuffix(".nii.gz")
        case_ids.append(case_id)
        label_nii = nib.load(str(label_path))
        label = np.asanyarray(label_nii.dataobj)
        if not np.all(np.isfinite(label)):
            raise ValueError(f"{case_id}: non-finite label values")
        rounded = np.rint(label).astype(np.int16)
        if not np.allclose(label, rounded):
            raise ValueError(f"{case_id}: non-integral label values")
        observed_labels.update(int(value) for value in np.unique(rounded))
        shapes.append(list(label_nii.shape))
        spacings.append([float(value) for value in label_nii.header.get_zooms()[:3]])
        for channel in channels:
            image_path = args.dataset / "imagesTr" / f"{case_id}_{channel:04d}.nii.gz"
            if not image_path.is_file():
                raise FileNotFoundError(image_path)
            image_nii = nib.load(str(image_path))
            if image_nii.shape != label_nii.shape:
                raise ValueError(f"{case_id} channel {channel}: shape mismatch")
            if not np.allclose(image_nii.affine, label_nii.affine, atol=1e-4):
                raise ValueError(f"{case_id} channel {channel}: affine mismatch")
            image = np.asanyarray(image_nii.dataobj)
            if not np.all(np.isfinite(image)):
                raise ValueError(f"{case_id} channel {channel}: non-finite values")
    if not observed_labels.issubset(expected_labels):
        raise ValueError(f"observed labels outside dataset.json: {observed_labels - expected_labels}")

    payload = {
        "dataset": args.dataset.name,
        "dataset_path": str(args.dataset.resolve()),
        "archive": str(args.archive.resolve()) if args.archive else None,
        "archive_sha256": sha256(args.archive) if args.archive else None,
        "cases": len(case_ids),
        "channels": channels,
        "channel_names": dataset_json["channel_names"],
        "expected_labels": labels,
        "observed_labels": sorted(observed_labels),
        "geometry": "all image channels match their reference label shape and affine",
        "unique_shapes": sorted({tuple(shape) for shape in shapes}),
        "spacing_min": np.min(np.asarray(spacings), axis=0).tolist(),
        "spacing_median": np.median(np.asarray(spacings), axis=0).tolist(),
        "spacing_max": np.max(np.asarray(spacings), axis=0).tolist(),
        "case_ids": case_ids,
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(payload, indent=2) + "\n")
    print(json.dumps({key: payload[key] for key in ("dataset", "cases", "channels", "observed_labels")}))


if __name__ == "__main__":
    main()
