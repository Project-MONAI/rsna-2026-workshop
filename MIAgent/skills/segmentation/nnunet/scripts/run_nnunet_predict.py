#!/usr/bin/env python3
"""Run nnUNetv2_predict with explicit arguments."""

from __future__ import annotations

import argparse
import subprocess
from pathlib import Path


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--input-dir", required=True, type=Path)
    parser.add_argument("--output-dir", required=True, type=Path)
    parser.add_argument("--dataset-id", required=True)
    parser.add_argument("--configuration", default="3d_fullres")
    parser.add_argument("--trainer", default="nnUNetTrainer")
    parser.add_argument("--plans", default="nnUNetPlans")
    parser.add_argument("--folds", default="all")
    parser.add_argument("--checkpoint", default="checkpoint_final.pth")
    parser.add_argument("--extra", nargs=argparse.REMAINDER, default=[])
    args = parser.parse_args()

    args.output_dir.mkdir(parents=True, exist_ok=True)
    cmd = [
        "nnUNetv2_predict",
        "-i", str(args.input_dir),
        "-o", str(args.output_dir),
        "-d", str(args.dataset_id),
        "-c", args.configuration,
        "-tr", args.trainer,
        "-p", args.plans,
        "-f", args.folds,
        "-chk", args.checkpoint,
    ] + args.extra
    print(" ".join(cmd))
    subprocess.run(cmd, check=True)


if __name__ == "__main__":
    main()
