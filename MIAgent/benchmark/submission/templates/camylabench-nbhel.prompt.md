:/auto

Make this session `{{RUN_NAME}}`. Focus on the single task `{{TASK_ID}}`; for
this session, `task_ID = {{TASK_ID}}`. Ignore all previous MIAgent task runs.
If `{{WORK_DIR}}` already contains an earlier run, preserve it by moving it to
an ignored-previous-runs location before initializing a clean challenge folder.
Do not use solutions from the Camyla paper.

Use the nb-hel cluster, not DFW. Follow the nb-hel cluster skill/instructions
for SSH, SLURM, container, and path conventions. Use nb-hel host
`cluster-login.example.invalid` by default, SLURM account `your_slurm_account`, and the
nb-hel `batch`, `batch_short`, or `interactive` GPU partitions as appropriate.

Use this nb-hel working directory: `{{WORK_DIR}}`.

The CamylaBench dataset is located on nb-hel at `{{DATASET_ROOT}}`.
The ReX-MLE dataset is available on nb-hel at
`/cluster/shared/projects/your_slurm_account/datasets/ReX-MLE`.
The container image is
`/cluster/shared/users/your_username/cache/groot.sqsh`.
Use the container mount and Python conventions from the nb-hel skill.

Use the existing split JSON file in the task's CamylaBench dataset directory.
Use only the `train` split for development and model training. External data
and pretraining are allowed. You may create your own internal training and
validation splits within `train`. Do not access, inspect, tune on, or evaluate
against the provided `val` split during development.

Once the method is fully trained and you believe it has reached its best
possible performance, freeze the method, checkpoint, postprocessing, and
predictions. Then evaluate on the provided `val` split once and report it as
the final held-out test score. Do not make modeling changes after seeing this
score. A failed evaluation that produces no valid score because of an
output-format, packaging, I/O, or evaluator bug does not count as the single
test attempt. You may fix the technical error and retry, but you must not
change the frozen model, checkpoint, postprocessing, or predictions except
where required to correct the technical format.

Use up to {{MAX_GPUS}} GPUs concurrently for up to {{WALL_HOURS}} hours of
wall-clock time. Implementation and inference do not count as GPU cost. Try to
achieve the best possible performance on the held-out test set. Reserve enough
time for final inference and evaluation; as the deadline approaches, stop
experimentation and test the best frozen checkpoint. After testing, record the
final result, reproducible commands, and total GPU-hours used in `dashboard.md`.

Keep the remote nb-hel challenge folder authoritative while compute is active.
At completion, synchronize the challenge artifacts back to the matching local
folder under `/path/to/MIAgent/challenge/`. Copy Markdown files
only. Do not copy checkpoints, model weights, environments, caches, source-code
artifacts, logs, metrics files, viewers, manifests, predictions, or generated
images to the local machine; keep all non-Markdown artifacts on nb-hel.
