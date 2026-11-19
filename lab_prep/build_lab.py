#!/usr/bin/env python3
"""Time an uncached lab build, image pulls, and Qwen download."""

import argparse
import json
import os
import subprocess
import time
from datetime import datetime, timezone
from pathlib import Path

LAB_ROOT = Path(__file__).resolve().parent.parent
ROOT = LAB_ROOT / "MIAgent"
REPORTS = LAB_ROOT / "build_reports"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--resume", action="store_true", help="Resume the latest incomplete timing report.")
    args = parser.parse_args()
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    if args.resume:
        reports = sorted(REPORTS.iterdir())[-1]
        result = json.loads((reports / "timings.json").read_text())
    else:
        reports = REPORTS / stamp
        reports.mkdir(parents=True)
        result = {"started_at_utc": stamp, "stages": [], "no_layer_cache": True}
    stages = (
        ("build", ["--profile", "build", "build", "--no-cache", "--pull"]),
        ("image_pull", ["pull", "chat"]),
        ("qwen_download", ["--profile", "download", "run", "--rm", "--no-deps", "llm-download"]),
    )
    for name, arguments in stages:
        if any(stage["name"] == name and stage["return_code"] == 0 for stage in result["stages"]):
            continue
        command = ["docker", "compose", *arguments]
        stage_started = time.monotonic()
        print(f"Starting {name}; log: {reports / (name + '.log')}", flush=True)
        with (reports / (name + ".log")).open("w") as log:
            completed = subprocess.run(command, cwd=ROOT, stdout=log, stderr=subprocess.STDOUT,
                                       env={**os.environ, "BUILDKIT_PROGRESS": "plain"})
        result["stages"].append({"name": name, "seconds": round(time.monotonic() - stage_started, 3),
                                  "return_code": completed.returncode})
        result["total_seconds"] = round(sum(stage["seconds"] for stage in result["stages"]), 3)
        (reports / "timings.json").write_text(json.dumps(result, indent=2) + "\n")
        print(json.dumps(result["stages"][-1]), flush=True)
        if completed.returncode:
            print(f"Failed; inspect {reports / (name + '.log')}", flush=True)
            return completed.returncode
    print(f"Total: {result['total_seconds']} seconds. Report: {reports / 'timings.json'}", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
