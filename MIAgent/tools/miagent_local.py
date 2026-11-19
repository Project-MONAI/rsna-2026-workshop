#!/usr/bin/env python3
"""Container-only local GPU control plane for MIAgent.

Examples:
  python3 tools/miagent_local.py init
  python3 tools/miagent_local.py build
  python3 tools/miagent_local.py up
  python3 tools/miagent_local.py preflight
  python3 tools/miagent_local.py smoke
  python3 tools/miagent_local.py run --challenge imagechd --baseline baseline001 --experiment exp001 -- python script.py
"""

from __future__ import annotations

import argparse
import fcntl
import getpass
import json
import os
import secrets
import shutil
import subprocess
import sys
import time
from pathlib import Path
from typing import Any, Sequence


ROOT = Path(__file__).resolve().parent.parent
COMPOSE_FILE = ROOT / "docker-compose.yml"


def env_file_value(name: str) -> str | None:
    """Read one non-exported setting from the repository's private .env."""
    try:
        lines = (ROOT / ".env").read_text().splitlines()
    except OSError:
        return None
    for raw_line in lines:
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        if key.strip() == name:
            return value.strip().strip('"').strip("'")
    return None


def runtime_dir() -> Path:
    value = os.environ.get("MIAgent_RUNTIME_DIR") or env_file_value("MIAgent_RUNTIME_DIR")
    return Path(value).expanduser().resolve() if value else ROOT.parent / "MIAgent_runtime_v35"


def paths() -> dict[str, Path]:
    runtime = runtime_dir()
    return {
        "runtime": runtime,
        "env": ROOT / ".env",
        "lock": runtime / "locks" / "gpu0.lock",
        "registry_lock": runtime / "locks" / "gpu0.registry.lock",
        "state": runtime / "locks" / "gpu0.state.json",
        "shared_states": runtime / "locks" / "gpu0.shared",
    }


def prepare_runtime() -> None:
    runtime = paths()["runtime"]
    for relative in (
        "locks",
        "locks/gpu0.shared",
        "logs",
        "caches/huggingface",
        "caches/torch",
        "caches/matplotlib",
        "caches/xdg",
        "mlflow/artifacts",
        "miagent-home",
        "tracking-home",
        "proxy",
        "proxy-config",
        "paseo-home",
    ):
        (runtime / relative).mkdir(parents=True, exist_ok=True)


def ensure_env(*, show_summary: bool = False, reset_env: bool = False) -> None:
    env_path = paths()["env"]
    if env_path.exists() and not reset_env:
        return
    prepare_runtime()
    docker_gid = Path("/var/run/docker.sock").stat().st_gid if Path("/var/run/docker.sock").exists() else 983
    env_path.write_text(
        "\n".join(
            (
                f"MIAgent_RUNTIME_DIR={paths()['runtime']}",
                f"MIAgent_DATA_DIR={os.environ.get('MIAgent_DATA_DIR', str(ROOT.parent / 'data'))}",
                f"MIAgent_HOST_ROOT={ROOT}",
                f"MIAgent_DOMAIN={os.environ.get('MIAgent_DOMAIN', 'miagent.local')}",
                f"MIAgent_HTTP_PORT={os.environ.get('MIAgent_HTTP_PORT', '80')}",
                f"MIAgent_CHAT_GATE_TOKEN={secrets.token_hex(32)}",
                f"LOCAL_UID={os.getuid()}",
                f"LOCAL_GID={os.getgid()}",
                f"DOCKER_GID={docker_gid}",
                "",
            )
        )
    )
    os.chmod(env_path, 0o600)
    print(f"Created {env_path} with mode 0600.")
    if show_summary:
        print("Browser services use the gateway without authentication on this teaching host.")


def compose_args(arguments: Sequence[str]) -> list[str]:
    env_path = paths()["env"]
    if not env_path.exists():
        raise RuntimeError("runtime is not initialized; run `python3 tools/miagent_local.py init` first")
    return [
        "docker",
        "compose",
        "--project-directory",
        str(ROOT),
        "--env-file",
        str(env_path),
        "-f",
        str(COMPOSE_FILE),
        *arguments,
    ]


