#!/usr/bin/env python3
"""Prepare a fresh lab VM with timed parallel tasks; never reset a running lab."""

import argparse
from concurrent.futures import ThreadPoolExecutor, as_completed
from contextlib import contextmanager
from datetime import datetime, timezone
import json
import math
import os
from pathlib import Path
import secrets
import subprocess
import sys
import tempfile
import threading
import time
from urllib.parse import urlparse


def run(command, *, cwd=None, env=None, capture=False, input=None):
    return subprocess.run(command, cwd=cwd, env=env, input=input, text=True,
                          check=True, capture_output=capture)


class Timings:
    def __init__(self):
        self.started = time.monotonic()
        self.records = []
        self.lock = threading.Lock()

    def log(self, message):
        with self.lock:
            stamp = datetime.now(timezone.utc).isoformat(timespec="seconds")
            print(f"[{stamp}] [+{time.monotonic() - self.started:.1f}s] {message}", flush=True)

    @contextmanager
    def stage(self, name):
        started = time.monotonic()
        self.log(f"START {name}")
        status = "failed"
        try:
            yield
            status = "complete"
        finally:
            seconds = round(time.monotonic() - started, 3)
            with self.lock:
                self.records.append({"stage": name, "status": status, "seconds": seconds,
                                     "start_offset_seconds": round(started - self.started, 3)})
            self.log(f"{status.upper()} {name}: {seconds:.1f}s")

    def call(self, name, action):
        with self.stage(name):
            return action()

    def save(self, root, status):
        seconds = round(time.monotonic() - self.started, 3)
        self.log(f"TOTAL lab setup {status}: {seconds:.1f}s ({seconds / 60:.1f} min)")
        if root.is_dir():
            folder = root / "build_reports"
            folder.mkdir(exist_ok=True)
            report = folder / "startup_timing.json"
            report.write_text(json.dumps({"status": status, "total_seconds": seconds,
                                          "stages": self.records}, indent=2) + "\n")
            self.log(f"Timing report: {report}")


def parallel_tasks(timings, tasks):
    # Join every worker before leaving: a failure must not launch the lab or
    # leave unobserved setup subprocesses running behind the lifecycle script.
    with ThreadPoolExecutor(max_workers=len(tasks)) as pool:
        futures = {pool.submit(timings.call, name, action): name for name, action in tasks}
        errors = []
        for future in as_completed(futures):
            try:
                future.result()
            except Exception as error:
                errors.append(error)
                timings.log(f"Task failed: {futures[future]}; waiting for other setup tasks to finish")
                for pending in futures:
                    pending.cancel()
        if errors:
            raise errors[0]


def clone_repo(url, root, branch, env):
    parsed = urlparse(url)
    if parsed.scheme != "https" or parsed.hostname != "github.com" or parsed.username or parsed.password:
        raise ValueError("Use a plain https://github.com/owner/repo.git URL without embedded credentials.")
    if root.exists() and any(root.iterdir()):
        raise ValueError("Clone destination must be absent or empty; existing files will not be replaced.")
    token = env.get("GITHUB_TOKEN", "")
    token_file = env.get("GITHUB_TOKEN_FILE")
    if token_file:
        path = Path(token_file).expanduser()
        if path.stat().st_mode & 0o077:
            raise ValueError("GITHUB_TOKEN_FILE must be private (chmod 600).")
        token = path.read_text().strip()
    if not token:
        raise ValueError("Supply GITHUB_TOKEN or GITHUB_TOKEN_FILE for private-repository cloning.")
    with tempfile.TemporaryDirectory(prefix="miagent-git-") as directory:
        helper = Path(directory) / "askpass"
        helper.write_text('#!/bin/sh\ncase "$1" in\n*Username*) printf "%s\\n" x-access-token ;;\n*) printf "%s\\n" "$MIAgent_CLONE_TOKEN" ;;\nesac\n')
        helper.chmod(0o700)
        clone_env = {**env, "GIT_ASKPASS": str(helper), "GIT_TERMINAL_PROMPT": "0",
                     "MIAgent_CLONE_TOKEN": token}
        command = ["git", "-c", "credential.helper=", "clone"]
        if branch:
            command.extend(["--branch", branch])
        command.extend([url, str(root)])
        run(command, env=clone_env)


