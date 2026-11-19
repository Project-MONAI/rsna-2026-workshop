---
name: nv-segment-ct-finetune
description: Used for smoke or dataset finetuning of NV-Segment-CT VISTA3D on CT NIfTI labels. Not for clinical validation.
license: Apache-2.0
allowed-tools: Bash
metadata:
  author: NVIDIA MedTech Team
  tags:
    - MedTech
    - CT
    - finetuning
    - segmentation
---

# NV-Segment-CT Finetune

## Purpose

- Used for smoke or dataset finetuning of NV-Segment-CT VISTA3D on CT NIfTI labels. Not for clinical validation.
- Wraps the upstream MONAI bundle entrypoint; do not replace it with handwritten training or inference code.
- Manifest inputs are `dataset_dir`, `datalist`, `target_anatomy`, `label_mapping`, `smoke`, `sanity`, `auto_seg`, and `skip_formal_eval`.
- Manifest outputs are `finetuned_ckpt` and schema-checked `result_json`.

## Instructions

- Run `scripts/run_finetune.py`; do not patch files under `bundle/` or upstream checkouts during normal skill use.
- For standalone Bash, include the fresh-environment setup line before the wrapper; benchmark venvs start empty.
- Run the committed script in place from the repo root. Do not copy this skill to a runtime directory, and do not use `rm` or cleanup commands in generated invocations.
- If a host exposes `run_script`, use `run_script("scripts/run_finetune.py", args=[...])`; otherwise run from the repo root.
- For the shortest workflow check, use `--smoke`; for MSD Task06 Lung Tumor reproduction, use `--sanity`.
- Read `references/task06-and-results.md` only when you need Task06 reference details, output-field definitions, or manual bundle setup notes.

## Available Scripts

| Script | Purpose | Arguments |
|---|---|---|
| `scripts/run_finetune.py` | Primary entrypoint declared by `skill_manifest.yaml`; stages configs, runs MONAI, and writes `output.json`. Initial validation is always disabled. | `[FIXTURE_OR_DATASET] --output-dir OUT_DIR [--smoke] [--sanity] [--auto-seg] [--dataset-dir DIR] [--datalist JSON] [--target-anatomy TEXT] [--label-mapping JSON] [--patch-size JSON] [--steps-per-epoch N] [--val-interval N]` |

## Prerequisites

- Python 3.10+ with CUDA-capable Torch for GPU runs.
- Runtime packages from `skill_manifest.yaml`, especially `monai==1.4.0`, `numpy<2`, `nibabel`, `scipy`, `typer`, `PyYAML`, `fire`, `pytorch-ignite`, `einops`, and `huggingface_hub`.
- Optional environment variables: `CUDA_VISIBLE_DEVICES` restricts visible GPUs; `NPROC_PER_NODE` overrides GPU count and values `>=2` select multi-GPU mode for non-sanity runs.
- Side effects: writes generated MONAI configs under the caller's run-local `<output-dir>/configs/`, writes checkpoints/evidence under `--output-dir`, may cache model assets under `~/.cache/huggingface/`, and may contact `https://huggingface.co` or `https://raw.githubusercontent.com`. Run-local configs keep distinct output directories safe from cross-run config overwrites.

Fresh environment setup:

```bash
python -m pip install "monai==1.4.0" "numpy<2" "pytorch-ignite==0.5.5" einops nibabel scipy typer PyYAML "fire==0.7.1" huggingface_hub
```

Known upstream compatibility constraints:

- DFW Task06 reference: Python `3.10.16`, MONAI `1.4.0`, Torch `2.7.0+cu126`.
- Use exact `monai==1.4.0` for smoke, sanity, and evidence runs; MONAI 1.5.x can crash the upstream finetune loss on boolean labels.
- Do not float the dependency as `monai>=1.4,<1.6` in generated commands.

## Usage

Smoke-scale workflow check:

```bash
python -m pip install "monai==1.4.0" "numpy<2" "pytorch-ignite==0.5.5" einops nibabel scipy typer PyYAML "fire==0.7.1" huggingface_hub && \
python skills/nv-segment-ct-finetune/scripts/run_finetune.py \
  PATH_TO_DATASET \
  --smoke \
  --patch-size '[64,64,64]' \
  --output-dir runs/nvseg_smoke
```

