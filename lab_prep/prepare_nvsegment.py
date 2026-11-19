#!/usr/bin/env python3
"""Prepare inference in a standalone, GPU-free container after the lab starts."""

import argparse
import json
import os
from pathlib import Path
import subprocess

from setup_lab import Timings, run


def start_preparation(docker, repo, env, runner=run):
    training = runner(docker + ["compose", "ps", "-q", "training"], cwd=repo, env=env, capture=True).stdout.strip()
    if not training:
        raise ValueError("Start the lab before preparing the inference model.")
    info = json.loads(runner(docker + ["inspect", training], env=env, capture=True).stdout)[0]
    mounts = {mount["Destination"]: mount for mount in info["Mounts"]}
    for target in ("/workspace", "/cache"):
        if mounts.get(target, {}).get("Type") != "volume":
            raise ValueError(f"Expected the lab's named volume at {target}")
    name = info["Name"].lstrip("/") + "-nvsegment-prepare"
    existing = runner(docker + ["ps", "-aq", "--filter", f"name=^/{name}$"], env=env, capture=True).stdout.strip()
    if existing:
        previous = json.loads(runner(docker + ["inspect", existing], env=env, capture=True).stdout)[0]
        if previous["State"]["Running"]:
            print(f"Inference preparation is already running: {name}")
            return name
        runner(docker + ["rm", existing], env=env)
    command = docker + ["run", "--detach", "--name", name, "--pull", "never", "--init",
                        "--user", info["Config"]["User"] or "1000:1000", "--read-only",
                        "--tmpfs", "/tmp:rw,nosuid,size=256m", "--cap-drop", "ALL",
                        "--security-opt", "no-new-privileges", "--workdir", "/workspace",
                        "--env", "HF_HOME=/cache/huggingface", "--env", "PYTHONUNBUFFERED=1",
                        "--env", "PYTHONDONTWRITEBYTECODE=1", "--env", "MPLCONFIGDIR=/tmp/matplotlib",
                        "--env", "XDG_CACHE_HOME=/tmp/cache",
                        "--env", "CUDA_VISIBLE_DEVICES=", "--env", "NVIDIA_VISIBLE_DEVICES=void"]
    for target in ("/workspace", "/cache"):
        mount = mounts[target]
        option = f"type=volume,source={mount['Name']},target={target}"
        command += ["--mount", option + (",readonly" if target == "/workspace" else "")]
    command += ["--entrypoint", "python3", info["Image"], "/workspace/tools/prepare_lab_models.py"]
    runner(command, env=env)
    print(f"Inference preparation started: {name}. Check progress with: docker logs -f {name}")
    return name


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=Path(__file__).resolve().parent.parent)
    parser.add_argument("--background", action="store_true", help="Return immediately; Docker keeps the download running.")
    parser.add_argument("--plan", action="store_true")
    args = parser.parse_args()
    if args.plan:
        print("After lab startup: docker run --detach using the training image, read-only workspace and writable model cache; no GPU or Docker socket.")
        return 0
    repo = args.root.expanduser().resolve() / "MIAgent"
    docker = ["docker"]
    env = dict(os.environ)
    for key in ("GITHUB_TOKEN", "GITHUB_TOKEN_FILE", "GH_TOKEN", "MIAgent_CLONE_TOKEN", "MIAgent_GATEWAY_PASSWORD"):
        env.pop(key, None)
    try:
        run(docker + ["info"], env=env, capture=True)
    except subprocess.CalledProcessError:
        docker = ["sudo", "-n", "docker"]
        run(docker + ["info"], env=env, capture=True)
    name = Timings().call("Start NV-Segment background preparation", lambda: start_preparation(docker, repo, env, runner=run))
    if not args.background:
        run(docker + ["logs", "--follow", name], env=env)
        result = run(docker + ["wait", name], env=env, capture=True)
        if result.stdout.strip() != "0":
            raise ValueError("Inference preparation failed; inspect its container logs for details.")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (OSError, ValueError, subprocess.CalledProcessError) as error:
        raise SystemExit(f"NV-Segment preparation stopped: {error}")
