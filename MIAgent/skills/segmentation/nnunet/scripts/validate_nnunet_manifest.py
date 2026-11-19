#!/usr/bin/env python3
"""Validate a generic nnU-Net conversion manifest without running nnU-Net."""

from __future__ import annotations

import argparse
import json
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


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--manifest", required=True, type=Path)
    args = parser.parse_args()

    manifest = load_manifest(args.manifest)
    dataset = manifest["dataset"]
    cases = manifest["cases"]
    channels = dataset["channel_names"]
    n_channels = len(channels)

    seen = set()
    errors = []
    for split in ["train", "test"]:
        for case in cases.get(split, []) or []:
            case_id = str(case["id"])
            if case_id in seen:
                errors.append(f"duplicate case id: {case_id}")
            seen.add(case_id)
            images = case["images"]
            if isinstance(images, dict):
                image_paths = [images.get(str(i), images.get(i)) for i in range(n_channels)]
            else:
                image_paths = images
            if len(image_paths) != n_channels:
                errors.append(f"{case_id}: expected {n_channels} images, got {len(image_paths)}")
            for path in image_paths:
                if not path or not Path(path).exists():
                    errors.append(f"{case_id}: missing image {path}")
            if split == "train":
                label = case.get("label")
                if not label or not Path(label).exists():
                    errors.append(f"{case_id}: missing label {label}")

    if errors:
        for error in errors:
            print(f"ERROR: {error}")
        raise SystemExit(1)
    print(f"ok: {len(cases.get('train', []) or [])} train, {len(cases.get('test', []) or [])} test")


if __name__ == "__main__":
    main()
