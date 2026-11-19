#!/usr/bin/env python3
import json
import os
from pathlib import Path


def configure():
    home = Path(os.environ["HOME"])
    home.mkdir(parents=True, exist_ok=True)
    rc = home / ".bashrc"
    contents = rc.read_text() if rc.exists() else ""
    marker = "# MIAgent terminal defaults"
    if marker not in contents:
        with rc.open("a") as stream:
            stream.write("\n" + marker + "\n")
            stream.write("alias ll='ls -alF'\n")
            stream.write("alias la='ls -A'\n")
            stream.write("alias l='ls -CF'\n")
            stream.write("PS1='\\u@\\h:\\w\\$ '\n")
    config_path = Path(os.environ["PASEO_HOME"]) / "config.json"
    config = json.loads(config_path.read_text())
    profiles = config.setdefault("daemon", {}).setdefault("terminalProfiles", [])
    profile = {"id": "miagent-bash", "name": "Bash", "command": "/bin/bash"}
    profiles[:] = [profile] + [item for item in profiles if item.get("id") != profile["id"]]
    config_path.write_text(json.dumps(config, indent=2) + "\n")


if __name__ == "__main__":
    configure()