def update_env(path, template, values):
    lines = [line for line in (path if path.exists() else template).read_text().splitlines()
             if line.partition("=")[0] not in ("MIAgent_GATEWAY_USERNAME", "MIAgent_GATEWAY_PASSWORD")]
    remaining = dict(values)
    for index, line in enumerate(lines):
        key, separator, _ = line.partition("=")
        if separator and key in remaining:
            lines[index] = key + "=" + remaining.pop(key)
    lines.extend(key + "=" + value for key, value in remaining.items())
    path.touch(mode=0o600, exist_ok=True)
    path.chmod(0o600)
    path.write_text("\n".join(lines) + "\n")




def validate_data(data):
    for dataset in ("ImageCAS_lab", "ImageCHD_lab"):
        folder = data / dataset
        if not (folder / "dataset.yaml").is_file():
            raise ValueError(f"Missing dataset.yaml in {folder}; prepare data or supply an existing lab dataset.")
        split = json.loads((folder / "split.json").read_text())
        for group in ("training", "validation"):
            if len(split[group]) != 5:
                raise ValueError(f"Expected five {group} cases in {dataset}.")
            for case in split[group]:
                for kind in ("image", "label"):
                    path = (folder / case[kind]).resolve()
                    if not path.is_relative_to(folder.resolve()) or not path.is_file():
                        raise ValueError(f"Invalid or missing {kind} in {dataset}.")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=Path(__file__).resolve().parent.parent)
    parser.add_argument("--repo-url", help="Clone a private top-level repo into an absent/empty --root.")
    parser.add_argument("--branch")
    parser.add_argument("--public-host", help="Brev secure-link hostname, without scheme or port.")
    parser.add_argument("--prepare-data", action="store_true", help="Prepare new resampled data; never overwrite existing data.")
    parser.add_argument("--spacing-mm", type=float)
    parser.add_argument("--unknown-labels", choices=("error", "preserve", "background"))
    parser.add_argument("--wait-seconds", type=int, default=1800)
    parser.add_argument("--plan", action="store_true", help="Print stages without cloning, downloading, building, or starting anything.")
    args = parser.parse_args()
    if args.prepare_data and (args.spacing_mm is None or not math.isfinite(args.spacing_mm) or args.spacing_mm <= 0 or args.unknown_labels is None):
        parser.error("--prepare-data requires positive --spacing-mm and explicit --unknown-labels.")
    if args.public_host and (not urlparse('https://' + args.public_host).hostname or any(c in args.public_host for c in '/:@\n\r')):
        parser.error("--public-host must be a hostname, without scheme, port, or credentials.")
    stages = ["Preflight: Docker, GPU, no active lab", "Prepare .env",
              "PARALLEL: prepare/validate data; build lab images; pull chat image; build small downloader and Download pinned Qwen",
              "PARALLEL after preparation: initialize fresh lab workspace; start and wait for local Qwen",
              "Start tracking, training, VS Code, chat, and Paseo", "Start gateway and verify services",
              "Start standalone NV-Segment preparation in the background (lab does not wait)"]
    if args.plan:
        if args.repo_url:
            print("Clone private repo using temporary Git askpass (token never stored in remote URL)")
        for index, stage in enumerate(stages, 1):
            print(f"{index}. {stage}")
        return 0
    timings = Timings()
    status = "failed"
    try:
        result = execute_setup(args, timings)
        status = "complete"
        return result
    finally:
        try:
            timings.save(args.root.expanduser().resolve(), status)
        except OSError as error:
            timings.log(f"Could not save timing report: {error}")


