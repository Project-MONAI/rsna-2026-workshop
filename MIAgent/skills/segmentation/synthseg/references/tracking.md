# Tracking and evidence contract

Use `tools/experiment_tracking.py` inside MIAgent workload containers. The
launcher owns the MLflow run and imports the durable tracking files after the
container exits.

## Description and tags

Write a concise Markdown description stating:

- scientific question and why the run exists;
- controlled difference from its comparator;
- train/validation split and explicit test-access status;
- input modality, label semantics, model, and phase;
- checkpoint-selection and continuation rule.

Tags must identify challenge, baseline, experiment, run kind, modality/task,
model family, phase, synthesis mode, and upstream commit.

## Parameters

At minimum log:

- upstream URL/commit, Cornucopia commit, extension image tag/digest, dependency
  artifact, code hash, config hash, manifest hash, and seed;
- label-map version/definitions and train-only source-case count;
- synthesis parameter ranges, synthetic updates/samples, and real/synthetic
  sampling proportions;
- preprocessing, orientation, spacing, intensity/window assumptions, crop/ROI,
  batch size, patches per image, effective patches, and cache rate;
- architecture, initialization checkpoint/hash, optimizer, learning rate,
  schedule, precision, loss, epoch/update budget, validation epochs/cadence,
  early stopping, and selection rule;
- explicit `held_out_test_accessed=false` until policy permits otherwise.

Use `record_parameter_descriptions(...)` for scientific parameters whose names
do not explain their meaning.

## Metrics and timing

TensorBoard and MLflow must receive the same main curves, using the repository's
canonical names:

- `training.loss`
- `training.dice`
- `validation.loss`
- `validation.dice`

Also preserve per-class and per-case validation metrics as durable artifacts.
Record synthesis, pretraining, fine-tuning, validation, inference, evaluation,
and end-to-end wall time separately. Send GPU utilization/memory and host
RAM/swap through `record_telemetry(...)`, not TensorBoard scalar charts.

## Images and viewer

Only log review images during validation. Use at most two fixed validation
patients per validation pass, and begin only when imagery is diagnostically
useful. Include source image, target, prediction, and a labeled TP/FP/FN overlay.
Throttle image logging if it materially increases wall time.

Every prediction-producing experiment must use the challenge's shared viewer.
Inspect synchronized axial/coronal/sagittal views and per-case metrics before
accepting the result. The held-out test viewer is produced only after test
access is authorized.

## Durable run summary

The experiment `summary.md` states the hypothesis, controlled change, execution
status, selected checkpoint, best/final metrics, wall times, per-case behavior,
visual diagnosis, conclusion, and next decision. Link raw logs, resolved config,
prepared manifest, dependencies, telemetry, metrics, checkpoints, and viewer.

Run the helper's `validate-evidence` command before declaring a phase complete.
It is a structural check, not a metric-quality verdict.
