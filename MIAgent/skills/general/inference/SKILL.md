---
name: inference
description: Run pretrained medical-image inference in the prepared lab and publish image/prediction pairs for the existing NiiVue viewer. Not for training or fine-tuning.
---

# Inference and viewer handoff

## Defaults for a short request

A request such as "Run NV-Segment-CT on ImageCAS and let me view the results"
is enough. Apply these defaults without requiring the student to repeat them:

- Run pretrained inference only; do not train or fine-tune.
- Do not read ground-truth labels or solution predictions unless evaluation
  is explicitly requested.
- Reference the original image, optionally through a symlink; do not copy it
  just for viewing.
- Save each case in one unique folder under `/workspace/inference_tmp/`.
- For segmentation, use all automatic labels supported by the selected model
  unless the user requests a subset. Use that model's label dictionary.
- For a dataset-wide request, process its available cases sequentially and
  publish each result before moving on. Do not silently reduce it to one case.
- Publish the full prediction for NiiVue and return clickable viewer links.
- If the prepared model is missing or GPU admission fails, explain and stop
  rather than installing, downloading, or restarting services.

## Execution

- In the prepared lab, before NV-Segment-CT inference, first run
  `python3 tools/prepare_lab_models.py --status`.
  This only reads shared-cache readiness; it does not download anything or need
  imaging libraries. When status is `preparing`, tell the student "Inference
  model is still preparing" and stop. For `failed` or `not_started`, report
  the status and ask for instructor preparation. Do not repair, download,
  install, or substitute another model from the agent session.
- Read the selected model's skill for its supported inputs, labels, and exact wrapper.
  Do not rediscover the workflow by browsing old challenge results or solutions.
- Use the prepared training container for imaging libraries and GPU execution.
  Submit through `tools/miagent_local.py run --stage inference --shared-gpu`
  with an explicit GPU-memory budget. Do not install packages, download weights,
  or restart services unless the user authorizes preparation separately.
- If the model or input is missing, or GPU admission fails, explain and stop.
  Do not read ground truth unless evaluation is explicitly requested.

## Files

Use one uniquely named direct child of `/workspace/inference_tmp/` per case/run.
There is no required extra dataset, anatomy, or `all/` directory hierarchy.
Keep the wrapper's raw outputs and `result.json` in that run folder.

The input stays at its original `/data/.../image.nii.gz` path. Do not copy it
just for visualization. An optional `image.nii.gz` symlink may point there, but
the viewer URL must use `data-files/` because the file browser intentionally
does not follow links outside its output root.

Do not change image intensities or geometry just to make a result look better.
If a model needs documented preprocessing, preserve the source and record the
derived input. The published mask must match the geometry of the displayed CT.

## Publish

For NV-Segment-CT or NV-Segment-CTMR, run the existing publisher **in the training
container** after the model wrapper finishes:

```bash
python3 tools/publish_nv_inference.py \
  --run-dir /workspace/inference_tmp/RUN_NAME \
  --image /data/DATASET/cases/CASE/image.nii.gz
```

Replace the paths with the selected case. The publisher reads `result.json`,
checks the actual image/mask shape and affine, and creates `manifest.json` and
`result_viewer.html`. It preserves all global prediction IDs in
`prediction_global.nii.gz`, which is the default overlay. It does not require
a particular anatomy to be present in that global view.

`--overlay heart` is an optional NV-specific reduced view, not the generic
contract. The default display offset is zero. Only pass `--hu-offset` when
the displayed image has a documented stored-value offset; never apply 1024
universally to all datasets. A display offset does not calibrate the image.

For another model, use its existing publisher if available, retaining the same
image/prediction handoff. If no compatible publisher exists, report that gap
rather than inventing model arguments, claiming publication, or repeatedly
searching old runs.

## Completion

Open `/miagent/`, expand `inference_tmp`, and choose the run's
`result_viewer.html`. Viewer links use the current lab origin, not a hardcoded
Brev hostname. Confirm that both the source CT URL and mask URL load.
Return the clickable viewer link, source image, requested/observed labels,
runtime, and validation status. Do not call it complete merely because the
model exited. If publication fails, report that separately and retain the
prediction for repair. These are research outputs, not clinical results.
