#!/usr/bin/env python3
"""Clone an nnU-Net plan with an explicit DDP-safe global batch size."""

from __future__ import annotations

import argparse
import json
from pathlib import Path


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--configuration", default="3d_fullres")
    parser.add_argument("--gpus", type=int, required=True)
    parser.add_argument("--global-batch", type=int)
    parser.add_argument("--report", type=Path)
    args = parser.parse_args()

    if args.gpus < 1:
        raise ValueError("--gpus must be positive")
    global_batch = args.global_batch or args.gpus
    if global_batch < args.gpus or global_batch % args.gpus:
        raise ValueError("global batch must be at least and divisible by the GPU count")

    plans = json.loads(args.input.read_text())
    configuration = plans["configurations"][args.configuration]
    planned_batch = int(configuration["batch_size"])
    configuration["batch_size"] = global_batch
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(plans, indent=2) + "\n")

    report = {
        "source_plan": str(args.input.resolve()),
        "ddp_plan": str(args.output.resolve()),
        "configuration": args.configuration,
        "single_gpu_planned_batch": planned_batch,
        "world_size": args.gpus,
        "global_batch": global_batch,
        "per_rank_batch": global_batch // args.gpus,
        "reason": "DDP requires global batch >= world size; one sample per rank gives dataset-sized epochs",
    }
    if args.report:
        args.report.parent.mkdir(parents=True, exist_ok=True)
        args.report.write_text(json.dumps(report, indent=2) + "\n")
    print(json.dumps(report))


if __name__ == "__main__":
    main()
