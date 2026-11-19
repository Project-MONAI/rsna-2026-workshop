:/auto

Make this session `{{RUN_NAME}}`. Focus on the single task `{{TASK_ID}}`; for
this session, `task_ID = {{TASK_ID}}`. Ignore all previous runs of this task.
Do not read or use the Camyla paper.

The CamylaBench dataset is located at `{{DATASET_ROOT}}`. Use the existing
split JSON file in the task's CamylaBench dataset directory. Use only the
`train` split for development and model training; external data and pretraining
are allowed. You may create internal training and validation splits within
`train`. Do not access, inspect, tune on, or evaluate against the provided
`val` split during development.

Once the method is fully trained and you believe it has reached its best
possible performance, freeze the method, checkpoint, and post-processing. Run
final inference on `val`, freeze those predictions, and evaluate them once.
Report the result as the final held-out test score. Do not make modeling or
prediction changes after seeing a valid score. A failed evaluation that
produces no valid score solely because of an output-format, packaging, I/O, or
evaluator bug does not count as the single test attempt. You may fix the
technical error and retry, but you must not change the frozen method,
checkpoint, post-processing, or predictions except where required to correct
the technical format.

Use this DFW working directory: `{{WORK_DIR}}`.

Use up to {{MAX_GPUS}} GPUs concurrently for up to {{WALL_HOURS}} hours of
wall-clock time. Try to achieve the best possible performance on the held-out
test set. Reserve enough time for final inference and evaluation; as the
deadline approaches, stop experimentation and test the best frozen checkpoint.
After testing, record the final result, reproducible commands, and total
GPU-hours used in `dashboard.md`.
