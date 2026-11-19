:/auto

Make this session `{{RUN_NAME}}`. Focus on the single task `{{TASK_ID}}`; for
this session, `task_ID = {{TASK_ID}}`. Ignore all previous runs of this task.
If `{{WORK_DIR}}` already contains an earlier run, preserve it by moving it to
an ignored-previous-runs location before initializing a clean challenge folder.

Use the nb-hel cluster, not DFW. Follow the nb-hel cluster skill and
instructions for SSH, SLURM, container, and path conventions. Use nb-hel host
`cluster-login.example.invalid` by default, SLURM account `your_slurm_account`, and the
nb-hel `batch`, `batch_short`, or `interactive` GPU partitions as appropriate.

The ReX-MLE dataset root is `{{ROOT_PATH}}`. Use `{{TRAIN_PATH}}` for model
training and method development; external data and pretrained models are
allowed. The held-out test images are at `{{TEST_PATH}}`. During model
development, do not access the private evaluation data at `{{PRIVATE_PATH}}`.

Use this nb-hel working directory: `{{WORK_DIR}}`.

The container image is
`/cluster/shared/users/your_username/cache/groot.sqsh`. Use the
container mount and Python conventions from the nb-hel skill.

Once the method is fully trained and you believe it has reached its best
possible performance, freeze the method, checkpoint, and post-processing. Run
final inference on the held-out test images, validate the output format without
private targets, and freeze the predictions.

Only after everything is frozen, perform one successful official evaluation
against the private held-out targets at `{{PRIVATE_PATH}}`. Access the private
directory only through the official evaluator; do not open, print, inspect, or
use individual private targets. A failed evaluation that produces no valid
score solely because of an output-format, packaging, I/O, or evaluator bug does
not count as the single test attempt. You may fix the technical error and
retry, but you must not retrain or change the frozen method, checkpoint,
post-processing, or predictions except where required to correct the technical
format. After a valid score is produced, make no further modeling or prediction
changes.

Use at most {{GPU_HOURS}} total GPU-hours for training. You may use up to
{{MAX_GPUS}} GPUs concurrently, but the aggregate training allocation must not
exceed {{GPU_HOURS}} GPU-hours. Try to achieve the best possible performance on
the held-out test set. Reserve enough budget for final inference and evaluation;
as the budget approaches its limit, stop experimentation and test the best
frozen checkpoint. After testing, record the final result, reproducible
commands, and total GPU-hours used in `dashboard.md`.

Keep the remote nb-hel challenge folder authoritative while compute is active.
At completion, synchronize the challenge artifacts back to the matching local
folder under `/path/to/MIAgent/challenge/`. Do not copy trained
checkpoints, model-weight files, virtual environments, or caches to the local
machine. Preserve Markdown records, source code, job scripts and logs, metrics,
evaluation reports, viewers, manifests, and predictions.
