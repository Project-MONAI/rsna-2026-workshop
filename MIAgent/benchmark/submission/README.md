# Benchmark submission prompts

This folder is the clean, self-contained interface for rendering and submitting
CamylaBench and ReX-MLE prompts. Edit the complete prompt files directly with
any text editor:

- `templates/camylabench.prompt.md`
- `templates/camylabench-nbhel.prompt.md`
- `templates/rex-mle.prompt.md`
- `templates/rex-mle-nbhel.prompt.md`

Do not edit shell heredocs; the submitter reads these files at runtime.

## Preview a prompt

```text
benchmark/submission/submit.sh camyla 907 --version v3.5 --dry-run
benchmark/submission/submit.sh rex-mle puma-track2-task2 --version v3.5 --dry-run
```

The rendered prompt and reproducibility metadata are saved below the hidden
`.runs/` directory. Dry runs never start Codex.

## Submit to Codex

```text
benchmark/submission/submit.sh camyla 907 --version v3.5 --submit
benchmark/submission/submit.sh rex-mle puma-track2-task2 --version v3.5 --submit
```

Submission uses Codex GPT-5.5 with `xhigh` reasoning by default. Override these
with `--model` and `--reasoning`. The submitter captures Codex's JSONL event
stream and final message alongside the exact rendered prompt and its SHA-256
hash. It refuses to overwrite a previously submitted run with the same version.

## CamylaBench on nb-hel

Preview one task or submit tasks 916 through 932 using v3.5 session and
challenge-folder names:

```text
benchmark/submission/submit_camylabench_nbhel.sh 916 --dry-run
benchmark/submission/submit_camylabench_nbhel.sh --all --submit
```

The all-task launcher runs at most four Codex processes at once. Each task uses
the nb-hel prompt and writes its captured session under
`benchmark/submission/.runs/camyla_task_v3.5_<task>_nbhel/`. On completion, its
remote challenge artifacts are synchronized into local `challenge/`, excluding
everything except Markdown records.

## ReX-MLE on nb-hel

Preview or submit one task using v3.5 for both the session name and challenge
directory:

```text
benchmark/submission/submit_rex_mle_nbhel.sh usenhance --dry-run
benchmark/submission/submit_rex_mle_nbhel.sh usenhance --submit
```

Submit every prepared task, with at most four Codex processes active at once:

```text
benchmark/submission/submit_rex_mle_nbhel.sh --all --submit
```

For a long all-task launch, keep the supervisor alive after closing the shell:

```text
nohup benchmark/submission/submit_rex_mle_nbhel.sh --all --submit \
  > benchmark/submission/rex-v3.5-nbhel.log 2>&1 &
```

Each task writes its prompt, metadata, JSONL event stream, and final response to
`benchmark/submission/.runs/rex_task_v3.5_<task>_nbhel/`. Its challenge folder is
`challenge/ReX-MLE_v3.5_<task>/`. The launcher refuses
to overwrite a submitted run; use a new `--version` to rerun one. After each
task finishes, the launcher pulls its remote challenge folder into local
`challenge/`, excluding checkpoints, model weights, environments, and caches.
It then validates semantic completion: the final response must report
`Completed`, `dashboard.md` must contain official protected-evaluation evidence,
an official evaluation result artifact must exist, and the strict consistency
checker must pass. A clean Codex process exit with a `Blocked` response is
reported as a failed task rather than a completed benchmark.

`codex exec` tasks persist in the CLI session store but are not guaranteed to
appear as task cards in the Codex desktop sidebar. For sidebar-visible runs,
create the tasks through the Codex desktop app instead of this CLI submitter.

## Choosing terminal or Codex desktop submission

Both routes use the same repository instructions, prompt, model, tools, and
cluster workflow. They are operationally comparable, but exact scores are not
guaranteed to repeat because agent decisions, training, external research, and
scheduler timing can vary.

### Terminal/headless submission

Use the terminal launcher for unattended runs. Keep it inside `tmux` so the
supervisor is not lost when a terminal or tool session closes:

```text
cd /path/to/MIAgent
tmux new -s rex-v35
benchmark/submission/submit_rex_mle_nbhel.sh --all --submit --max-parallel 4
```

Detach with `Ctrl-b d` and reconnect with:

```text
tmux attach -t rex-v35
```

`--max-parallel 4` means all requested tasks are placed in the launcher's local
queue, with four Codex processes active at a time. A later batch is not started
until every process in the current batch exits. This limit controls Codex
processes, not the per-task SLURM GPU limit.

### Sidebar-visible Codex desktop tasks

For interactive task cards, ask Codex from an existing desktop task to create
one new task per benchmark ID. A reusable request is:

```text
Create separate Codex desktop tasks for all listed ReX-MLE task IDs. Run them
in waves of four. Use the saved MIAgent project directly, not worktrees. Title
each task rex_task_v3.5_<task_ID>_nbhel, use GPT-5.5 with xhigh reasoning, and
render its prompt from benchmark/submission/templates/rex-mle-nbhel.prompt.md.
Follow AGENTS.md and the challenge workflow, use nb-hel with the stated GPU
budget, and synchronize the final challenge folder locally without checkpoints.
Do not launch a task that already has an active or completed run with the same
version. Report every created task ID.
```

Do not run the same task through both routes at once. That can race on the same
challenge folder and can violate a one-shot protected-evaluation contract.

For the two routes to remain comparable, keep the rendered prompt, repository
revision, model and reasoning effort, data permissions, compute limits,
container, cluster, clean task folder, and freeze/evaluation rules identical.

## Editable parameters

```text
--version v3.5
--cluster dfw
--max-gpus 8
--wall-hours 8
--gpu-hours 24
--model gpt-5.5
--reasoning xhigh
```

CamylaBench uses `--wall-hours`; ReX-MLE uses `--gpu-hours`. Task paths,
session names, and cluster working directories are derived from the benchmark,
versions, task ID, and selected cluster.
