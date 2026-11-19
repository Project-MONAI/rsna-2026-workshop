#!/usr/bin/env python3
"""Integration check for recreation versus restart, using isolated test volumes."""

import subprocess
import uuid


def docker(*arguments):
    subprocess.run(["docker", *arguments], check=True)


if __name__ == "__main__":
    name = "miagent-reset-check-" + uuid.uuid4().hex[:8]
    volumes = [name + "-" + part for part in ("workspace", "runtime", "cache")]
    mounts = []
    for volume, target in zip(volumes, ("/workspace", "/runtime", "/cache")):
        mounts.extend(["-v", volume + ":" + target])
    initialize = ["run", "--name", name, "--user", "root", "--entrypoint", "python3",
                  *mounts, "miagent-control:0.2.0", "/usr/local/bin/miagent-lab-init"]
    def probe(code):
        docker("run", "--rm", "--entrypoint", "python3", *mounts,
               "miagent-control:0.2.0", "-c", "from pathlib import Path; " + code)
    try:
        docker(*initialize)
        probe("assert not any((Path('/opt/miagent-seed') / p).exists() for p in ('.env', '.git', '.vscode', 'inference_tmp/qwen_request.md')); "
              "Path('/workspace/student.txt').write_text('student'); "
              "Path('/workspace/inference_tmp/output.txt').write_text('output'); "
              "Path('/runtime/logs/student.log').write_text('log'); "
              "Path('/cache/torch/model.txt').write_text('weights')")
        docker("start", "-a", name)
        probe("assert Path('/workspace/student.txt').exists(); assert Path('/runtime/logs/student.log').exists()")
        docker("rm", name)
        docker(*initialize)
        probe("assert not Path('/workspace/student.txt').exists(); "
              "assert not Path('/workspace/inference_tmp/output.txt').exists(); "
              "assert not Path('/runtime/logs/student.log').exists(); "
              "assert Path('/cache/torch/model.txt').read_text() == 'weights'; "
              "assert Path('/workspace/challenge/challenge_template').is_dir()")
        print("PASS: restart preserves work; recreation restores the seed and preserves weights.")
    finally:
        subprocess.run(["docker", "rm", "-f", name], check=False)
        for volume in volumes:
            subprocess.run(["docker", "volume", "rm", volume], check=False)