def compose(arguments: Sequence[str], *, check: bool = True) -> subprocess.CompletedProcess[str]:
    env = os.environ.copy()
    # Inside the control container this variable is `/runtime`, but Compose
    # bind sources must remain host paths from the repository `.env`.
    env.pop("MIAgent_RUNTIME_DIR", None)
    env["LOCAL_UID"] = str(os.getuid())
    env["LOCAL_GID"] = str(os.getgid())
    env["MIAgent_RUN_USER"] = getpass.getuser()
    return subprocess.run(compose_args(arguments), check=check, text=True, env=env)


def read_json(path: Path) -> dict[str, Any] | None:
    try:
        value = json.loads(path.read_text())
    except (OSError, json.JSONDecodeError):
        return None
    return value if isinstance(value, dict) else None


def read_state() -> dict[str, Any] | None:
    return read_json(paths()["state"])


def active_state() -> dict[str, Any] | None:
    state = read_state()
    if state and process_alive(state.get("host_pid")):
        return state
    return None


def acquire_registry_lock() -> Any:
    """Serialize short state-registry updates without serializing workloads."""
    lock_path = paths()["registry_lock"]
    lock_path.parent.mkdir(parents=True, exist_ok=True)
    handle = lock_path.open("a+")
    fcntl.flock(handle.fileno(), fcntl.LOCK_EX)
    return handle


def release_lock(handle: Any) -> None:
    fcntl.flock(handle.fileno(), fcntl.LOCK_UN)
    handle.close()


def shared_state_path(container: str) -> Path:
    return paths()["shared_states"] / f"{container}.json"


def active_shared_states(*, clear_stale: bool = True) -> list[dict[str, Any]]:
    directory = paths()["shared_states"]
    directory.mkdir(parents=True, exist_ok=True)
    active: list[dict[str, Any]] = []
    for path in directory.glob("*.json"):
        value = read_json(path)
        # Registration is written before Docker finishes creating the
        # container. Keep that startup reservation while the owning launcher
        # is alive so a concurrent admission cannot erase its budget.
        if value and (
            process_alive(value.get("host_pid"))
        ):
            active.append(value)
        elif clear_stale:
            try:
                path.unlink()
            except FileNotFoundError:
                pass
    return sorted(active, key=lambda value: float(value.get("started_at") or 0))


def process_alive(pid: object) -> bool:
    try:
        value = int(pid)
    except (TypeError, ValueError):
        return False
    if value <= 0:
        return False
    try:
        os.kill(value, 0)
    except OSError:
        return False
    return True


def write_state(state: dict[str, Any]) -> None:
    path = paths()["state"]
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(state, indent=2, sort_keys=True) + "\n")


def write_live_dashboard(run_dir: Path, state: dict[str, Any]) -> None:
    """Expose an active job immediately; the container replaces this on exit."""
    tracking = run_dir / "tracking"
    tracking.mkdir(parents=True, exist_ok=True)
    payload = {
        "challenge": state["challenge"],
        "baseline": state["baseline"],
        "experiment": state["experiment"],
        "stage": state["stage"],
        "status": "running",
        "started_at": state["started_at"],
        "wall_time": "in progress",
        "parameter_summary": "workload starting; detailed parameters will appear after initialization",
    }
    (tracking / "dashboard.json").write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n")
    (tracking / "dashboard.md").write_text(
        "# Local Run Dashboard\n\n"
        "| Field | Value |\n|---|---|\n"
        "| Status | running |\n"
        f"| Stage | `{state['stage']}` |\n"
        f"| Started | {time.strftime('%Y-%m-%d %H:%M:%S UTC', time.gmtime(float(state['started_at'])))} |\n"
        "| Wall time | in progress |\n"
    )
    tools_dir = ROOT / "tools"
    if str(tools_dir) not in sys.path:
        sys.path.insert(0, str(tools_dir))
    from container_entrypoint import update_challenge_dashboard

    update_challenge_dashboard(run_dir)


def clear_stale_state() -> None:
    state_path = paths()["state"]
    if state_path.exists() and active_state() is None:
        try:
            state_path.unlink()
        except FileNotFoundError:
            # The runner may remove its state between the existence check and
            # a concurrent stop/status command.
            pass


def safe_component(value: str, field: str) -> str:
    normalized = "".join(char if char.isalnum() or char in "-_" else "-" for char in value.lower()).strip("-")
    if not normalized:
        raise ValueError(f"{field} must include at least one letter or digit")
    return normalized


