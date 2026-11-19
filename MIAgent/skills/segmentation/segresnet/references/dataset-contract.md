# SegResNet Dataset Contract

The dataset YAML is authoritative for paths, storage-to-physical conversion,
class semantics, geometry, sampling ratios, and evaluation labels. The split
file remains separate so train/validation membership is immutable and easy to
hash.

Required top-level mappings are `dataset`, `image`, `label`, `geometry`, and
`evaluation`.

- `dataset.root` is the runtime-visible directory; `dataset.split_file` is
  relative to it unless absolute.
- `image.physical_conversion` declares affine `scale` and `offset` applied as
  `physical = stored * scale + offset` before any window.
- `image.recommended_windows_hu` maps names to `[low, high]`. Experiment files
  select names, not duplicated numeric windows.
- `image.preflight_limits` bounds low/high clipping fractions measured within
  foreground anatomy using `image.preflight_window_hu`.
- `label.classes` lists every integer value and name. `label.foreground` owns
  the labels used for sampling and Dice; it is never inferred as one anatomy.
- `label.recommended_sampling_ratios` supplies one ratio per class for 3D
  `RandCropByLabelClassesd`. The background ratio may be lower than foreground
  ratios but remains a dataset/experiment decision.
- `evaluation.labels` explicitly defines the mean-Dice labels.

Preflight must fail on missing split files, overlap, image/label geometry
mismatch, undeclared label values, missing foreground classes, physical-unit
conversion/window saturation, or inconsistent class-ratio keys.
