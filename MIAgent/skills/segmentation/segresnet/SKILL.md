---
name: segresnet
description: Configure and run reproducible MONAI SegResNet training for supervised multiclass NIfTI segmentation using a dataset YAML contract and the supplied runner. Use when SegResNet is selected; do not write a replacement trainer.
---

# MONAI SegResNet

Use the supplied runner for 2.5D or 3D SegResNet experiments. Scientific
choices belong in a copied YAML configuration; do not create another trainer,
evaluator, prediction exporter, or result publisher when this runner supports
the requested path.

Use the supplied shared visualizer. Configure metadata only; do not rewrite or
replace it unless required functionality is demonstrably missing. The supplied
runner already publishes the manifest, predictions, categorical error maps,
per-case metrics, NiiVue reviews, and all-case index, so a SegResNet experiment
does not need challenge-specific visualization code.

## Required inputs

- A dataset YAML following [references/dataset-contract.md](references/dataset-contract.md).
- One copied and edited configuration from `templates/experiment-2d.yaml` or
  `templates/experiment-3d.yaml`.
- The normal MIAgent challenge, baseline, experiment, launcher, tracking, and
  heartbeat workflow.

Read `skills/monai/SKILL.md`, including `intensity-and-sampling.md`, before
changing preprocessing or sampling. Dataset-declared storage conversion is
binding and is applied by the runner before physical-unit windows.

## Stable command surface

The control container does not contain MONAI. Run every command, including
preflight, in the persistent training container through `miagent_local.py`.
After the launcher's `--`, the first executable must be `env`; a bare
`CQ500_ARCHITECTURE=...` token is not executable.

Copy one template to the baseline configuration directory, then use these
literal 2.5D command patterns (replace only baseline/experiment/config names):

```bash
mkdir -p challenge/imagechd_lab/baselines/baseline001_segresnet/configs
cp skills/segmentation/segresnet/templates/experiment-2d.yaml \
  challenge/imagechd_lab/baselines/baseline001_segresnet/configs/experiment-2d.yaml

python3 tools/miagent_local.py run \
  --challenge imagechd_lab --baseline baseline001_segresnet \
  --experiment exp001_preflight --stage other \
  --shared-gpu --gpu-budget-mb 1024 -- \
  env CQ500_ARCHITECTURE=2_5d_segresnet CQ500_CONTEXT_SLICES=7 \
  CQ500_PATCH_SIZE=256,256,32 \
  python3 /workspace/skills/segmentation/segresnet/scripts/run_segresnet.py preflight \
  --dataset /data/ImageCHD_lab/dataset.yaml \
  --config /workspace/challenge/imagechd_lab/baselines/baseline001_segresnet/configs/experiment-2d.yaml \
  --init-filters 32 --input-channels windows3

python3 tools/miagent_local.py run \
  --challenge imagechd_lab --baseline baseline001_segresnet \
  --experiment exp002_smoke --stage smoke \
  --shared-gpu --gpu-budget-mb 20480 -- \
  env CQ500_ARCHITECTURE=2_5d_segresnet CQ500_CONTEXT_SLICES=7 \
  CQ500_PATCH_SIZE=256,256,32 \
  python3 /workspace/skills/segmentation/segresnet/scripts/run_segresnet.py smoke \
  --dataset /data/ImageCHD_lab/dataset.yaml \
  --config /workspace/challenge/imagechd_lab/baselines/baseline001_segresnet/configs/experiment-2d.yaml \
  --init-filters 32 --input-channels windows3

python3 tools/miagent_local.py optimize-gpu \
  --challenge imagechd_lab --baseline baseline001_segresnet \
  --experiment exp003_gpu_optimization \
  --shared-gpu --gpu-budget-mb 20480 -- \
  env CQ500_ARCHITECTURE=2_5d_segresnet CQ500_CONTEXT_SLICES=7 \
  CQ500_PATCH_SIZE=256,256,32 \
  python3 /workspace/skills/segmentation/segresnet/scripts/run_segresnet.py profile \
  --dataset /data/ImageCHD_lab/dataset.yaml \
  --config /workspace/challenge/imagechd_lab/baselines/baseline001_segresnet/configs/experiment-2d.yaml \
  --init-filters 32 --input-channels windows3

python3 tools/miagent_local.py run \
  --challenge imagechd_lab --baseline baseline001_segresnet \
  --experiment exp004_train --stage training \
  --shared-gpu --gpu-budget-mb 20480 -- \
  env CQ500_ARCHITECTURE=2_5d_segresnet CQ500_CONTEXT_SLICES=7 \
  CQ500_PATCH_SIZE=256,256,32 \
  python3 /workspace/skills/segmentation/segresnet/scripts/run_segresnet.py train \
  --dataset /data/ImageCHD_lab/dataset.yaml \
  --config /workspace/challenge/imagechd_lab/baselines/baseline001_segresnet/configs/experiment-2d.yaml \
  --init-filters 32 --input-channels windows3
```

For 3D, copy `experiment-3d.yaml` and keep these four replacements identical
in smoke, profile, and train: `CQ500_ARCHITECTURE=3d_segresnet`,
`CQ500_PATCH_SIZE=128,128,64`, `--init-filters 16`, and
`--input-channels windows3_coord3`. The context token remains 7. Never change a
training token after profiling without rerunning `optimize-gpu`, because the
approval record is bound to the exact architecture, context, width, channels,
and patch.

The runner owns loading, physical-unit conversion, intensity windows,
class-aware sampling, SegResNet construction, BF16/FP32 execution, checkpoint
selection, full-volume validation, Dice, prediction export, error maps, and the
NiiVue result index. A smoke or profile proves wiring/capacity only.

## Experiment decisions

- Record `samples_per_epoch`, `steps_per_epoch`, and `total_optimizer_steps`.
  Under an epoch cap, scale sampled exposure after measuring throughput rather
  than treating the source-case count as the epoch length.
- Change one decision-bearing variable at a time when practical.
- Do not call a direction plateaued while loss is falling or the latest
  scheduled validation improves.
- Preserve failed runs as evidence and publish the best scheduled checkpoint,
  not merely the last checkpoint.

## Files

- [references/dataset-contract.md](references/dataset-contract.md): dataset YAML
  schema and preflight invariants.
- `templates/experiment-2d.yaml`: proven 2.5D multi-window starting recipe.
- `templates/experiment-3d.yaml`: proven 3D class-balanced starting recipe.
- `scripts/run_segresnet.py`: the only trainer/evaluator entrypoint.
