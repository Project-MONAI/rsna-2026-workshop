# Segmentation Result Analysis

Use this to plan evidence and diagnose semantic, instance, or small-structure
segmentation. Adapt it to the evaluator; do not assume Dice alone defines
success.

## Initial Viewer For Every Experiment

Use the supplied shared visualizer. Configure metadata only; do not rewrite or
replace it unless required functionality is demonstrably missing. Invoke it
after every experiment that produces segmentations, regardless of baseline.
Its `visualize_case(...)` call accepts image NIfTI path(s), prediction,
optional ground truth, case ID, metrics, and output directory; its
`visualize_run(...)` path builds the indexed run viewer from the same normalized
fields. For nnU-Net baselines, use
[`nnunet/visualization`](nnunet/visualization/README.md) for log parsing,
training curves, orthogonal case rendering, and indexed HTML; configure the
supplied challenge renderer as the label/palette/provenance adapter. Inspect the
viewer before interpreting metrics. Provide an all-case index.

For each evaluated NIfTI prediction with ground truth, the shared viewer must
also persist two human-review artifacts **in the prediction's own directory**:

```text
<case>_prediction.nii.gz
<case>_error.nii.gz
<case>_review.html
```

The review HTML must open the source image and let the human switch among the
prediction, ground truth, and error overlays. It must use relative artifact
paths so moving the run as a unit does not break it. The error NIfTI is a
categorical voxel map derived from the exact saved prediction and reference:
0 correct background, 1 correct foreground class, 2 false positive, 3 false
negative, and 4 wrong nonzero class. Record the `error` and `review` paths in
the run's visualization manifest and link every review from the all-case index.
Regenerate both whenever the prediction or ground truth changes; do not let a
stale error map survive a new inference result. In this repository,
`python3 tools/segmentation_review.py --manifest <run>/visualization_manifests/visualization_manifest.json`
provides the deterministic NIfTI/HTML generation step; pass the dataset's
stored CT intensity offset with `--hu-offset` when applicable.

Keep repeated evaluation artifacts out of the experiment root: write per-case
metric tables under `<run>/per_case_dice/`, run-level HTML indexes under
`<run>/result_viewers/`, and visualization manifests under
`<run>/visualization_manifests/`. Predictions, error maps, and their colocated
interactive review pages remain together in the prediction directory.

For 3D data, show synchronized axial, coronal, and sagittal views at the same
location for each selected case and class; for 2D data, show the corresponding
full-image panels. Each view must show these panels side by side:

```text
original image
original image + ground truth overlay
original image + prediction overlay
original image + error overlay with TP, FP, and FN in distinct labeled colors
```

Use correct orientation, spacing/aspect ratio, fixed intensity windows, a fixed
color legend, and identical slice coordinates across panels. Show every input
modality when relevant. The initial viewer includes fixed reference and
representative cases. For a key experiment, expand it with best, median, worst,
empty-label, small-target, and failure-specific cases plus relevant
intermediates. Interactive slice/class controls are preferred; a static viewer
must select the largest-target and largest-error locations in all three planes.
An axial-only montage does not pass.

Before trusting an apparent image/mask mismatch, prove that the source image and
label, network input and target, saved prediction, and displayed overlay refer
to the same case and coordinate system. For multimodal input, show every
modality rather than silently choosing one channel. If train-set predictions
are empty, noisy, or implausible, verify checkpoint head/decoder loading and
overfit one case or foreground-positive patch before changing the objective or
architecture.

## Evidence To Produce

- provenance naming the run/checkpoint, split/cases, input modalities,
  preprocessing, evaluator, orientation, and display ranges;
- per-case and per-class Dice plus the official surface metric;
- target presence, ground-truth/predicted volume, and object-size strata;
- raw image, ground truth, prediction, FP/FN, and boundary overlays in the
  correct orientation and spacing;
- fixed reference, best, median, worst, empty-label, and failure-specific cases;
- training/validation curves, patch foreground frequency, and inference output
  geometry.

The training curves belong in the same run viewer as the held-out visual and
metric evidence. Clearly label nnU-Net pseudo-Dice as an internal validation
signal rather than the official evaluator result. When training resumed, merge
all logs by epoch and let the newest complete record win so duplicated epochs
do not distort the plot.

Do not show an unexplained crop or montage without the source case, checkpoint,
mask semantics, and final prediction.

## Diagnostic Checklist

Consider and disposition applicable items; they are possible explanations, not
the diagnosis or a limit on the agent's reasoning.

- Good Dice with poor HD95 often indicates isolated false positives or one bad
  boundary; component filtering may help but can delete true small targets.
- Small or absent structures with low recall suggest resolution, crop, class
  mapping, foreground sampling, or loss imbalance before model capacity.
- Systematic left/right or anatomical confusion requires checking orientation,
  label mapping, and unsafe flips.
- Large predicted volume with low precision suggests threshold/calibration,
  background sampling, or weak localization; tiny volume with low recall
  suggests the opposite.
- A few catastrophic cases require site/modality/size subgroup inspection, not
  blind global tuning.
- Improving loss without official-metric or visual improvement can indicate a
  loss/evaluator mismatch.

Choose interventions only after identifying the failure pattern. Track the
classes, sizes, and previously strong cases that the intervention could harm.
