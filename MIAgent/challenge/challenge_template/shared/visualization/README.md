<!-- miagent-template-source: challenge/challenge_template/shared/visualization/README.md -->
<!-- miagent-template-contract: active; keep the miagent-template-source loaded for creation/material updates; reload after resume or compaction -->
# Shared Visualization

Challenge-level debugging visualization used by every baseline. **Use the
supplied shared visualizer. Configure metadata only; do not rewrite or replace
it unless required functionality is demonstrably missing.** Reuse that
implementation for all experiments. Do not fork separate renderers inside
baseline folders.

| Field | Value |
|---|---|
| task type | `<segmentation / registration / generation / representation / VLM / other>` |
| implementation | `shared/visualization/visualizer.py` plus any challenge-wide helpers |
| canonical command | `python shared/visualization/visualizer.py --manifest <run>/visualization_manifests/visualization_manifest.json --output <run>/result_viewers/result_viewer.html` |
| normalized inputs | `<case IDs, image paths, reference, prediction, intermediates, metrics, and provenance>` |
| output | `baselines/<baseline>/runs/<exp>/result_viewers/result_viewer.html` plus relative assets; segmentation predictions with ground truth also receive colocated `<case>_error.nii.gz` and `<case>_review.html` artifacts. Store per-case metric tables in `<run>/per_case_dice/` and normalized manifests in `<run>/visualization_manifests/` instead of placing epoch artifacts at the run root. |
| validated by | `<smoke-run summary and viewer link>` |

Follow the relevant `skills/<task>/result_analysis.md` contract. The shared
renderer owns orientation, display ranges, colors/legends, synchronized views,
case selection, and HTML layout so evidence is comparable across baselines. A
baseline may add a thin exporter for its native output format, but it must feed
the shared renderer rather than create a separate gallery.

Run this renderer after every experiment that produces predictions. Before an
Important Completed Run drives the next training decision, expand its viewer to
satisfy the relevant task-specific result-analysis skill. An
engineering-only experiment may reuse an existing viewer when its summary
explains why no new predictions exist.

For NIfTI segmentation, the supplied renderer invokes
`tools/segmentation_review.py`, records the generated `error` and `review`
paths in each manifest case, and links the review from the all-case index.
Configure its manifest and intensity offset; do not reimplement this path.
Keep both generated files beside the exact prediction they describe, and
overwrite them after prediction regeneration so visual evidence cannot
silently refer to an older mask.

## Stable API

Keep these two callable entry points in `visualizer.py`:

```python
visualize_case(
    inputs,
    prediction,
    output_dir,
    *,
    ground_truth=None,
    case_id,
    intermediates=None,
    metrics=None,
    metadata=None,
)

visualize_run(manifest, output_html)
```

`inputs`, `prediction`, and `ground_truth` may be a path, a list of paths, or a
named path mapping. For example, segmentation can use `inputs={"image": ...}`
and `prediction={"mask": ...}`; registration can use
`inputs={"moving": ..., "fixed": ...}` and
`prediction={"warped": ..., "displacement": ...}`. The direct function is
for quick debugging. The run function consumes a JSON manifest with the same
fields for every case and builds the all-case `result_viewer.html`. Also keep
the canonical CLI so trainers and evaluation jobs can call the renderer without
importing challenge code.

Keep saved predictions and metrics as source artifacts; visualization should be
cheap to rerun without retraining. Extend this implementation when a result
reveals a missing diagnostic view, then regenerate affected run viewers. Treat
renderer interfaces as challenge-wide APIs: preserve existing inputs or update
all affected baseline adapters together.