Use the staged dataset as `PATH_TO_DATASET`. For the micro fixture, use `skills/nv-segment-ct-finetune/fixtures/spleen_micro`. Smoke mode proves wiring, config generation, checkpoint loading, and runtime compatibility; it is not a quality bar.

MSD Task06 Lung Tumor sanity reproduction:

```bash
python skills/nv-segment-ct-finetune/scripts/run_finetune.py \
  /path/to/Task06 \
  --sanity \
  --output-dir runs/nvseg_task06_sanity
```

The sanity preset follows the single-GPU DFW recipe: fold-0 validation, label mapping `[[1, 23]]` for `lung tumor`, automatic class-prompt segmentation, patch `[128,128,128]`, 5 epochs, and original-spacing `configs/evaluate.json` scoring before and after training. Expected reference range is pretrained Dice about `0.6697`, training-best Dice about `0.6905`, and fine-tuned formal Dice about `0.6836`.

User-data finetune:

```bash
python skills/nv-segment-ct-finetune/scripts/run_finetune.py \
  --dataset-dir /path/to/dataset \
  --datalist /path/to/datalist.json \
  --target-anatomy "lung tumor" \
  --auto-seg \
  --epochs 5 \
  --patch-size '[128,128,128]' \
  --output-dir runs/nvseg_user_finetune
```

Use `--label-mapping '[[1, 23]]'` when local label values are custom or the anatomy name is ambiguous.

Time-bounded small-dataset finetune with SegResNet-like exposure accounting:

```bash
python skills/segmentation/nv-segment-ct-finetune/scripts/run_finetune.py \
  --dataset-dir /path/to/dataset \
  --datalist /path/to/datalist.json \
  --label-mapping '[[1,133],[2,134]]' \
  --auto-seg --skip-formal-eval \
  --epochs 10 --steps-per-epoch 64 \
  --val-interval 5 \
  --patch-size '[96,96,96]' \
  --output-dir runs/nvseg_bounded
```

`--steps-per-epoch` samples cases with replacement and produces one randomly
cropped 3D patch per optimizer update. Use it to compare training exposure
rather than raw epoch counts across architectures. The example performs 640
updates and validates only at epochs 5 and 10. It is a practical starting point
for a five-case, sub-20-minute lab run on the profiled local GPU, not a general
quality guarantee. Keep the default upstream behavior when reproducing a
published recipe except for this skill's invariant that initial validation is
disabled.

Initial validation is always disabled by the wrapper. Do not add a separate
pre-training validation pass: it spends time scoring unchanged weights and can
leave the best-checkpoint saver pointing at epoch zero.

## Examples

Smoke run on a staged tiny dataset:

```bash
python skills/nv-segment-ct-finetune/scripts/run_finetune.py \
  runs/with_vs_without_nv/_inputs/nv_segment_ct_finetune/input_dataset \
  --smoke \
  --patch-size '[64,64,64]' \
  --output-dir runs/nvseg_smoke
```

Task06 sanity run on a local MSD cache:

```bash
python skills/nv-segment-ct-finetune/scripts/run_finetune.py \
  .workbench_data/datasets/Task06_Lung \
  --sanity \
  --output-dir runs/nvseg_task06_sanity
```

## Data Contract

- Preferred layout: `dataset/imagesTr/*.nii.gz` and `dataset/labelsTr/*.nii.gz`.
- Labels must align one-to-one with images by basename.
- The target label value must be present in the training labels.
- Use a datalist when patient-level splitting matters. The bundle default `fold` is `0`, so `fold: 0` entries are validation and all other folds are training.
- For normal fine-tuning, every foreground label must map to the anatomically
  matching VISTA3D global class ID from `bundle/label_dict.json`. Never map a
  structure onto a merely similar or convenient pretrained name.

## Experimental Novel-Class Feasibility

Use this mode only when the human explicitly asks to train structures absent
from `label_dict.json`. Keep it separate from normal pretrained-class claims:

- `vista3d132` has 512 class-embedding rows and treats IDs above its
  `last_supported=132` boundary as zero-shot. IDs 133–254 are mechanically
  usable by the continual-training path but have no named pretrained anatomy.
- Prefer unused reserved IDs, assigned deterministically from 133 upward, for
  unsupported structures. Preserve the exact pretrained ID for any supported
  structure; for example, retain `aorta -> 6` while assigning the six
  unsupported ImageCHD structures to 133–138.
