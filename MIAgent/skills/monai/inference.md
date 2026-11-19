# MONAI Inference And Export

Use MONAI's inferers for window generation, overlap blending, and output
stitching. Do not implement manual tiling unless a documented output topology
or model interface cannot be expressed by the installed inferer.

## Sliding-window inference

`SlidingWindowInferer` receives the input tensor first and the network second:

```python
import torch
from monai.inferers import SlidingWindowInferer

network = network.eval().to("cuda")
inferer = SlidingWindowInferer(
    roi_size=(128, 128, 128),
    sw_batch_size=1,
    overlap=0.25,
    mode="gaussian",
    sw_device="cuda",
    device="cpu",
)

with torch.inference_mode():
    logits = inferer(volume_on_cpu, network)
```

- `roi_size` is the spatial window and must be compatible with the network's
  downsampling and output-size constraints.
- `sw_batch_size` is the number of windows passed through the network together;
  it is not request concurrency or dataset batch size.
- `overlap` trades additional compute for reduced boundary artifacts.
- The default blend mode in MONAI 1.4.0 is `"constant"`. Request
  `mode="gaussian"` explicitly when weighted overlap is desired.
- `sw_device="cuda"` runs windows on the GPU, while `device="cpu"` accumulates
  the stitched output in CPU memory. Keeping the source volume on CPU avoids
  placing the entire input on the GPU; increase `sw_batch_size` only from
  measured memory evidence.

Inspect both constructor and call signatures in the workload environment:

```bash
python - <<'PY'
import inspect
from monai.inferers import SlidingWindowInferer

print(inspect.signature(SlidingWindowInferer))
print(inspect.signature(SlidingWindowInferer.__call__))
PY
```

## Postprocess according to task semantics

- Apply sigmoid plus a recorded threshold for binary or multilabel logits.
- Apply softmax/argmax for mutually exclusive multiclass logits.
- Keep probability maps separately when calibration or uncertainty analysis
  requires them; do not overwrite them with discretized labels.
- Use nearest-neighbor interpolation whenever a discrete prediction is
  spatially transformed.

MONAI dictionary pipelines may use `Activationsd` and `AsDiscreted`, but inspect
their installed signatures and configure each key explicitly.

## Restore the required output grid

When preprocessing used invertible MONAI transforms and retained its
`MetaTensor` history, apply the same preprocessing `Compose` through `Invertd`:

```python
from monai.transforms import Compose, Invertd, SaveImaged

postprocess = Compose(
    [
        Invertd(
            keys="pred",
            transform=preprocess,
            orig_keys="image",
            nearest_interp=True,
            to_tensor=True,
            device="cpu",
        ),
        SaveImaged(
            keys="pred",
            output_dir=output_dir,
            output_postfix="prediction",
            output_ext=".nii.gz",
            resample=False,
            output_dtype="uint8",
        ),
    ]
)
```

`orig_keys` identifies the transformed source whose recorded operations and
original metadata define the inverse for `pred`. Do not discard that source or
convert away its transform history before inversion. `nearest_interp=True` is
required for a discrete segmentation. Explicit inversion followed by
`SaveImaged(resample=False)` keeps export behavior inspectable.

Before relying on this pattern, verify `Invertd` and `SaveImaged` signatures in
the installed MONAI version and run a round-trip test because not every custom
or third-party transform is invertible.

## Validate the saved artifact

- Reload the saved file and compare shape, affine, orientation, spacing, dtype,
  and label set with the required reference grid.
- Confirm the filename/layout meets the evaluator's contract.
- Display the prediction over the original image in orthogonal views.
- For at least one nontrivially transformed case, verify a known landmark or
  foreground centroid in world coordinates.
- Run the official evaluator or downstream reader; successful NIfTI loading is
  not sufficient validation.
