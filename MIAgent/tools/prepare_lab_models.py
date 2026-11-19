#!/usr/bin/env python3
"""Prepare pinned NV-Segment-CT inference assets without loading a model or GPU."""

import argparse
from datetime import datetime, timezone
import fcntl
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import time

MODEL_ID = "nvidia/NV-Segment-CT"
REVISION = "afb51518689f71e6abb367ee6301b2cd0225c66a"
WEIGHT = "vista3d_pretrained_model/model.pt"
WEIGHT_BYTES = 871970895
WEIGHT_SHA256 = "c92bab26d00b4a5d89fa8a383900cdeb88302fd318e5e816df0bbec7106d9a1b"
CODE_FILES = (
    "hugging_face_pipeline.py", "vista3d_model.py", "vista3d_config.py",
    "vista3d_pipeline.py", "scripts/__init__.py", "scripts/inferer.py", "scripts/early_stop_score_function.py",
    "config.json", "metadata.json", "vista3d_pretrained_model/config.json",
    "LICENSE", "data_license.txt",
)


def bundle_path(cache):
    return Path(cache) / "bundles/nv-segment-ct"


def status_path(cache):
    return Path(cache) / "model-preparation/nv-segment-ct.json"


def bundle_errors(bundle):
    errors = [f"Missing {name}" for name in (*CODE_FILES, "label_dict.json", WEIGHT)
              if not (bundle / name).is_file()]
    weight = bundle / WEIGHT
    if weight.is_file() and weight.stat().st_size != WEIGHT_BYTES:
        errors.append("Checkpoint size does not match the pinned model")
    for name in ("config.json", "metadata.json", "vista3d_pretrained_model/config.json", "label_dict.json"):
        if (bundle / name).is_file():
            try:
                value = json.loads((bundle / name).read_text())
                if not isinstance(value, dict) or not value:
                    errors.append(f"Empty or invalid {name}")
            except (ValueError, OSError):
                errors.append(f"Invalid JSON in {name}")
    return errors


def model_status(cache):
    try:
        result = json.loads(status_path(cache).read_text())
    except (OSError, ValueError):
        return {"status": "not_started", "message": "Inference model preparation has not started."}
    if not isinstance(result, dict) or result.get("status") not in {"ready", "preparing", "failed"}:
        return {"status": "failed", "message": "Invalid inference preparation status file."}
    if result.get("status") == "ready":
        errors = bundle_errors(bundle_path(cache))
        if result.get("revision") != REVISION:
            errors.append("Prepared revision differs from the configured model")
        if result.get("weight_sha256") != WEIGHT_SHA256:
            errors.append("Checkpoint has not passed checksum validation")
        if errors:
            return {**result, "status": "failed", "message": "; ".join(errors)}
    return result


def write_status(cache, state, started, **extra):
    record = {"model": MODEL_ID, "revision": REVISION, "status": state,
              "updated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
              "seconds": round(time.monotonic() - started, 3), **extra}
    target = status_path(cache)
    target.parent.mkdir(parents=True, exist_ok=True)
    temporary = target.with_suffix(f".{os.getpid()}.tmp")
    temporary.write_text(json.dumps(record, indent=2) + "\n")
    temporary.replace(target)
    print(json.dumps(record), flush=True)
    return record


def digest(path):
    sha = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(8 * 1024 * 1024), b""):
            sha.update(chunk)
    return sha.hexdigest()


def prepare(cache, downloader=None, validator=None):
    cache = Path(cache)
    started = time.monotonic()
    status_path(cache).parent.mkdir(parents=True, exist_ok=True)
    with status_path(cache).with_suffix(".lock").open("w") as lock:
        try:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            print("NV-Segment-CT preparation is already running.", flush=True)
            return model_status(cache)
        try:
            previous = model_status(cache)
            bundle = bundle_path(cache)
            bundle.mkdir(parents=True, exist_ok=True)
            weight = bundle / WEIGHT
            write_status(cache, "preparing", started, message="Checking cached inference assets.")
            cached_weight = weight.is_file() and weight.stat().st_size == WEIGHT_BYTES and digest(weight) == WEIGHT_SHA256
            if weight.exists() and not cached_weight:
                weight.unlink()
            legacy = cache / "bundles/nv-segment-ct-finetune" / WEIGHT
            if not cached_weight and legacy.is_file() and legacy.stat().st_size == WEIGHT_BYTES and digest(legacy) == WEIGHT_SHA256:
                weight.parent.mkdir(parents=True, exist_ok=True)
                os.link(legacy, weight)
                cached_weight = True
            # Reuse valid assets offline; otherwise fetch only the pinned files.
            if not cached_weight or bundle_errors(bundle) or previous.get("status") != "ready":
                if downloader is None:
                    from huggingface_hub import snapshot_download
                    downloader = snapshot_download
                patterns = list(CODE_FILES) + ([] if cached_weight else [WEIGHT])
                message = "Downloading pinned inference code; reusing the cached checkpoint." if cached_weight else "Downloading pinned inference code and weights."
                write_status(cache, "preparing", started, message=message,
                             checkpoint_bytes=WEIGHT_BYTES, reused_checkpoint=cached_weight)
                downloader(repo_id=MODEL_ID, revision=REVISION, local_dir=str(bundle),
                           allow_patterns=patterns, max_workers=4)
                metadata = json.loads((bundle / "metadata.json").read_text())
                labels = metadata["network_data_format"]["outputs"]["pred"]["channel_def"]
                label_dict = {name: int(index) for index, name in labels.items()}
                if len(label_dict) < 2:
                    raise ValueError("Model metadata does not contain a label dictionary")
                (bundle / "label_dict.json").write_text(json.dumps(label_dict, indent=2) + "\n")
            errors = bundle_errors(bundle)
            if errors:
                raise ValueError("; ".join(errors))
            if digest(weight) != WEIGHT_SHA256:
                raise ValueError("Downloaded checkpoint failed SHA-256 validation")
            if validator is None:
                env = {**os.environ, "HF_HUB_OFFLINE": "1", "TRANSFORMERS_OFFLINE": "1", "CUDA_VISIBLE_DEVICES": ""}
                subprocess.run([sys.executable, "-c", "import sys; sys.path.insert(0, sys.argv[1]); import hugging_face_pipeline", str(bundle)],
                               env=env, check=True)
            else:
                validator(bundle)
            return write_status(cache, "ready", started, bundle=str(bundle), weight_sha256=WEIGHT_SHA256,
                                checkpoint_bytes=WEIGHT_BYTES, message="NV-Segment-CT inference is ready.")
        except Exception as error:
            write_status(cache, "failed", started, message=str(error))
            raise


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--cache-dir", type=Path, default=Path("/cache"))
    parser.add_argument("--status", action="store_true", help="Read readiness without downloading or importing imaging libraries.")
    args = parser.parse_args()
    if args.status:
        result = model_status(args.cache_dir)
        print(json.dumps(result, indent=2))
        return 0 if result["status"] == "ready" else 2
    return 0 if prepare(args.cache_dir)["status"] == "ready" else 2


if __name__ == "__main__":
    raise SystemExit(main())
