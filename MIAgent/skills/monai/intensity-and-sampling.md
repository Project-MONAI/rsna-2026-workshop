# MONAI Intensity Conversion and Class Sampling

Read this before implementing intensity normalization/windowing or patch/slice
sampling. Treat the dataset contract as executable input, not documentation to
paraphrase.

## Convert stored values before normalization

Medical-image voxels are not necessarily stored in physical units. Apply the
dataset-declared scale and offset before a window expressed in HU or another
physical unit. For an affine conversion:

```text
physical_value = stored_value * scale + offset
```

In MONAI, keep conversion before windowing in the deterministic prefix:

```python
Compose([
    ShiftIntensityd(keys=["image"], offset=declared_offset),
    ScaleIntensityRanged(
        keys=["image"], a_min=window_low, a_max=window_high,
        b_min=0.0, b_max=1.0, clip=True,
    ),
])
```

Use `Lambdad` or a small tested transform when both a non-unit scale and offset
are required. Do not record a conversion in prose or tracking metadata unless
the executed transform contains it.

Before training, calculate on real training data:

- stored and physical min/max plus robust percentiles;
- the fraction clipped below and above every selected window;
- the same clipping fractions restricted to foreground labels when ground
  truth is available.

Fail preflight when the dataset contract's limits are exceeded. A finite loss,
valid tensor shape, or successful forward pass does not prove intensity
semantics. Near-constant or boundary-saturated target anatomy is a pipeline
failure.

## Sample all multiclass labels deliberately

`RandCropByPosNegLabeld` balances background against the union of foreground;
it does not balance individual foreground classes. For mutually exclusive
multiclass segmentation with unequal labels, prefer
`ClassesToIndicesd` plus `RandCropByLabelClassesd`, using ratios defined by the
dataset or experiment contract.

For 2D or 2.5D training, build slice weights from class presence or class voxel
frequency and sample with replacement. Do not weight only by total foreground
area because large structures can starve small classes.

Before a decision-bearing run, report the observed sampled center/class
frequency for every foreground class. Missing or severely underrepresented
classes block training until the sampler or declared intent is corrected.

## Budget optimizer updates, not epoch labels

An epoch is one traversal of the configured loader, not a comparable compute
unit. Record:

```text
steps_per_epoch = ceil(samples_per_epoch / batch_size)
total_optimizer_steps = steps_per_epoch * epochs
```

For a tiny source dataset under an epoch cap, use stochastic replacement
sampling to create sufficient independent patches or slices. Profile throughput
with a short real run, then choose exposure that uses the wall-time budget.
Do not declare a plateau while training loss is falling or the last scheduled
validation is improving; increase useful exposure before changing several loss
or architecture variables together.
