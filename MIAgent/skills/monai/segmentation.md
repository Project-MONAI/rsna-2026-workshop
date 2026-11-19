# MONAI Segmentation

Use this guidance for segmentation pipelines implemented directly with MONAI.
It does not replace nnU-Net conversion/execution, an official MONAI Bundle, the
challenge split contract, or the experiment workflow.

## Build the data pipeline deliberately

Place reusable deterministic preprocessing before random sampling and
augmentation in one `Compose`. `CacheDataset` and `PersistentDataset`
automatically cache the result before the first MONAI `Randomizable` transform;
they do not have a `post_transform` constructor argument in MONAI 1.4.0.

```python
from monai.data import CacheDataset
from monai.transforms import Compose, RandCropByPosNegLabeld, RandFlipd

train_transform = Compose(
    [
        # deterministic loading and spatial/intensity preprocessing first
        deterministic_preprocess,
        RandCropByPosNegLabeld(
            keys=["image", "label"],
            label_key="label",
            spatial_size=(96, 96, 96),
            pos=1,
            neg=1,
            num_samples=2,
        ),
        RandFlipd(keys=["image", "label"], prob=0.5, spatial_axis=0),
    ]
)

train_dataset = CacheDataset(
    data=train_items,
    transform=train_transform,
    cache_rate=1.0,
)
```

- `CacheDataset` keeps cached deterministic outputs in memory.
- `PersistentDataset` stores them under its required `cache_dir` and can reuse
  them across processes or runs.
- `RandCropByPosNegLabeld` uses `label_key`; `pos` and `neg` are relative
  sampling weights. Its `num_samples` can return multiple dictionary samples
  per input item. It balances background against any foreground, not the
  individual labels of a multiclass target. Read `intensity-and-sampling.md`
  and use class-aware sampling when individual foreground labels matter.
- Keep all image and label keys together in random spatial transforms, using
  continuous interpolation for images and nearest interpolation for labels.
- Use validation transforms with no random augmentation.

Call `monai.utils.set_determinism(seed=<seed>)` when a reproducible diagnostic
or experiment requires it. Still record the data split, worker configuration,
software versions, and transform configuration; a seed alone does not prove
bitwise reproducibility.

## Match output and objective semantics

Determine whether the task is binary, mutually exclusive multiclass, or
overlapping multilabel before choosing channels, activations, losses, and
metrics.

- Binary or multilabel heads normally use independent logits and sigmoid-based
  loss/postprocessing.
- Mutually exclusive multiclass heads normally use one channel per class and
  softmax/cross-entropy-compatible semantics.
- Configure Dice-family losses deliberately: inspect `include_background`,
  `to_onehot_y`, `sigmoid`, `softmax`, class weighting, and empty-class
  behavior rather than accepting defaults blindly.
- Keep training loss separate from reported evaluation metrics. Patch-level
  training Dice is not full-volume validation Dice.
- Inspect the installed signatures for the selected network, loss, and metric;
  MONAI APIs and defaults vary across versions.

Architecture choice is a scientific decision rather than a MONAI default.
MONAI supplies components such as `UNet`, `SegResNet`, `DynUNet`, and
`SwinUNETR`, but a task-specific skill, selected baseline, or measured
experiment should justify the choice and configuration.

## MONAI-specific smoke checks

Before a full direct-MONAI training run:

1. Transform one representative image/label pair and inspect its `MetaTensor`
   shape, affine, dtype, intensity range, and label values.
2. Confirm random crops contain the intended foreground/background mixture and
   every returned patch has the expected shape. For multiclass work, also
   measure sampled coverage for every intended foreground label.
3. Run one model forward pass, compute the selected loss, and perform one
   optimizer step.
4. Save and reload a checkpoint and compare its model interface.
5. Run full-volume validation through the inference path and restore one
   prediction to the required output grid.

Read `transforms-and-geometry.md` for spatial preprocessing and `inference.md`
for full-volume validation and export.