def llm_service_running() -> bool:
    """Return whether the Compose-managed local inference service is running."""
    inspected = subprocess.run(
        compose_args(["ps", "--status", "running", "-q", "llm"]),
        capture_output=True,
        text=True,
    )
    if inspected.returncode != 0:
        raise RuntimeError("could not determine whether the local LLM service is running")
    return bool(inspected.stdout.strip())


def gpu_free_memory_mb() -> int:
    """Return free GPU-0 memory, querying the GPU-owning service when needed."""
    query = [
        "nvidia-smi",
        "--id=0",
        "--query-gpu=memory.free",
        "--format=csv,noheader,nounits",
    ]
    command = query
    env = None
    if shutil.which("nvidia-smi") is None:
        command = compose_args(["exec", "-T", "training", *query])
        env = os.environ.copy()
        env.pop("MIAgent_RUNTIME_DIR", None)
        env["LOCAL_UID"] = str(os.getuid())
        env["LOCAL_GID"] = str(os.getgid())
        env["MIAgent_RUN_USER"] = getpass.getuser()
    inspected = subprocess.run(
        command,
        capture_output=True,
        text=True,
        env=env,
    )
    try:
        value = int(inspected.stdout.strip().splitlines()[0])
    except (IndexError, ValueError) as exc:
        raise RuntimeError("could not determine free memory on GPU 0") from exc
    if inspected.returncode != 0 or value <= 0:
        raise RuntimeError("could not determine free memory on GPU 0")
    return value


