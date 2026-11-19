#!/usr/bin/env python3
import json
import os
from pathlib import Path


def configure():
    home = Path(os.environ["HOME"])
    config_path = Path(os.environ["PASEO_HOME"]) / "config.json"
    config_path.parent.mkdir(parents=True, exist_ok=True)
    config = json.loads(config_path.read_text()) if config_path.exists() else {"version": 1}
    paths = {
        "XDG_CONFIG_HOME": str(home / ".config"),
        "XDG_DATA_HOME": str(home / ".local/share"),
        "XDG_STATE_HOME": str(home / ".local/state"),
        "XDG_CACHE_HOME": str(home / ".cache"),
    }
    for path in paths.values():
        Path(path).mkdir(parents=True, exist_ok=True)
    providers = config.setdefault("agents", {}).setdefault("providers", {})
    for provider in ("claude", "codex", "copilot", "pi", "omp"):
        providers.setdefault(provider, {})["enabled"] = False
    opencode = providers.setdefault("opencode", {})
    opencode.update({
        "enabled": True,
        "label": "Local Qwen (OpenCode)",
        "models": [{
            "id": os.environ["OPENCODE_MODEL"],
            "label": "Local Qwen",
            "isDefault": True,
        }],
    })
    opencode.setdefault("env", {}).update(paths)
    opencode["env"]["OPENCODE_CONFIG"] = "/workspace/opencode.json"
    profiles = config.setdefault("daemon", {}).setdefault("agentProfiles", [])
    profile = next((entry for entry in profiles if entry.get("id") == "miagent-local-qwen"), None)
    if profile is None:
        profile = {"id": "miagent-local-qwen"}
        profiles.append(profile)
    profile.update({
        "name": "Local Qwen",
        "provider": "opencode",
        "model": os.environ["OPENCODE_MODEL"],
    })
    profile.setdefault("featureValues", {})["auto_accept"] = True
    config_path.write_text(json.dumps(config, indent=2) + "\n")


if __name__ == "__main__":
    configure()
