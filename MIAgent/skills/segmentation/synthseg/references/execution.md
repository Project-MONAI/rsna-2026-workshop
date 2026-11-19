# Execution contract

## Required gates

Pass these in order before a quality-bearing run:

1. **Dependency:** the combined training image builds, `pip check` passes,
   versions and image digest are recorded, CUDA is visible, and the core image
   remains its pinned base.
2. **Transform:** a tiny label fixture produces finite aligned output; fixed
   seeds replay categorical labels exactly and images within the helper's
   recorded `5e-7` absolute float32 CUDA tolerance, while different seeds
   produce variation; wall time and peak GPU memory are recorded.
3. **Challenge preparation:** one train case passes label, containment,
   geometry, split, and provenance checks.
4. **Optimizer smoke:** one train case and a small patch complete forward,
   finite loss, backward, optimizer step, checkpoint save/reload, one
   validation inference, tracking, and viewer generation.
5. **Core regression:** the ordinary preflight still passes and existing jobs
   execute in the persistent training service.
6. **Scientific feasibility:** a baseline contract defines a matched real-only
   control and one short intervention before longer compute.

## Baseline-owned adapter

Create one baseline-owned CLI with explicit phases such as `augment-train`,
`pretrain`, `finetune`, `infer`, and `evaluate`. It must import the verified
upstream transform from the read-only checkout, not copy or patch upstream
code. Keep preprocessing and model code shared between the intervention and
control; the controlled difference must be visible in `design.md` and config.

For augmentation-only mode, apply spatial transforms identically to the real
image and label. Preserve modality semantics when applying intensity effects.
SynthSeg's label-to-image GMM is not the same as CT HU augmentation.

For synthetic pretraining, sample only training label maps, log the number of
optimizer updates and source-case exposure, and checkpoint enough state for an
exact resume: model, optimizer, scheduler/scaler, epoch/update, RNG states,
config/split hashes, and upstream commit. Fine-tuning must record the source
checkpoint hash and use the same real-data recipe as its matched control.

## Canonical MIAgent commands

The `training` Compose service includes these dependencies. The following
launcher shape is canonical; substitute baseline-owned paths and immutable
experiment IDs.

Bootstrap/verify and transform smoke:

```bash
python3 skills/segmentation/synthseg/scripts/run_synthseg.py bootstrap
python3 skills/segmentation/synthseg/scripts/run_synthseg.py verify-upstream
python3 tools/miagent_local.py run \
  --challenge CHALLENGE --baseline BASELINE --experiment exp001_smoke \
  --stage smoke -- \
  python3 skills/segmentation/synthseg/scripts/run_synthseg.py smoke-synthesis \
  --config challenge/CHALLENGE/baselines/BASELINE/configs/smoke.yaml \
  --label challenge/CHALLENGE/baselines/BASELINE/fixtures/label.nii.gz \
  --output-dir challenge/CHALLENGE/baselines/BASELINE/runs/exp001_smoke/artifacts
```

Pretrain, resume, and fine-tune:

```bash
python3 tools/miagent_local.py run --stage training \
  --challenge CHALLENGE --baseline BASELINE --experiment EXPERIMENT -- \
  python3 challenge/CHALLENGE/baselines/BASELINE/scripts/run_synthseg_experiment.py \
  pretrain --config CONFIG

python3 tools/miagent_local.py run --stage training \
  --challenge CHALLENGE --baseline BASELINE --experiment EXPERIMENT -- \
  python3 challenge/CHALLENGE/baselines/BASELINE/scripts/run_synthseg_experiment.py \
  pretrain --config CONFIG --resume CHECKPOINT

python3 tools/miagent_local.py run --stage training \
  --challenge CHALLENGE --baseline BASELINE --experiment EXPERIMENT -- \
  python3 challenge/CHALLENGE/baselines/BASELINE/scripts/run_synthseg_experiment.py \
  finetune --config CONFIG --checkpoint PRETRAINED_CHECKPOINT
```

Inference and evaluation are separate phases in the same scientific experiment:

```bash
python3 tools/miagent_local.py run --stage inference \
  --challenge CHALLENGE --baseline BASELINE --experiment EXPERIMENT -- \
  python3 challenge/CHALLENGE/baselines/BASELINE/scripts/run_synthseg_experiment.py \
  infer --config CONFIG --checkpoint SELECTED_CHECKPOINT

python3 tools/miagent_local.py run --stage evaluation \
  --challenge CHALLENGE --baseline BASELINE --experiment EXPERIMENT -- \
  python3 challenge/CHALLENGE/baselines/BASELINE/scripts/run_synthseg_experiment.py \
  evaluate --config CONFIG --checkpoint SELECTED_CHECKPOINT
```

Do not invent launcher options that do not exist or install into the host
environment.

## GPU and validation policy

Use `skills/compute/gpu_optimization.md` for a new exact workload. Start from a
reasoned high candidate, back off on OOM, keep batch size no larger than unique
training cases, and distinguish batch size from patches per image and effective
patches. Re-profile only when memory-relevant inputs materially change.

Use one validation pass in an optimizer smoke. In training, schedule sparse
validation after timing early epochs, cap total passes as the compute contract
requires, and include a final pass. Validation is mandatory for a completed
quality-bearing experiment.

## Failure classification

- Dependency/import, geometry, non-finite output, checkpoint load, tracking, or
  OOM before an approved safe configuration: engineering failure; repair or
  reduce scope without creating a new scientific identity.
- Valid matched execution with no improvement: scientific negative result;
  preserve it and diagnose before choosing the next intervention.
- Accidental validation/test leakage: invalid evidence; quarantine artifacts,
  record the incident, and rerun from a clean admissible state.
- Interrupted run with a compatible checkpoint: resume the same experiment;
  do not create a new experiment merely for execution recovery.
