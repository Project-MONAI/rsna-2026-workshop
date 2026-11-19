# Data and label-map contract

## Inputs

Use a versioned dataset manifest with one entry per patient/case. Every entry
has a stable `case_id`, exactly one split (`train`, `validation`, or `test`), an
image path, and named binary mask sources. Paths are resolved relative to the
manifest file unless absolute.

Patient identities must be unique across all splits. Store a SHA-256 hash of
the final manifest and never rebuild the split implicitly inside a trainer.

## Label construction

The config defines contiguous output IDs starting at zero. ID 0 is background
and has no source. Each foreground class names one binary source mask, optional
source masks to exclude, a priority for overlap resolution, and whether an
empty class is allowed in an individual case.

For a minimal brain-lesion example:

| ID | Meaning | Rule |
|---:|---|---|
| 0 | outside-brain background | remaining voxels |
| 1 | brain without target | `brain > 0` and not `target > 0` |
| 2 | target lesion | `target > 0`; higher priority |

This example is not a universal anatomical model. Sparse three-class maps may
be too weak for useful image synthesis. Derived anatomy requires a documented,
training-only method with no label leakage and a validation audit.

The helper refuses shape or affine mismatches and does not silently resample.
Align masks using a separately recorded preprocessing step: continuous images
use an appropriate interpolation, while categorical labels use nearest-neighbor
interpolation. Record original and target orientation, spacing, shape, physical
volume, and interpolation.

Containment constraints (for example, lesion inside brain) must be explicit.
Resolve violations rather than clipping them silently. Record every output's
observed IDs, voxel counts, affine, spacing, source hashes, and output hash.

## Leakage boundary

`prepare-labels` defaults to `train` only. Validation maps may be prepared for
evaluation in a separately named operation, but may never enter the synthesis
or pretraining manifest. Test labels must not be prepared or inspected before
the challenge's held-out access policy permits evaluation.

For training, prove all generated inputs descend only from train-split sources.
For validation, use fixed real cases for checkpoint selection unless the
baseline contract explicitly studies synthetic-domain validation as a separate
diagnostic. Never select a checkpoint using the held-out test set.

## Pre-synthesis checks

Require:

- finite arrays and valid NIfTI headers;
- one channel and three spatial dimensions;
- nonempty total foreground;
- observed IDs contained in the declared ID set;
- required nonempty classes present when configured;
- image/mask shape, affine, orientation, and physical extent aligned;
- no duplicate case IDs or cross-split patient overlap;
- input manifest and prepared-manifest hashes recorded.
