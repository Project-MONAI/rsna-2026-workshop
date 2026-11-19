#!/usr/bin/env python3
"""Build the normalized multi-modal manifest consumed by the nnU-Net viewer."""

from __future__ import annotations

import argparse
import json
from pathlib import Path


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--images", type=Path, required=True)
    parser.add_argument("--ground-truth", type=Path, required=True)
    parser.add_argument("--predictions", type=Path, required=True)
    parser.add_argument("--metrics", type=Path, required=True)
    parser.add_argument("--dataset-json", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--experiment", required=True)
    parser.add_argument("--checkpoint", required=True)
    parser.add_argument("--split", required=True)
    parser.add_argument("--model", default="nnU-Net")
    parser.add_argument("--training-description", required=True)
    parser.add_argument("--preprocessing", required=True)
    parser.add_argument("--training-log", type=Path, action="append", default=[])
    args = parser.parse_args()

    evaluation = json.loads(args.metrics.read_text())
    dataset = json.loads(args.dataset_json.read_text())
    channel_names = {int(key): str(value) for key, value in dataset["channel_names"].items()}
    label_names = {}
    region_order = iter(dataset.get("regions_class_order", []))
    for name, value in dataset["labels"].items():
        if isinstance(value, list):
            label = int(next(region_order))
        else:
            label = int(value)
        if label != 0:
            label_names[label] = str(name)
    by_name = {
        Path(row["prediction_file"]).name: row["metrics"]
        for row in evaluation["metric_per_case"]
    }
    cases = []
    for prediction in sorted(args.predictions.glob("*.nii.gz")):
        case_id = prediction.name.removesuffix(".nii.gz")
        images = {
            channel_names[channel]: str(
                (args.images / f"{case_id}_{channel:04d}.nii.gz").resolve()
            )
            for channel in sorted(channel_names)
        }
        ground_truth = args.ground_truth / prediction.name
        missing = [path for path in images.values() if not Path(path).is_file()]
        if missing or not ground_truth.is_file():
            raise FileNotFoundError(f"{case_id}: missing {missing or [ground_truth]}")
        cases.append(
            {
                "case_id": case_id,
                "inputs": {"image": images},
                "ground_truth": {"mask": str(ground_truth.resolve())},
                "prediction": {"mask": str(prediction.resolve())},
                "metrics": {"classes": by_name[prediction.name]},
            }
        )
    payload = {
        "provenance": {
            "experiment": args.experiment,
            "model": args.model,
            "checkpoint": args.checkpoint,
            "training_data": args.training_description,
            "split": args.split,
            "evaluator": evaluation.get("provenance", {}),
            "modalities": [channel_names[index] for index in sorted(channel_names)],
            "preprocessing": args.preprocessing,
        },
        "viewer": {
            "labels": {str(label): name for label, name in label_names.items()},
        },
        "training": {
            "logs": [str(path.resolve()) for path in args.training_log],
            "class_names": [label_names[index] for index in sorted(label_names)],
            "title": f"{args.experiment} training diagnostics",
        },
        "cases": cases,
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(payload, indent=2, allow_nan=True) + "\n")
    print(json.dumps({"output": str(args.output.resolve()), "cases": len(cases)}))


if __name__ == "__main__":
    main()