- A compact local-ID control such as local labels 1–7 mapping to prompt IDs
  1–7 is allowed only when clearly labeled as semantically mismatched: those
  rows represent other pretrained anatomy (and some IDs may be unnamed). It is
  an adaptation control, not a deployable anatomy mapping.
- Use `--auto-seg` for class-prompt-only training. It sets
  `drop_label_prob=0.0` and `drop_point_prob=1.0`; the point head is not trained.
  Verify that claim by comparing `point_head.*` tensors when it matters.
- Keep the two mapping strategies controlled: same datalist, split, seed,
  patch, cache rate, learning rate, epochs, and evaluation path. Run them
  sequentially when sharing a GPU.
- The standard formal evaluator may reject IDs above 132 without points. A
  `--skip-formal-eval` run is therefore only training-path feasibility evidence:
  report its training-time validation trajectory and explicitly state that it
  produced no per-case predictions or NiiVue artifacts.
- Novel-class feasibility is a materially different solution claim. Create a
  new baseline direction rather than appending it to an exact-vocabulary subset
  baseline.
- The default continual recipe samples one patch per training case per epoch.
  On five training cases, five epochs are only 25 optimizer steps; treat such a
  run as feasibility evidence, not a quality verdict.
- For bounded novel-class experiments, set the exposure explicitly with
  `--steps-per-epoch` and reduce validation overhead with `--val-interval`.
  Initial validation is always disabled. Ensure the final epoch is a validation epoch. On the
  five-case ImageCHD lab profile, `10 x 64 = 640` optimizer updates with
  validation at epochs 5 and 10 is the current under-20-minute starting recipe.

## Results

Check `output.json` in the run directory first:

- `formal_pretrained_val_dice` and `formal_finetuned_val_dice`: original-spacing pre/post scores when formal eval is enabled.
- `training_start_val_dice`, `val_dice_per_epoch`, and `training_best_val_dice`: training-time validation trace.
- `finetuned_ckpt_matches_pretrained_weights`: verifies that the selected post-training checkpoint changed from the pretrained weights.
- `recommended_ckpt`: checkpoint to keep. Do not blindly use the last epoch or `model_finetune.pt`.
- `runtime.oom`, `runtime.peak_gpu_mb`, and phase logs: distinguish OOM, slow validation, and process failure.

Decision rule: prefer formal original-spacing pre/post scores when present; reject tensor-identical "fine-tuned" checkpoints for sanity recovery; treat `improved: false` as valid evidence rather than a wrapper failure.

## Limitations

- Thin wrapper. Training, validation, transforms, and checkpointing are delegated to the upstream bundle in `bundle/`.
- The auto-derived plan is heuristic; caller-provided `--patch-size`,
  `--cache-rate`, `--epochs`, `--steps-per-epoch`, `--val-interval`, and
  `--learning-rate` win.
- The Task06 sanity recipe intentionally forces single-GPU execution to match the DFW reference. Multi-GPU mode for other datasets requires host `torchrun` support.
- The paired verifier is CPU-only and audits the evidence pack; it does not re-run GPU segmentation.
- Not for clinical deployment, clinical interpretation, autonomous diagnosis, or regulatory submission.

## Troubleshooting

| Error | Cause | Fix |
|---|---|---|
| Missing dependency or import error | Runtime drift from `skill_manifest.yaml`. | Install the packages above or use the documented environment. |
| Low Task06 pretrained Dice | Wrong config, wrong checkpoint, data split drift, or dependency drift. | Compare environment fields and staged configs before changing training logic. |
| `model_finetune.pt` matches pretrained | No post-training validation improved enough to save changed weights, or training did not update the intended parameters. | Inspect the validation trajectory and tensor comparison; treat sanity recovery as failed unless a changed checkpoint improves formal Dice. |
| Missing formal Dice fields | Formal eval failed or was skipped. | Inspect `eval_pretrained.log`, `eval_finetuned.log`, and `metrics.csv`. |
| GPU out of memory | Patch/cache settings too large. | Reduce `--patch-size`, lower `--cache-rate`, or reduce workers. |
| No validation cases | Datalist lacks `fold: 0`. | Provide at least one validation entry. |

## Verification

Run the implemented verifier when quality gates matter:

```bash
python -m eval_engine.run_trusted skills/nv-segment-ct-finetune \
  --fixture skills/nv-segment-ct-finetune/fixtures/spleen_micro \
  --out runs/nvseg_trusted
```
