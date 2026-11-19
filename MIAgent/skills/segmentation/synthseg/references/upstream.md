# Upstream and environment contract

## Pinned source

- Repository: `https://github.com/brudfors/synthseg-monai.git`
- Commit: `9b25434ccbf3a7b4bd902008c4a2514213ac9e6c`
- Commit date: `2025-07-23T11:29:05+01:00`
- License: Apache-2.0
- Cornucopia commit declared upstream:
  `8b326481e799bff827cb4e245633631c26db435e`

The pin was verified from the upstream Git repository on 2026-09-08. A pin
change is a reviewed implementation change: inspect the diff, dependency
declarations, synthesis parameters, label behavior, checkpoint format, and
license before updating both this reference and the helper constant.

## What MIAgent reuses

The adapter may import:

- `transforms_synthseg.SynthSegd`, which wraps
  `cornucopia.SynthFromLabelTransform` and returns an image/label pair;
- `utils_synthseg.get_synth_params` only as a reviewed starting point for
  parameter ranges;
- `utils_synthseg.get_model` only when the upstream `BasicUNet` is itself the
  declared matched architecture.

Do not import `train_synthseg.py` as a library. It executes global setup and
training at import time, hard-codes paths/settings, uses the same label set for
training and validation, and does not satisfy MIAgent's split, tracking, or
held-out-test contracts. Implement a baseline-owned trainer around the reusable
transform instead.

Do not apply upstream `MapLabelsSynthSeg` to challenge labels. Its mapping is
specific to the anatomical labels in the original brain example. Prepare and
validate challenge labels explicitly.

## Cached checkout

Bootstrap once:

```bash
python3 skills/segmentation/synthseg/scripts/run_synthseg.py bootstrap
```

The default checkout is:

```text
runtime/upstreams/synthseg-monai/9b25434ccbf3a7b4bd902008c4a2514213ac9e6c/
```

Before every run, call `verify-upstream` or perform the same checks in the
adapter. Require the exact `HEAD`, expected origin URL, no tracked or untracked
changes, and the expected `LICENSE`, `transforms_synthseg.py`, and
`utils_synthseg.py` files. Mount the checkout read-only in workload containers.

## Training image integration

The persistent training image is derived from the repository's pinned core
image and installs this extension's `requirements.lock` alongside nnUNet. Do
not replace the core Torch/CUDA installation or
change core MONAI, NumPy, SciPy, nibabel, or pydicom versions. Run `pip check`
and save `pip freeze`, image tag, image digest, Torch/CUDA/MONAI/Cornucopia
versions, and GPU identity as build/preflight evidence.

The MIAgent adapter imports only the upstream synthesis transform, so the
extension lock adds pinned Cornucopia plus its `torch-interpol` and
`torch-distmap` dependencies. The upstream example trainer also declares
`nvidia-ml-py3`, matplotlib, tqdm, dicom2nifti, and wget; do not add those
packages unless adapter code actually imports them. Core already supplies
matplotlib/tqdm and MIAgent owns telemetry and asset acquisition.

Do not create an ephemeral SynthSeg container. The MIAgent launcher uses the
already-running `training` service for core, nnUNet, and SynthSeg work.

An experiment-scoped virtual environment is a fallback only. It must be
explicitly selected and recorded; never install packages afresh for every
training run.
