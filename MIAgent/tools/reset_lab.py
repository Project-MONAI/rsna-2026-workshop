#!/usr/bin/env python3
"""Stop the lab before recreating its seed and services; keep model caches."""

import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

if __name__ == "__main__":
    if ROOT == Path("/workspace"):
        raise SystemExit("Run reset_lab.py on the host, outside the student containers.")
    subprocess.run(["docker", "compose", "down"], cwd=ROOT, check=True)
    subprocess.run(["docker", "compose", "up", "-d", "--force-recreate"], cwd=ROOT, check=True)
