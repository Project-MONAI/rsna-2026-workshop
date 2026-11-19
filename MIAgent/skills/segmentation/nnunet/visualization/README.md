# nnU-Net Visualization Package

This package turns nnU-Net logs, saved NIfTI predictions, reference masks, and
official evaluator output into one portable diagnostic viewer. It is designed
for experiment evidence, not as a replacement for the official evaluator.

## What it produces

- a four-panel training curve: train/validation loss, per-class and mean
  pseudo-Dice, learning rate, and epoch duration;
- a machine-readable epoch JSON with resume logs de-duplicated by epoch;
- canonical sagittal, coronal, and axial image/ground-truth/prediction/error
  montages for every case, preserving every named input modality;
- an indexed HTML viewer containing training curves, provenance, per-class
  metrics, label/error legends, and source artifact paths.

Run from the MIAgent repository root:

```bash
python -m skills.segmentation.nnunet.visualization.cli curves \
  --log RUN/training_log_1.txt \
  --log RUN/training_log_2.txt \
  --output RUN/viewer_assets/training_curves.png \
  --json RUN/viewer_assets/training_curves.json

python -m skills.segmentation.nnunet.visualization.cli viewer \
  --manifest RUN/visualization_manifest.json \
  --training-log RUN/training_log_1.txt \
  --training-log RUN/training_log_2.txt \
  --output RUN/result_viewer.html
```

Use `--reuse-assets` to rebuild HTML and training diagnostics without reloading
NIfTI files when the case PNGs already exist locally. This is useful after
copying a cluster-generated run folder back to a workstation.

## Manifest extension

The normalized challenge manifest keeps `provenance` and `cases`, and may add:

```json
{
  "viewer": {
    "title": "My challenge segmentation evidence",
    "labels": {"1": "organ", "2": "lesion"},
    "colors": [[0, 0, 0, 0], [0.16, 0.64, 0.98, 0.62], [0.96, 0.45, 0.35, 0.62]]
  },
  "training": {
    "logs": ["/absolute/path/training_log_1.txt", "/absolute/path/training_log_2.txt"],
    "class_names": ["organ", "lesion"],
    "title": "fold 0 training diagnostics"
  }
}
```

Each case retains the stable challenge API fields: `case_id`, `inputs`,
`ground_truth`, `prediction`, `metrics`, and optional `metadata`.
For multi-modal data, use a named mapping so the viewer can label every image:

```json
{"inputs": {"image": {"FLAIR": "/case_0000.nii.gz", "T1c": "/case_0002.nii.gz"}}}
```

All modalities must share canonical shape and affine with the reference and
prediction. Each modality gets its own intensity window and display column;
reference, prediction, and error overlays use the first modality as background.

## Python API

```python
from skills.segmentation.nnunet.visualization import (
    parse_training_logs,
    render_training_curves,
    visualize_case,
    visualize_run,
)
```

Challenge renderers should be thin adapters that provide label semantics,
palette, title, modalities, and evaluator provenance. They should not fork the
generic log parser or HTML renderer.
