#!/usr/bin/env python3
"""Build and run the standalone data-preparation container, without Compose."""

import argparse
import math
import os
from pathlib import Path
import shlex
import subprocess
import sys

IMAGE = "miagent-data-prep:0.1.0"


def container_commands(docker, raw, output, stage, dataset, spacing, labels):
    context = Path(__file__).resolve().parent
    build = [*docker, "build", "--tag", IMAGE, str(context)]
    execute = [*docker, "run", "--rm", "--init", "--user", f"{os.getuid()}:{os.getgid()}",
               "--cap-drop", "ALL", "--security-opt", "no-new-privileges",
               "--mount", f"type=bind,source={raw},target=/raw",
               "--mount", f"type=bind,source={output},target=/data",
               IMAGE, stage, "--dataset", dataset, "--raw-dir", "/raw", "--output-dir", "/data",
               "--spacing-mm", str(spacing), "--unknown-labels", labels]
    return build, execute


def main():
    folder = Path(__file__).resolve().parent
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("stage", choices=("list", "download", "resample", "all"), nargs="?", default="all")
    parser.add_argument("--dataset", choices=("ImageCAS", "ImageCHD", "both"), default="both")
    parser.add_argument("--raw-dir", type=Path, default=folder / "raw")
    parser.add_argument("--output-dir", type=Path, default=folder.parent / "data")
    parser.add_argument("--spacing-mm", type=float, default=2.0)
    parser.add_argument("--unknown-labels", choices=("error", "preserve", "background"), default="background")
    parser.add_argument("--plan", action="store_true")
    args = parser.parse_args()
    if not math.isfinite(args.spacing_mm) or args.spacing_mm <= 0:
        parser.error("--spacing-mm must be finite and positive.")
    raw = args.raw_dir.expanduser().resolve()
    output = args.output_dir.expanduser().resolve()
    if any(',' in str(path) for path in (raw, output)):
        parser.error("Mount paths cannot contain commas.")
    if raw == output or raw.is_relative_to(output) or output.is_relative_to(raw):
        parser.error("Raw and output directories must be separate, non-nested paths.")
    docker = ["docker"]
    if args.plan:
        for command in container_commands(docker, raw, output, args.stage, args.dataset, args.spacing_mm, args.unknown_labels):
            print(shlex.join(command))
        return 0
    env = dict(os.environ)
    for key in ("GITHUB_TOKEN", "GITHUB_TOKEN_FILE", "GH_TOKEN", "MIAgent_CLONE_TOKEN", "MIAgent_GATEWAY_PASSWORD"):
        env.pop(key, None)
    def run(command, capture=False):
        return subprocess.run(command, env=env, check=True, text=True, capture_output=capture)
    try:
        run([*docker, "info"], capture=True)
    except subprocess.CalledProcessError:
        docker = ["sudo", "-n", "docker"]
        run([*docker, "info"], capture=True)
    raw.mkdir(parents=True, exist_ok=True)
    output.mkdir(parents=True, exist_ok=True)
    for command in container_commands(docker, raw, output, args.stage, args.dataset, args.spacing_mm, args.unknown_labels):
        run(command)
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (OSError, subprocess.CalledProcessError) as error:
        print(f"Data preparation stopped: {error}", file=sys.stderr)
        raise SystemExit(1)