def acquire_gpu_lock() -> Any:
    if llm_service_running():
        raise RuntimeError(
            "GPU 0 is shared with the local LLM; stop it with `docker compose stop llm` "
            "before starting an exclusive workload, or declare a bounded `--shared-gpu` run"
        )
    lock_path = paths()["lock"]
    lock_path.parent.mkdir(parents=True, exist_ok=True)
    handle = lock_path.open("a+")
    try:
        fcntl.flock(handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
    except BlockingIOError as exc:
        handle.close()
        raise RuntimeError("GPU 0 is already reserved by another miagent-local process") from exc
    registry = acquire_registry_lock()
    try:
        active = active_state()
        shared = active_shared_states()
        if active:
            raise RuntimeError(f"GPU 0 is already used by container {active['container']} (run `status` or `stop`)")
        if shared:
            names = ", ".join(str(value["container"]) for value in shared)
            raise RuntimeError(f"GPU 0 is shared by active containers: {names} (run `status` or `stop`)")
        clear_stale_state()
    except Exception:
        release_lock(handle)
        raise
    finally:
        release_lock(registry)
    return handle


def acquire_shared_gpu_slot(requested_budget_mb: int) -> Any:
    """Register a bounded shared workload while excluding an exclusive runner.

    The registry lock closes the race between an exclusive lock acquisition and
    a shared registration.  The shared jobs intentionally do not retain the
    exclusive GPU flock, so more than one can execute concurrently.
    """
    registry = acquire_registry_lock()
    try:
        if active_state():
            raise RuntimeError("GPU 0 is reserved by an exclusive miagent-local workload")
        exclusive_lock = paths()["lock"].open("a+")
        try:
            fcntl.flock(exclusive_lock.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError as exc:
            raise RuntimeError("GPU 0 is reserved by an exclusive miagent-local workload") from exc
        else:
            release_lock(exclusive_lock)
        clear_stale_state()
        shared = active_shared_states()
        committed = sum(int(value.get("gpu_budget_mb") or 0) for value in shared)
        currently_free = gpu_free_memory_mb()
        if committed + requested_budget_mb > currently_free:
            raise RuntimeError(
                "shared GPU admission exceeds current uncommitted memory: "
                f"{currently_free} MiB currently free, {committed} MiB already declared, "
                f"and {requested_budget_mb} MiB requested"
            )
        return registry
    except Exception:
        release_lock(registry)
        raise


def approved_optimization_record(challenge: str, baseline: str, architecture: str = "unet", context_slices: int = 7, init_filters: int = 16, input_channels: str = "single", patch_size: str = "128,128,32") -> Path:
    suffix = "" if architecture == "unet" else f"_{architecture}"
    if context_slices != 7:
        suffix += f"_ctx{context_slices}"
    if architecture in {"3d_segresnet", "3d_unet"} and init_filters != 16:
        suffix += f"_f{init_filters}"
    if input_channels != "single":
        suffix += f"_{input_channels}"
    if patch_size != "128,128,32":
        suffix += f"_p{patch_size.replace(',', 'x')}"
    filename = "approved.json" if not suffix else f"approved{suffix}.json"
    return ROOT / "challenge" / challenge / "baselines" / baseline / "gpu_optimization" / filename


def require_training_optimization(challenge: str, baseline: str, architecture: str = "unet", context_slices: int = 7, init_filters: int = 16, input_channels: str = "single", patch_size: str = "128,128,32") -> None:
    """Ensure a declared training run has durable, successful GPU evidence."""
    record = approved_optimization_record(challenge, baseline, architecture, context_slices, init_filters, input_channels, patch_size)
    try:
        value = json.loads(record.read_text())
    except (OSError, json.JSONDecodeError) as exc:
        raise RuntimeError(
            "training requires a completed GPU optimization record; run "
            "`miagent_local.py optimize-gpu` first"
        ) from exc
    if not isinstance(value, dict) or value.get("approved") is not True:
        raise RuntimeError(f"GPU optimization record is not approved: {record}")
    if value.get("policy_version") != "adaptive-headroom-v1":
        raise RuntimeError(
            "GPU optimization record uses an obsolete fixed ladder; rerun the "
            "adaptive headroom optimizer before training"
        )
    selected = value.get("selected")
    if architecture != "unet" and (not isinstance(selected, dict) or selected.get("architecture") != architecture):
        raise RuntimeError(f"GPU optimization record is not bound to requested architecture {architecture}: {record}")
    if not isinstance(selected, dict) or int(selected.get("context_slices", 7)) != context_slices:
        raise RuntimeError(f"GPU optimization record is not bound to requested context {context_slices}: {record}")
    if architecture in {"3d_segresnet", "3d_unet"} and int(selected.get("init_filters", 16)) != init_filters:
        raise RuntimeError(f"GPU optimization record is not bound to requested init_filters {init_filters}: {record}")
    if str(selected.get("input_channels", "single")) != input_channels:
        raise RuntimeError(f"GPU optimization record is not bound to requested input_channels {input_channels}: {record}")
    try:
        approved_patch = [int(value) for value in selected.get("patch", [])]
        requested_patch = [int(value) for value in patch_size.split(",")]
    except (TypeError, ValueError) as exc:
        raise RuntimeError(f"invalid patch geometry in GPU optimization record: {record}") from exc
    if len(requested_patch) != 3 or any(value < 16 for value in requested_patch):
        raise RuntimeError("CQ500_PATCH_SIZE must be three integers, each at least 16")
    if approved_patch != requested_patch:
        raise RuntimeError(f"GPU optimization record is not bound to requested patch {patch_size}: {record}")


def training_architecture(command: Sequence[str]) -> str:
    """Read the explicit architecture from an ``env`` workload prefix."""
    for item in command:
        if item.startswith("CQ500_ARCHITECTURE="):
            architecture = item.split("=", 1)[1].strip().lower()
            if not architecture or any(char not in "abcdefghijklmnopqrstuvwxyz0123456789_-" for char in architecture):
                raise RuntimeError("invalid CQ500_ARCHITECTURE value")
            return architecture
    return "unet"


def training_context_slices(command: Sequence[str]) -> int:
    """Read the explicit odd context depth from an ``env`` workload prefix."""
    for item in command:
        if item.startswith("CQ500_CONTEXT_SLICES="):
            try:
                context = int(item.split("=", 1)[1].strip())
            except ValueError as exc:
                raise RuntimeError("invalid CQ500_CONTEXT_SLICES value") from exc
            if context < 3 or context % 2 == 0:
                raise RuntimeError("CQ500_CONTEXT_SLICES must be an odd integer of at least 3")
            return context
    return 7


def training_init_filters(command: Sequence[str]) -> int:
    """Read an explicit 3D-model width from its trainer argument."""
    for index, item in enumerate(command):
        if item == "--init-filters" and index + 1 < len(command):
            try:
                value = int(command[index + 1])
            except ValueError as exc:
                raise RuntimeError("--init-filters must be a positive integer") from exc
            if value < 1:
                raise RuntimeError("--init-filters must be a positive integer")
            return value
    return 16


def training_input_channels(command: Sequence[str]) -> str:
    """Read the explicit CT input encoding from its trainer argument."""
    for index, item in enumerate(command):
        if item == "--input-channels" and index + 1 < len(command):
            value = command[index + 1].strip().lower()
            if value not in {"single", "windows3", "windows3_coord3", "windows3_coordz"}:
                raise RuntimeError("--input-channels must be single, windows3, windows3_coord3, or windows3_coordz")
            return value
    return "single"


def training_patch_size(command: Sequence[str]) -> str:
    """Read and validate the explicit 3D patch geometry from an env prefix."""
    for item in command:
        if item.startswith("CQ500_PATCH_SIZE="):
            value = item.split("=", 1)[1].strip()
            try:
                parsed = [int(part) for part in value.split(",")]
            except ValueError as exc:
                raise RuntimeError("CQ500_PATCH_SIZE must be three integers, each at least 16") from exc
            if len(parsed) != 3 or any(part < 16 for part in parsed):
                raise RuntimeError("CQ500_PATCH_SIZE must be three integers, each at least 16")
            return ",".join(map(str, parsed))
    return "128,128,32"


def launch_run(args: argparse.Namespace, command: list[str], *, stage: str = "other") -> int:
    challenge = safe_component(args.challenge, "challenge")
    baseline = safe_component(args.baseline, "baseline")
    experiment = safe_component(args.experiment, "experiment")
    campaign = safe_component(getattr(args, "campaign", "") or "", "campaign") if getattr(args, "campaign", "") else ""
    skip_optimization = bool(getattr(args, "skip_gpu_optimization", False))
    shared_gpu = bool(getattr(args, "shared_gpu", False))
    gpu_budget_mb = int(getattr(args, "gpu_budget_mb", 0) or 0)
    runner_service = str(getattr(args, "runner_service", "training") or "training")
    if runner_service not in {"training", "runner", "synthseg-runner", "nnunet-runner"}:
        raise RuntimeError("runner service must be training")
    # Old command lines remain accepted, but all scientific dependencies now
    # live in the one persistent training service.
    runner_service = "training"
    if shared_gpu and gpu_budget_mb <= 0:
        raise RuntimeError("shared GPU runs require a positive --gpu-budget-mb")
    if stage == "training" and not skip_optimization:
        require_training_optimization(challenge, baseline, training_architecture(command), training_context_slices(command), training_init_filters(command), training_input_channels(command), training_patch_size(command))
    run_dir = ROOT / "challenge" / challenge / "baselines" / baseline / "runs" / experiment
    run_dir.mkdir(parents=True, exist_ok=True)
    workload = f"miagent-{challenge}-{baseline}-{experiment}"[:62]
    workload_pid_file = f"/runtime/locks/{workload}.pid"
    lock = acquire_shared_gpu_slot(gpu_budget_mb) if shared_gpu else acquire_gpu_lock()
    # Archive the prior stage only after admission succeeds and before the live
    # dashboard replaces its completed tracking record.
    from container_entrypoint import archive_prior_execution
    archive_prior_execution(run_dir)
    state = {
        "challenge": challenge,
        "baseline": baseline,
        "experiment": experiment,
        "container": "miagent-training-1",
        "workload": workload,
        "workload_pid_file": workload_pid_file,
        "host_pid": os.getpid(),
        "run_dir": str(run_dir),
        "started_at": time.time(),
        "command": command,
        "stage": stage,
        "campaign": campaign,
        "gpu_optimization_bypassed": skip_optimization,
        "gpu_mode": "shared" if shared_gpu else "exclusive",
        "gpu_budget_mb": gpu_budget_mb if shared_gpu else None,
        "runner_service": runner_service,
    }
    if shared_gpu:
        shared_state_path(workload).write_text(json.dumps(state, indent=2, sort_keys=True) + "\n")
        # The registry lock only protects admission/state mutation. Retaining
        # it for the workload lifetime would serialize every shared job.
        release_lock(lock)
        lock = None
    else:
        write_state(state)
    write_live_dashboard(run_dir, state)
    try:
        # Never start, stop, restart, or recreate training here. An operator
        # owns its lifecycle; MIAgent only executes an admitted job in it.
        inspected = subprocess.run(compose_args(["ps", "--status", "running", "-q", "training"]), capture_output=True, text=True)
        if inspected.returncode != 0 or not inspected.stdout.strip():
            raise RuntimeError("training is not running; an operator must start it with `docker compose up -d training`")
        container_run_dir = "/workspace/" + str(run_dir.relative_to(ROOT))
        completed = compose(
            [
                "exec",
                "-T",
                "-e",
                f"MIAgent_RUN_DIR={container_run_dir}",
                "-e",
                f"MIAgent_CHALLENGE={challenge}",
                "-e",
                f"MIAgent_BASELINE={baseline}",
                "-e",
                f"MIAgent_EXPERIMENT={experiment}",
                "-e",
                f"MIAgent_STAGE={stage}",
                "-e",
                f"MIAgent_CAMPAIGN={campaign}",
                "-e",
                f"MIAgent_GPU_OPTIMIZATION_BYPASS={'true' if skip_optimization else 'false'}",
                "-e",
                f"MIAgent_GPU_MODE={'shared' if shared_gpu else 'exclusive'}",
                "-e",
                f"MIAgent_GPU_BUDGET_MB={gpu_budget_mb}",
                "-e",
                f"MIAgent_WORKLOAD_PID_FILE={workload_pid_file}",
                "training",
                "python3",
                "/workspace/tools/container_entrypoint.py",
                "--",
                *command,
            ],
            check=False,
        )
        return completed.returncode
    finally:
        if shared_gpu:
            try:
                shared_state_path(workload).unlink()
            except FileNotFoundError:
                pass
        else:
            state_path = paths()["state"]
            if state_path.exists():
                state_path.unlink()
        if lock is not None:
            release_lock(lock)


def command_init(args: argparse.Namespace) -> int:
    ensure_env(show_summary=True, reset_env=args.reset_env)
    return 0


def command_build(_: argparse.Namespace) -> int:
    ensure_env()
    compose(["--profile", "build", "build"])
    return 0


def command_up(_: argparse.Namespace) -> int:
    ensure_env()
    compose(["up", "-d", "tracking", "miagent", "llm", "chat", "paseo", "gateway"])
    print("MIAgent browser services, Paseo agents, and local Qwen chat are available through the gateway. Training lifecycle remains operator-owned.")
    return 0


def command_down(_: argparse.Namespace) -> int:
    ensure_env()
    active = [value for value in [active_state(), *active_shared_states()] if value]
    if active:
        names = ", ".join(str(value["container"]) for value in active)
        raise RuntimeError(f"refusing to stop dashboards while GPU job(s) {names} are active; run `stop` first")
    compose(["stop", "gateway", "paseo", "chat", "llm", "archive-tracking", "archive-viewer", "miagent", "tracking"])
    return 0


def command_preflight(_: argparse.Namespace) -> int:
    ensure_env()
    result = compose(["exec", "-T", "training", "python3", "/workspace/tools/local_preflight.py"], check=False)
    return result.returncode


def command_smoke(_: argparse.Namespace) -> int:
    return launch_run(
        argparse.Namespace(challenge="runtime_smoke", baseline="baseline001_monai", experiment="exp001_gpu"),
        ["python3", "/workspace/tools/synthetic_monai_smoke.py"],
        stage="smoke",
    )


def command_run(args: argparse.Namespace) -> int:
    command = list(args.command)
    if command[:1] == ["--"]:
        command = command[1:]
    if not command:
        raise RuntimeError("run requires a workload command after --")
    return launch_run(args, command, stage=args.stage)


def command_optimize_gpu(args: argparse.Namespace) -> int:
    command = list(args.command)
    if command[:1] == ["--"]:
        command = command[1:]
    if not command:
        raise RuntimeError("optimize-gpu requires a workload command after --")
    return launch_run(args, command, stage="gpu_optimization")


def command_status(_: argparse.Namespace) -> int:
    ensure_env()
    state = active_state()
    if state:
        print(json.dumps({"gpu_state": "running", **state}, indent=2, sort_keys=True))
        return 0
    shared = active_shared_states()
    if shared:
        print(
            json.dumps(
                {
                    "gpu_state": "shared",
                    "gpu_free_memory_mb": gpu_free_memory_mb(),
                    "shared_gpu_admitted_mb": sum(int(value.get("gpu_budget_mb") or 0) for value in shared),
                    "workloads": shared,
                },
                indent=2,
                sort_keys=True,
            )
        )
        return 0
    clear_stale_state()
    print(json.dumps({"gpu_state": "idle"}, indent=2))
    return 0


def command_stop(_: argparse.Namespace) -> int:
    ensure_env()
    state = read_state()
    shared = active_shared_states()
    if not state and not shared:
        print("No recorded GPU workload is active.")
        return 0
    workloads = [value for value in [state, *shared] if value]
    for workload in workloads:
        pid_file = str(workload.get("workload_pid_file") or "")
        if not pid_file.startswith("/runtime/locks/") or not pid_file.endswith(".pid"):
            continue
        script = (
            "import os,pathlib,signal,sys; "
            "p=pathlib.Path(sys.argv[1]); "
            "pid=int(p.read_text().strip()); "
            "os.killpg(pid, signal.SIGTERM)"
        )
        compose(["exec", "-T", "training", "python3", "-c", script, pid_file], check=False)
    clear_stale_state()
    active_shared_states()
    print(f"Signalled {len(workloads)} recorded GPU workload(s); the training container was left running.")
    return 0


def parser() -> argparse.ArgumentParser:
    result = argparse.ArgumentParser(description=__doc__)
    subparsers = result.add_subparsers(dest="action", required=True)
    for name, handler in (
        ("init", command_init),
        ("build", command_build),
        ("up", command_up),
        ("down", command_down),
        ("preflight", command_preflight),
        ("smoke", command_smoke),
        ("status", command_status),
        ("stop", command_stop),
    ):
        child = subparsers.add_parser(name)
        if name == "init":
            child.add_argument("--reset-env", action="store_true", help="Regenerate the local runtime environment file.")
        child.set_defaults(handler=handler)
    run = subparsers.add_parser("run", help="Run one workload on GPU 0 (exclusive by default).")
    run.add_argument("--challenge", required=True)
    run.add_argument("--baseline", required=True)
    run.add_argument("--experiment", required=True)
    run.add_argument("--campaign", help="Place this workload in a named MLflow campaign.")
    run.add_argument(
        "--stage",
        choices=("other", "preprocess", "inference", "smoke", "training"),
        default="other",
        help="Declare training to enforce completed GPU-optimization evidence.",
    )
    run.add_argument(
        "--shared-gpu",
        action="store_true",
        help="Allow this bounded low-memory workload to share GPU 0 with other shared runs.",
    )
    run.add_argument(
        "--gpu-budget-mb",
        type=int,
        help="Per-workload admission budget for --shared-gpu; recorded in provenance.",
    )
    run.add_argument(
        "--skip-gpu-optimization",
        action="store_true",
        help="Run training without a matching optimization record; this explicit override is recorded in run provenance.",
    )
    run.add_argument(
        "--runner-service",
        choices=("training", "runner", "synthseg-runner", "nnunet-runner"),
        default="training",
        help="Compatibility option; every workload now uses the persistent training service.",
    )
    run.add_argument("command", nargs=argparse.REMAINDER)
    run.set_defaults(handler=command_run)
    optimize = subparsers.add_parser("optimize-gpu", help="Run an admitted GPU-optimization workload on GPU 0.")
    optimize.add_argument("--challenge", required=True)
    optimize.add_argument("--baseline", required=True)
    optimize.add_argument("--experiment", required=True)
    optimize.add_argument(
        "--runner-service",
        choices=("training", "runner", "synthseg-runner", "nnunet-runner"),
        default="training",
        help="Compatibility option; every workload now uses the persistent training service.",
    )
    optimize.add_argument(
        "--shared-gpu",
        action="store_true",
        help="Profile within a declared budget while the local LLM remains running.",
    )
    optimize.add_argument(
        "--gpu-budget-mb",
        type=int,
        help="Run-specific profile memory boundary for --shared-gpu.",
    )
    optimize.add_argument("command", nargs=argparse.REMAINDER)
    optimize.set_defaults(handler=command_optimize_gpu)
    return result


def main() -> int:
    args = parser().parse_args()
    try:
        return int(args.handler(args))
    except (RuntimeError, subprocess.CalledProcessError, ValueError) as exc:
        print(f"miagent-local: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
