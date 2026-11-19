# Workshop Data Preparation

Download only the existing fixed 10-case cohorts from each original Kaggle
dataset, then resample images and labels onto matching RAS grids. Everything
is written to explicitly selected output directories; existing lab data is
not modified.

Data dependencies are installed in a standalone container, not on the host.
The host runner uses only Python's standard library and Docker. This container
is outside `MIAgent/docker-compose.yml` and is removed when preparation exits.

```bash
python3 lab_prep/run_data_prep.py --plan
```

Inspect the selected members without downloading the image volumes:

```bash
python3 lab_prep/run_data_prep.py list
```

Download and prepare both cohorts at 2 mm isotropic spacing:

```bash
python3 lab_prep/run_data_prep.py all \
  --raw-dir /tmp/workshop-data/raw \
  --output-dir /tmp/workshop-data/prepared --spacing-mm 2 \
  --unknown-labels background
```

The runner builds `miagent-data-prep:0.1.0`, then runs it with only the raw and
output directories mounted. The process uses your host UID/GID so outputs remain
owned by you. No GPU, Docker socket, lab workspace, or GitHub token is passed in.
The build context excludes downloaded data, secrets, Git metadata, and caches.
The image is retained for later runs; the one-shot container is removed.

Use `download` or `resample` instead of `all` to perform the stages separately.
Use `--dataset ImageCAS` or `--dataset ImageCHD` to select a single cohort.
Use empty output directories; the script refuses to overwrite case files.

## Transfer Method

The sources are `xiaoweixumedicalai/imagecas` and
`xiaoweixumedicalai/imagechd`. Kaggle exposes multi-part ZIP files, not separate
NIfTI case downloads. The downloader requests raw archive parts with
`raw=true`, reads their central directory using HTTP byte ranges, then reads
only blocks containing the requested members. A 4 MiB block cache introduces
small transfer overhead. It never silently falls back to a full-dataset
download. ZIP decoding and member CRC checks use Python's `zipfile` library;
the adapter translates split-disk offsets. ZIP64 central directories are not
supported; the current source archives use ordinary central directories.

Public access worked without credentials during testing. If access policies
or the archive layout change, the script fails explicitly. No keys are stored.

## Scientific Contract

- ImageCAS: cases 90-99; fixed five training and five validation cases.
- ImageCHD: cases 1122, 1135, 1138, 1139, 1140, 1143, 1145, 1147, 1148, 1170;
  retain the existing fixed five/five split.
- Image interpolation is linear; label interpolation is nearest neighbor.
- Images are float32; labels are uint8 with original class IDs.
- CT intensities are not windowed or normalized. ImageCAS stores HU directly;
  ImageCHD retains its shifted encoding, with HU = stored value - 1024.
- Geometry and class IDs are checked before and after preparation.
- Outputs include `split.json`, `dataset.yaml` (JSON-compatible YAML),
  `dataset.json`, SHA-256 checksums, and timing reports.

The original ImageCHD annotations contain undocumented IDs 13 in case 1122
and 12 in case 1148. The publisher documents anatomy IDs 1-7 only:
https://github.com/XiaoweiXu/ImageCHD-A-3D-Computed-Tomography-Image-Dataset-for-Classification-of-Congenital-Heart-Disease
The default `--unknown-labels background` converts undocumented IDs to zero
before nearest-neighbor label resampling, keeping the seven documented classes.
Every affected case records the original voxel counts and selected policy.
Use `--unknown-labels error` to stop instead, or `--unknown-labels preserve` to
retain those IDs; preservation requires a separate training/evaluation policy.

Resampling ImageCAS to 2 mm changes the native-resolution lab and can remove
small coronary structures. Use a finer `--spacing-mm` for coronary tasks;
the downloaded raw cohort remains available for native-resolution work.
The new ImageCHD grid follows its physical affine and may differ from the
earlier manually prepared lab; do not assume identical prior benchmark scores.

## Measurement

Each raw dataset has `download_report.json`, including actual range payload
bytes, HTTP request time, download/extraction time, and Mbps. Mbps means
megabits per second, not MB/s. Dataset-listing bytes and HTTP headers are
excluded. Each prepared dataset has `preprocessing_report.json`, including
per-case time, total time, geometry, retained labels, and compressed output size.
The reports measure the stages separately; dependency installation is excluded.

Run offline data tests inside the same image (no network or host data mounts):

```bash
docker build -t miagent-data-prep:0.1.0 lab_prep
docker run --rm --network none --entrypoint python miagent-data-prep:0.1.0 \
  -m unittest discover -s /opt/lab-prep -p test_prepare.py -v
```
