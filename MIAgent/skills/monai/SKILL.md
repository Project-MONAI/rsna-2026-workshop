---
name: monai
description: Design, implement, debug, or review code that directly uses MONAI transforms, datasets, segmentation components, or inferers. Use for general MONAI pipelines when an nnU-Net or task-specific MONAI Bundle skill does not already own the workflow.
---

# MONAI

Use MONAI's maintained medical-imaging primitives before implementing custom
geometry, caching, patch sampling, or sliding-window logic. Preserve spatial
metadata and label semantics across the complete pipeline.

## Precedence

- Follow a task-specific skill or official MONAI Bundle when it directly covers
  the selected workflow. Do not replace its entrypoint with custom MONAI code.
- For nnU-Net baselines, follow `skills/segmentation/nnunet/conversion.md` and
  `skills/segmentation/nnunet/execution.md`. Use this skill only for MONAI code
  outside nnU-Net's owned preprocessing, training, and inference path.
- Continue to follow the challenge workflow, relevant task skill, and selected
  compute skill. This skill supplies MONAI-specific implementation knowledge;
  it does not redefine experiment management or compute policy.

## Verify the installed API first

Do not rely on memory for a transform name or constructor argument. Run checks
with the Python interpreter in the selected workload environment, not an
unrelated control shell:

```bash
python - <<'PY'
import inspect
import monai
from monai.transforms import ResampleToMatchd

print("MONAI", monai.__version__)
print(inspect.signature(ResampleToMatchd))
print(ResampleToMatchd.__doc__.splitlines()[0])
PY
```

Before committing code that names a MONAI class:

1. Import the class from the installed environment.
2. Inspect its signature and focused docstring.
3. Run the proposed transform on one representative item or a small synthetic
   case.
4. Use custom code only if the installed MONAI APIs cannot express the required
   behavior. Record that missing capability and test the custom implementation
   against a trusted reference.

Never invent a plausible transform name or keyword. In MONAI 1.4.0, for
example, the reference key for `ResampleToMatchd` is `key_dst`, the foreground
crop is `CropForegroundd`, and `SlidingWindowInferer` is called with inputs
before the network. Reinspect these APIs when the installed version changes.

## Read the relevant guidance

- Read [intensity-and-sampling.md](intensity-and-sampling.md) before changing
  intensity conversion, normalization/windowing, or multiclass patch/slice
  sampling.
- Read [transforms-and-geometry.md](transforms-and-geometry.md) before changing
  medical-image loading, orientation, spacing, alignment, cropping, or affine
  handling.
- Read [segmentation.md](segmentation.md) for a directly implemented MONAI
  segmentation dataset, sampler, model, loss, metric, or training loop.
- Read [inference.md](inference.md) for sliding-window inference,
  postprocessing, inversion to source space, or prediction export.

Read every document that applies to the requested path, but do not load
unrelated references merely because MONAI is installed.

## Completion checks

- Exact imports and constructor signatures pass in the workload environment.
- Dataset-declared physical-unit conversion is present in executed code, and
  foreground clipping/percentile checks pass before training.
- Multiclass sampling evidence covers every intended foreground label, and the
  run records optimizer steps per epoch plus total optimizer steps.
- Image and label transforms preserve the intended geometry and label values.
- A one-item transform smoke test and one model/inference smoke test pass when
  those stages are in scope.
- Saved predictions are checked in the geometry required by the evaluator or
  downstream consumer.
