"""Focused regression checks for the local training-stage GPU gate."""

from __future__ import annotations

import importlib.util
import json
from pathlib import Path
from types import SimpleNamespace

import pytest


def load_launcher() -> object:
    path = Path(__file__).resolve().parents[1] / "miagent_local.py"
    spec = importlib.util.spec_from_file_location("miagent_local", path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_training_gate_requires_approved_record(tmp_path: Path, monkeypatch: object) -> None:
    launcher = load_launcher()
    monkeypatch.setattr(launcher, "ROOT", tmp_path)
    try:
        launcher.require_training_optimization("cq500", "baseline001")
    except RuntimeError as exc:
        assert "optimization" in str(exc)
    else:  # pragma: no cover
        raise AssertionError("missing record should block training")

    record = tmp_path / "challenge/cq500/baselines/baseline001/gpu_optimization/approved.json"
    record.parent.mkdir(parents=True)
    record.write_text(
        json.dumps(
            {
                "approved": True,
                "policy_version": "adaptive-headroom-v1",
                "selected": {
                    "context_slices": 7,
                    "input_channels": "single",
                    "patch": [128, 128, 32],
                },
            }
        )
    )
    launcher.require_training_optimization("cq500", "baseline001")


def test_runtime_dir_reads_private_env(tmp_path: Path, monkeypatch: object) -> None:
    launcher = load_launcher()
    monkeypatch.setattr(launcher, "ROOT", tmp_path)
    monkeypatch.delenv("MIAgent_RUNTIME_DIR", raising=False)
    expected = tmp_path / "external-runtime"
    (tmp_path / ".env").write_text(f"MIAgent_RUNTIME_DIR={expected}\n")

    assert launcher.runtime_dir() == expected.resolve()


def test_gpu_memory_query_uses_training_service_without_local_smi(monkeypatch: object) -> None:
    launcher = load_launcher()
    observed: dict[str, object] = {}
    monkeypatch.setattr(launcher.shutil, "which", lambda _: None)
    monkeypatch.setattr(
        launcher,
        "compose_args",
        lambda arguments: ["docker", "compose", *arguments],
    )

    def fake_run(command: list[str], **kwargs: object) -> object:
        observed["command"] = command
        observed["env"] = kwargs.get("env")
        return SimpleNamespace(returncode=0, stdout="46385\n")

    monkeypatch.setattr(launcher.subprocess, "run", fake_run)

    assert launcher.gpu_free_memory_mb() == 46385
    assert observed["command"] == [
        "docker",
        "compose",
        "exec",
        "-T",
        "training",
        "nvidia-smi",
        "--id=0",
        "--query-gpu=memory.free",
        "--format=csv,noheader,nounits",
    ]


def test_exclusive_gpu_gate_rejects_running_llm(tmp_path: Path, monkeypatch: object) -> None:
    launcher = load_launcher()
    monkeypatch.setattr(launcher, "ROOT", tmp_path)
    monkeypatch.setattr(launcher, "llm_service_running", lambda: True)

    with pytest.raises(RuntimeError, match="docker compose stop llm"):
        launcher.acquire_gpu_lock()
