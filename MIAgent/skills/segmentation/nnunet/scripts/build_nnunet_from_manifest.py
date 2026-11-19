#!/usr/bin/env python3
"""Build an nnU-Net v2 raw dataset from a generic manifest.

The manifest is challenge-specific and should live in `challenge/<name>/jobs/`.
This script is intentionally challenge-agnostic.
"""

from __future__ import annotations

import argparse
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
        raise ValueError(f"Unknown mode: {mode}")


def dataset_dir(nnunet_raw: Path, dataset_id: int, dataset_name: str) -> Path:
    return nnunet_raw / f"Dataset{dataset_id:03d}_{dataset_name}"


def normalized_channels(dataset: dict[str, Any]) -> dict[str, str]:
    channels = dataset["channel_names"]
    if isinstance(channels, list):
        return {str(i): name for i, name in enumerate(channels)}
    return {str(k): str(v) for k, v in channels.items()}


def write_dataset_json(out_dir: Path, manifest: dict[str, Any], num_training: int) -> None:
    dataset = manifest["dataset"]
    payload = {
        "channel_names": normalized_channels(dataset),
        "labels": dataset["labels"],
        "numTraining": num_training,
        "file_ending": dataset["file_ending"],
    }
    for key in ["name", "description", "reference", "release", "licence", "license"]:
        value = dataset.get(key)
        if value:
            payload[key] = value
    reader = dataset.get("overwrite_image_reader_writer")
    if reader:
        payload["overwrite_image_reader_writer"] = reader
    (out_dir / "dataset.json").write_text(json.dumps(payload, indent=2) + "\n")


def image_list(case: dict[str, Any], expected_channels: int) -> list[Path]:
    images = case["images"]
    if isinstance(images, dict):
        ordered = [images[str(i)] if str(i) in images else images[i] for i in range(expected_channels)]
    else:
        ordered = images
    if len(ordered) != expected_channels:
        raise ValueError(
            f"Case {case.get('id')} has {len(ordered)} images, expected {expected_channels}"
        )
    return [Path(p) for p in ordered]


def build(manifest: dict[str, Any]) -> Path:
    dataset = manifest["dataset"]
    output = manifest["output"]
    cases = manifest["cases"]

    channels = normalized_channels(dataset)
    expected_channels = len(channels)
    file_ending = dataset["file_ending"]
    mode = output.get("mode", "symlink")
    overwrite = bool(output.get("overwrite", False))
    out_dir = dataset_dir(Path(output["nnunet_raw"]), int(dataset["id"]), dataset["name"])

    for split_name, image_folder, label_folder in [
        ("train", "imagesTr", "labelsTr"),
        ("test", "imagesTs", None),
    ]:
        for case in cases.get(split_name, []) or []:
            case_id = str(case["id"])
            for channel_idx, src in enumerate(image_list(case, expected_channels)):
                dst = out_dir / image_folder / f"{case_id}_{channel_idx:04d}{file_ending}"
                link_or_copy(src, dst, mode, overwrite)
            if label_folder:
                label = case.get("label")
                if not label:
                    raise ValueError(f"Training case {case_id} is missing label")
                dst = out_dir / label_folder / f"{case_id}{file_ending}"
                link_or_copy(Path(label), dst, mode, overwrite)

    write_dataset_json(out_dir, manifest, len(cases.get("train", []) or []))
    return out_dir


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--manifest", required=True, type=Path)
    args = parser.parse_args()

    manifest = load_manifest(args.manifest)
    out_dir = build(manifest)
    print(f"wrote {out_dir}")


if __name__ == "__main__":
    main()
