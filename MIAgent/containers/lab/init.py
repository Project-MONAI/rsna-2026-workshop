#!/usr/bin/env python3
"""Seed shared lab state once per initialization-container lifetime."""

import os
import shutil
from pathlib import Path


def initialize(seed: Path, workspace: Path, runtime: Path, cache: Path, marker: Path) -> None:
    if marker.exists():
        return
    for target in (workspace, runtime):
        target.mkdir(parents=True, exist_ok=True)
        for child in target.iterdir():
            if child.is_dir() and not child.is_symlink():
                shutil.rmtree(child)
            else:
                child.unlink()
    shutil.copytree(seed, workspace, dirs_exist_ok=True, symlinks=True)
    for directory in (
        "logs", "locks/gpu0.shared", "heartbeats", "mlflow/artifacts",
        "nnunet/raw", "nnunet/preprocessed", "nnunet/results",
        "tracking-home", "paseo-home", "caches/matplotlib", "caches/xdg",
    ):
        (runtime / directory).mkdir(parents=True, exist_ok=True)
    for directory in ("huggingface", "torch", "torchinductor", "triton", "upstreams"):
        (cache / directory).mkdir(parents=True, exist_ok=True)
        (runtime / "caches" / directory).symlink_to(cache / directory, target_is_directory=True)
    (runtime / "upstreams").symlink_to(cache / "upstreams", target_is_directory=True)
    (workspace / "inference_tmp").mkdir(exist_ok=True)
    # Bundle downloads and upstream checkouts survive a student-state reset.
    for skill in (workspace / "skills").rglob("bundle"):
        if not skill.is_dir() or skill.is_symlink():
            continue
        persistent = cache / "bundles" / skill.parent.name
        shutil.copytree(skill, persistent, dirs_exist_ok=True, symlinks=True)
        shutil.rmtree(skill)
        skill.symlink_to(persistent, target_is_directory=True)
    # Fresh clones contain no downloaded bundles. Reconnect persistent caches anyway.
    for name in ("nv-segment-ct", "nv-segment-ct-finetune"):
        skill = workspace / "skills/segmentation" / name
        if not skill.is_dir():
            continue
        persistent = cache / "bundles" / name
        persistent.mkdir(parents=True, exist_ok=True)
        bundle = skill / "bundle"
        if bundle.is_symlink():
            bundle.unlink()
        if not bundle.exists():
            bundle.symlink_to(persistent, target_is_directory=True)
    (workspace / ".workbench_data").mkdir(exist_ok=True)
    (workspace / ".workbench_data/upstreams").symlink_to(cache / "upstreams", target_is_directory=True)
    settings = {
        "MIAgent_HOST_ROOT": "/workspace",
        "MIAgent_RUNTIME_DIR": "/runtime",
        "MIAgent_DATA_DIR": os.environ.get("MIAgent_DATA_DIR", "../data"),
        "LOCAL_UID": os.environ.get("LOCAL_UID", "1000"),
        "LOCAL_GID": os.environ.get("LOCAL_GID", "1000"),
        "DOCKER_GID": os.environ.get("DOCKER_GID", "983"),
        "MIAgent_HTTP_PORT": os.environ.get("MIAgent_HTTP_PORT", "8088"),
        "MIAgent_CHAT_GATE_TOKEN": os.environ.get("MIAgent_CHAT_GATE_TOKEN", "miagent-student-lab"),
        "MIAgent_LLM_CACHE_VOLUME": os.environ.get("MIAgent_LLM_CACHE_VOLUME", "miagent-qwen-cache"),
        "NVIDIA_API_KEY": "",
        "MIAgent_LLM_API_KEY": "",
    }
    (workspace / ".env").write_text("".join(f"{key}={value}\n" for key, value in settings.items()))
    (workspace / ".env").chmod(0o600)
    uid, gid = int(settings["LOCAL_UID"]), int(settings["LOCAL_GID"])
    for root in (workspace, runtime, cache):
        os.chown(root, uid, gid)
        for parent, directories, files in os.walk(root, followlinks=False):
            for name in directories + files:
                os.chown(Path(parent) / name, uid, gid, follow_symlinks=False)
    marker.parent.mkdir(parents=True, exist_ok=True)
    marker.touch()


if __name__ == "__main__":
    initialize(Path("/opt/miagent-seed"), Path("/workspace"), Path("/runtime"),
               Path("/cache"), Path("/var/lib/miagent-lab/initialized"))
