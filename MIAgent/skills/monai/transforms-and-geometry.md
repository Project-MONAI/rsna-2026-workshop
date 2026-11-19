# MONAI Transforms And Geometry

Read this file when code loads or spatially transforms medical images. Use
dictionary transforms for related images and labels so one operation receives
all keys and can preserve synchronized metadata.

## Establish the spatial contract

Before selecting transforms, inspect representative and exceptional cases:

- array shape and channel convention;
- affine, voxel spacing, and orientation codes;
- whether modalities and labels already occupy the same physical grid;
- image modality and intensity units;
- label values, class meanings, and overlap semantics;
- required output grid for training, evaluation, and export.

Shape equality is not proof of alignment. Resampling puts data on another grid;
it does not correct patient motion or anatomical misregistration. Use a
registration method when physical correspondence is not already valid.

## Prefer one resampling onto the final reference grid

For an image and discrete masks that start on potentially different affine
grids, define the final image grid first and resample each mask to it once. The
following pattern is verified against MONAI 1.4.0; inspect the installed
signatures before adapting it:

```python
from monai.transforms import (
    Compose,
    CropForegroundd,
    EnsureChannelFirstd,
    LoadImaged,
    Orientationd,
    ResampleToMatchd,
    Spacingd,
)

preprocess = Compose(
    [
        LoadImaged(keys=["image", "label", "brain"]),
        EnsureChannelFirstd(keys=["image", "label", "brain"]),
        Orientationd(keys=["image", "label", "brain"], axcodes="RAS"),
        Spacingd(keys=["image"], pixdim=(1.0, 1.0, 1.0), mode="bilinear"),
        ResampleToMatchd(
            keys=["label", "brain"],
            key_dst="image",
            mode=("nearest", "nearest"),
            padding_mode=("zeros", "zeros"),
        ),
        CropForegroundd(
            keys=["image", "label", "brain"],
            source_key="brain",
            margin=0,
            allow_smaller=True,
        ),
    ]
)
```

Important properties of this order:

- `Orientationd` permutes/flips all keys into a common axis convention while
  retaining their physical meaning.
- `Spacingd` creates the final continuous-image grid. MONAI's `"bilinear"`
  grid-sampling mode covers spatially 3D tensors as appropriate.
- `ResampleToMatchd` uses `key_dst`, not `source_key` or `key`, and puts both
  masks exactly on the final image grid using nearest-neighbor interpolation.
- The masks are not separately spaced and then resampled again.
- `CropForegroundd`, not `ForegroundCropd`, records the crop through MONAI's
  transform machinery. Choose a meaningful `source_key`; ordinary CT air is
  not automatically a suitable foreground definition.

Use continuous interpolation for CT, MRI, PET, probability maps, and other
continuous-valued images. Use nearest-neighbor interpolation for class maps,
binary masks, instance IDs, and other categorical arrays. For a synchronized
random spatial transform, include every spatially related key in the same
dictionary transform and provide the appropriate per-key modes.

## Preserve metadata and invertibility

Keep data as MONAI `MetaTensor` objects through spatial preprocessing when the
prediction must later return to the native grid. Do not convert to NumPy,
manually slice, overwrite an affine, and then assume MONAI can reconstruct the
discarded transform history.

Prefer invertible MONAI transforms for orientation, spacing, and cropping.
Retain both the preprocessing `Compose` object and the transformed source image
until prediction inversion is complete. Read `inference.md` for `Invertd` and
export.

## Validate geometry rather than headers alone

After preprocessing, check at least:

```python
import nibabel as nib
import numpy as np

assert image.shape[1:] == label.shape[1:] == brain.shape[1:]
assert np.allclose(image.affine, label.affine)
assert np.allclose(image.affine, brain.affine)
assert nib.aff2axcodes(np.asarray(image.affine)) == ("R", "A", "S")
assert np.allclose(nib.affines.voxel_sizes(np.asarray(image.affine)), (1, 1, 1))
assert set(np.unique(label.cpu().numpy())).issubset(expected_label_values)
```

These assertions verify stored geometry, not anatomical correspondence. Also:

- inspect image/label overlays in axial, coronal, and sagittal views;
- test a case with a different source affine or shape;
- compare physical landmarks or world-space foreground centroids when useful;
- record whether small foreground objects survive nearest-neighbor resampling;
- verify a cropped image's world origin and an inverse round trip.

Do not accept a check that saves every array with the same affine and then only
compares the saved headers.
