# Local GPU Optimization Contract

Apply this contract before every declared `miagent_local.py run --stage training`
workload. It is a capacity and reliability check, not a model-selection sweep.
All model computation, telemetry collection, and cache construction run inside
an admitted workload in the persistent `training` container.

## Goal and memory boundary

Discover a throughput-efficient crop/patch, batch, and cache configuration that
is repeatably safe on the GPU that is actually visible at runtime. At the start
of every profile, record the detected GPU model, physical memory, current use,
and the applicable memory boundary in the local optimization report. Do not
hardcode a workstation model or assume the GPU is otherwise empty.

- Establish the memory boundary independently for every challenge and workload.
  Use an explicit human/project constraint when one exists; otherwise derive a
  conservative boundary from current free memory, co-resident processes, their
  expected growth, and a documented safety reserve.
- A human requirement that a co-resident service remain running is binding.
  Preserve that service, measure around it, and select an explicit shared budget
  for the current run rather than importing a number from another project.
- Pass the run-specific boundary to the profile adapter and its capacity policy.
  A profile cannot be approved when its measured peak exceeds that boundary.
- The launcher admission budget is not a hard CUDA partition. The adapter must
  measure its own peak, stop before risking an OOM, and carry the same approved
  configuration and budget into training.

## Required phases

1. Start with cache disabled and a conservative task-valid crop or patch. Change
   one resource dimension at a time and treat a container-local OOM as evidence.
   Estimate usable headroom from measured process memory and refine a safe/unsafe
   bracket without imposing a universal batch, growth factor, or utilization
   target. Record each decision and its rationale.
2. With the selected compute shape, measure a representative nonzero cache rate
   after a clean zero-cache baseline while monitoring host available memory and
   swap. Project larger cache settings only when the measured change supports
   them. Retain the highest verified safe setting without imposing a universal
   cache-rate ladder.
3. Verify the selected configuration with real training and its configured
   validation cadence before beginning a longer training run.

## Validation budget

Use validation during a compatibility smoke only when needed to prove the
end-to-end path. For a longer run, derive the validation cadence and evaluation
budget from the task, evaluator cost, project objective, and any human resource
constraint. Record the projected epoch count, scheduled validation points,
actual validation count, and the rationale as MLflow parameters and in the run
description. Do not inherit a cadence or pass count from another challenge.

Record crop/patch dimensions, batch size, patches per image, and
`effective_patches = batch_size * patches_per_image`; also retain PyTorch peak
memory, GPU utilization, host available RAM, and swap in the local optimization
record, alongside the immutable split hash and code/config fingerprint. GPU
and other hardware telemetry must not be emitted as TensorBoard or MLflow
metrics. A training run may proceed only when an approved record matches its
baseline and the workload verifies the split/config hash.
Approved records must declare policy version `adaptive-headroom-v1`; the local
launcher rejects records made by a fixed ladder.

An effective batch may exceed the number of unique patients only when the
adapter performs stochastic patch sampling with replacement. Record source-case
count and `effective_patches_per_source_case` in the profile and final run so
the dashboard makes repeated-patient exposure explicit; do not imply that a
large crop batch represents equally many independent patients.

For a new trainer, provide a small profile adapter that can execute the three
phases, write learning metrics through `tools/experiment_tracking.py`, retain
resource measurements only in local telemetry and its human-readable report,
and persist its approved record at:

```text
challenge/<challenge>/baselines/<baseline>/gpu_optimization/approved.json
```

Use `python3 tools/miagent_local.py optimize-gpu ... -- <adapter command>` for
an exclusive profile, or add `--shared-gpu --gpu-budget-mb <run-specific MiB>`
when a co-resident GPU service must remain running. Use
`python3 tools/miagent_local.py run --stage training ...` with the same shared
flags and run-specific budget for the resulting training job.
Audit, preprocessing, inference, and smoke stages do not require this record.

## MLflow experiment context

Every workload must write a concise Markdown description and searchable tags
through `tools/experiment_tracking.py`. The description states the scientific
question, data split, model/input representation, and why the run exists.
Parameters include model/checkpoint, optimizer, learning rate, scheduler,
precision, crop/ROI, context slices or 3D depth, batch size, patches per image,
effective patches, cache rate, epoch/step budget, validation cadence, and split
hash. Tags identify challenge, baseline, run kind, modality/task, model family,
and execution stage. The container entrypoint imports these into MLflow at run
completion; raw JSON and Markdown remain durable artifacts.

Use `record_parameter_descriptions(...)` for any parameter whose meaning is
not obvious from its name. The core entrypoint always adds end-to-end wall time
to MLflow and generates `tracking/dashboard.md`, then refreshes the challenge
dashboard's **Local Runtime Telemetry** table with wall time, a compact
parameter summary, and a link to the full per-run record. Do not overwrite
that generated table manually.

For imaging validation, use `record_image(...)` only after a validation pass.
Cap visual examples at two fixed validation patients per pass, log a clear
ground-truth/prediction overlay, and never log training or held-out test images
through this review channel. The helper writes to that run's single TensorBoard
directory and preserves PNG artifacts for MLflow.

Keep TensorBoard and MLflow metrics curated: log training loss, validation
metrics, and validation review images only. Send GPU/CPU/RAM/cache telemetry
through `record_telemetry(...)`; it remains local to the durable run directory
and feeds the optimizer's report, but is not uploaded to MLflow and must not
create TensorBoard scalar charts. Never pass GPU telemetry to `record_metric`
or `record_metrics`; the tracking helper defensively diverts GPU-named scalars
away from both metric dashboards.