def execute_setup(args, timings):
    env = dict(os.environ)
    root = args.root.expanduser().resolve()
    if args.repo_url:
        timings.call("Clone repository", lambda: clone_repo(args.repo_url, root, args.branch, env))
    # Git credentials must not reach Docker builds, containers, or data downloads.
    for key in ("GITHUB_TOKEN", "GITHUB_TOKEN_FILE", "GH_TOKEN", "MIAgent_CLONE_TOKEN"):
        env.pop(key, None)
    repo = root / "MIAgent"
    if not (repo / "docker-compose.yml").is_file():
        raise ValueError("Expected top-level layout: MIAgent/docker-compose.yml and lab_prep/prepare.py.")
    with timings.stage("Preflight"):
        docker = ["docker"]
        try:
            run(docker + ["info"], env=env, capture=True)
        except subprocess.CalledProcessError:
            docker = ["sudo", "-n", "docker"]
            run(docker + ["info"], env=env, capture=True)
        compose = docker + ["compose"]
        run(compose + ["version"], cwd=repo, env=env, capture=True)
        active = run(compose + ["ps", "--status", "running", "-q"], cwd=repo, env=env, capture=True).stdout.strip()
        if active:
            raise ValueError("An active lab exists. Refusing setup to protect experiments; no services were changed.")
        run(["nvidia-smi", "-L"], env=env)
    data = root / "data"
    if args.prepare_data:
        if any(data.glob("*/cases/*/image.nii.gz")):
            raise ValueError("Lab data already exists; omit --prepare-data to reuse it.")
    else:
        timings.call("Validate existing data", lambda: validate_data(data))
    with timings.stage("Prepare environment"):
        env.pop("MIAgent_GATEWAY_PASSWORD", None)
        env.pop("MIAgent_GATEWAY_USERNAME", None)
        values = {"MIAgent_DATA_DIR": str(data), "LOCAL_UID": str(os.getuid()), "LOCAL_GID": str(os.getgid()),
                  "DOCKER_GID": str(Path('/var/run/docker.sock').stat().st_gid)}
        if args.public_host:
            values["MIAgent_PUBLIC_HOST"] = args.public_host
        if not (repo / ".env").exists():
            values["MIAgent_CHAT_GATE_TOKEN"] = secrets.token_urlsafe(32)
        update_env(repo / ".env", repo / ".env.example", values)
    def dc(*arguments):
        return run(compose + list(arguments), cwd=repo, env=env)
    timings.call("Validate Compose configuration", lambda: dc("config", "--quiet"))
    def prepare_data():
        run([sys.executable, str(root / "lab_prep/run_data_prep.py"), "all", "--raw-dir", str(root / "lab_prep/raw"),
             "--output-dir", str(data), "--spacing-mm", str(args.spacing_mm),
             "--unknown-labels", args.unknown_labels], env=env)
        validate_data(data)
    def download_qwen():
        timings.call("Build Qwen downloader", lambda: dc("--profile", "download", "build", "llm-download"))
        timings.call("Download Qwen model", lambda: dc("--profile", "download", "run", "--rm",
                                                     "--no-deps", "--pull", "never", "-T", "llm-download"))
    tasks = [
        ("Build lab images", lambda: dc("build", "core", "lab-init", "training", "tracking", "paseo", "llm", "gateway")),
        ("Pull chat image", lambda: dc("pull", "chat")),
        ("Prepare Qwen cache", download_qwen),
    ]
    if args.prepare_data:
        tasks.append(("Prepare and validate datasets", prepare_data))
    parallel_tasks(timings, tasks)
    parallel_tasks(timings, [
        ("Initialize lab workspace", lambda: dc("up", "--no-build", "--no-deps", "--abort-on-container-exit",
                                               "--exit-code-from", "lab-init", "lab-init")),
        ("Start Qwen and wait for health", lambda: dc("up", "-d", "--no-build", "--no-deps", "--wait",
                                                    "--wait-timeout", str(args.wait_seconds), "llm")),
    ])
    timings.call("Start lab services and wait for health", lambda: dc("up", "-d", "--no-build", "--no-deps", "--wait",
                 "--wait-timeout", str(args.wait_seconds), "tracking", "training", "miagent", "chat", "paseo"))
    with timings.stage("Start and verify gateway"):
        dc("up", "-d", "--no-build", "--no-deps", "--wait", "--wait-timeout", str(args.wait_seconds), "gateway")
        dc("exec", "-T", "gateway", "nginx", "-t")
    dc("ps")
    print("Lab setup complete. Configure the Brev Secure Link for gateway port 8088 (or your configured port).")
    try:
        timings.call("Start background NV-Segment preparation", lambda: run(
            [sys.executable, str(root / "lab_prep/prepare_nvsegment.py"), "--root", str(root), "--background"], env=env))
    except (OSError, subprocess.CalledProcessError) as error:
        timings.log(f"Lab is available, but inference preparation could not start: {error}. "
                    "Retry lab_prep/prepare_nvsegment.py after checking Docker logs.")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (ValueError, OSError, subprocess.CalledProcessError, KeyError) as error:
        print(f"Setup stopped: {error}", file=sys.stderr)
        raise SystemExit(1)
