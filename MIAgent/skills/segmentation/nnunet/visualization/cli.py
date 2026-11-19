#!/usr/bin/env python3
"""Command-line interface for reusable nnU-Net visual evidence."""

from __future__ import annotations

import argparse
import json

from .training import render_training_curves
from .viewer import visualize_run


def main() -> None:
    parser = argparse.ArgumentParser()
    subparsers = parser.add_subparsers(dest="command", required=True)

    curves = subparsers.add_parser("curves", help="render curves from one or more resumed nnU-Net logs")
    curves.add_argument("--log", action="append", required=True)
    curves.add_argument("--output", required=True)
    curves.add_argument("--json")
    curves.add_argument("--class-name", action="append")
    curves.add_argument("--title", default="nnU-Net training diagnostics")

    viewer = subparsers.add_parser("viewer", help="build an indexed segmentation result viewer")
    viewer.add_argument("--manifest", required=True)
    viewer.add_argument("--output", required=True)
    viewer.add_argument("--training-log", action="append")
    viewer.add_argument("--reuse-assets", action="store_true")

    args = parser.parse_args()
    if args.command == "curves":
        result = render_training_curves(
            args.log,
            args.output,
            output_json=args.json,
            class_names=args.class_name,
            title=args.title,
        )
        print(json.dumps(result["summary"], indent=2))
    else:
        print(
            visualize_run(
                args.manifest,
                args.output,
                training_logs=args.training_log,
                reuse_assets=args.reuse_assets,
            )
        )


if __name__ == "__main__":
    main()
