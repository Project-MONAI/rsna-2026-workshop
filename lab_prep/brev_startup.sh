#!/usr/bin/env bash
set -euo pipefail
# Upload/paste this script into a Brev VM-mode Launchable with a public Git Source.
# Brev owns the clone. This entrypoint only prepares and starts that checkout.
python3 - <<'PY'
import os
from pathlib import Path
import subprocess
import sys


def main():
    configured = os.environ.get("MIAgent_LAB_ROOT")
    candidates = [Path(configured).expanduser()] if configured else [
        Path.cwd(),
        Path.home() / "rsna-2026-workshop",
        Path("/home/ubuntu/rsna-2026-workshop"),
        Path.home() / "workspace" / "rsna-2026-workshop",
        Path.home() / "workspace",
    ]
    root = next((path.resolve() for path in candidates
                 if (path / "lab_prep/setup_lab.py").is_file()
                 and (path / "MIAgent/docker-compose.yml").is_file()), None)
    if root is None:
        raise SystemExit("Brev's repository checkout was not found. Attach the public repository "
                         "under Source, then set MIAgent_LAB_ROOT to its checkout directory. "
                         "This startup script does not clone repositories.")
    prepare = os.environ.get("MIAgent_PREPARE_DATA", "true").lower()
    if prepare not in ("true", "false"):
        raise SystemExit("MIAgent_PREPARE_DATA must be true or false.")
    command = [sys.executable, str(root / "lab_prep/setup_lab.py"), "--root", str(root)]
    if prepare == "true":
        command += ["--prepare-data", "--spacing-mm", os.environ.get("MIAgent_DATA_SPACING_MM", "2"),
                    "--unknown-labels", os.environ.get("MIAgent_UNKNOWN_LABELS", "background")]
    print(f"Preparing the Brev checkout at {root}", flush=True)
    subprocess.run(command, check=True, cwd=root)


if __name__ == "__main__":
    main()
PY
