# TotalSegmentator Body Mask Execution

Use TotalSegmentator when a challenge needs a deployable CT-side body,
skin, or broad anatomy mask and a hand-built intensity threshold is too brittle.
For outside-body air cleaning, use it as a boundary protector: clamp only
high-confidence outside air and preserve a dilated TotalSegmentator body/skin
region.

## DFW Runtime Pattern

Prefer a short GPU interactive job for quick segmentation/debugging. Use CPU
only when the workload is non-urgent or GPU queue pressure makes it faster in
practice. On DFW, run TotalSegmentator inside the `groot.sqsh` container and
create an experiment-scoped venv with `--system-site-packages` so it reuses the
container's PyTorch/CUDA stack:

```bash
ENV=$DFW_MIAGENT_ROOT/<challenge>/baselines/<baseline>/runs/<exp>/.venv_totalseg
PY=/root/miniconda3/envs/gr00t/bin/python3

"$PY" -m venv --system-site-packages "$ENV"
"$ENV/bin/python" -m pip install --upgrade pip setuptools wheel
"$ENV/bin/python" -m pip install "TotalSegmentator==2.15.0"
```

The bare DFW host Python may fail on TotalSegmentator dependency resolution,
especially around DICOM-only dependencies such as `python-gdcm`. The gr00t
container route avoids modifying the shared host environment and reuses the
container's CUDA-compatible PyTorch installation.

## Command

Use NIfTI input and request only the needed broad body task:

```bash
"$ENV/bin/TotalSegmentator" \
  -i "$INPUT_CT_NII_GZ" \
  -o "$OUTPUT_DIR.tmp" \
  --task body \
  --fast \
  --device gpu \
  --quiet

test -f "$OUTPUT_DIR.tmp/body.nii.gz"
mv "$OUTPUT_DIR.tmp" "$OUTPUT_DIR"
```

For CPU fallback, change `--device gpu` to `--device cpu`. Prefer GPU execution
for bounded debugging when it materially shortens turnaround.

## DFW Container Notes

- Set a persistent cache so model weights are not re-downloaded every run:

```bash
export TOTALSEG_HOME_DIR="$DFW_MIAGENT_ROOT/.cache/totalsegmentator"
export TOTALSEG_WEIGHTS_PATH="$TOTALSEG_HOME_DIR/weights"
```

- Do not call `/usr/bin/time` inside the gr00t container; it may not exist and
  can cause exit `127` after installation succeeds. Use shell timing instead:

```bash
start_seconds=$SECONDS
"$ENV/bin/TotalSegmentator" ...
echo "TotalSegmentator elapsed $((SECONDS - start_seconds))s"
```

- Write outputs through a `.tmp` directory and move them into place only after
  required masks exist.

## Verification

Before using masks for a metric-bearing experiment, write a manifest and check:

```text
body.nii.gz exists
skin.nii.gz exists when boundary protection is needed
mask shape equals CT shape
max(abs(mask.affine - ct.affine)) == 0 or within chosen tolerance
body/skin voxel counts are nonzero and plausible
```

Keep optional plotting out of metric-bearing reconstruction array jobs unless
the plotting environment is already validated. Keep optional plots in a
separate post-metric stage when a plotting dependency could otherwise invalidate
a completed reconstruction or evaluation.
