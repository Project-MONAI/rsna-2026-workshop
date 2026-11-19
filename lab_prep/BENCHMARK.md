# Measured Workshop Preparation

Measured on 2026-10-06 with fresh case downloads from Kaggle. Host: Intel Xeon
Platinum 8559C, 8 logical CPUs, 62 GiB RAM, Python 3.10. Processing is sequential
and CPU-only. Dependencies were installed in an isolated environment under
`/tmp/miagent-lab-prep-venv`; installation is excluded from the timings.

| Dataset | Cases | Range payload downloaded | Download + extraction | Effective speed | Resampling + verification | Prepared NIfTI size |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| ImageCAS | 10 | 904,459,069 bytes | 59.43 s | 121.75 Mbps | 45.20 s | 19,328,746 bytes |
| ImageCHD | 10 | 720,528,468 bytes | 46.77 s | 123.24 Mbps | 33.62 s | 128,525,670 bytes |

Combined download: 1,624,987,537 bytes (1.625 GB / 1.513 GiB) in 106.20 s.
Combined resampling: 78.82 s. The measured stages sum to **185.02 s**, about
**3 minutes 5 seconds**, excluding installation, investigation, and test reruns.

The complete selected source archives total 26,919,919,059 bytes. HTTP ranges
avoided approximately 94% of that transfer. Request latency is included in
effective Mbps; listing JSON and HTTP headers are excluded from payload bytes.
No full source archive or unrelated case was extracted. Range blocks include
small amounts of neighboring archive data.

Resampling uses 2 mm isotropic spacing and RAS orientation, linear CT
interpolation, and nearest-neighbor label interpolation. ImageCAS timing was
confirmed by a second pass (first pass: 45.38 s). Final preprocessing tests
reuse downloaded files and can benefit from the operating system's file cache.
These are host-specific measurements, not laptop or shared-Wi-Fi guarantees.

## Validation and Annotation Finding

- All selected ZIP members passed CRC validation during extraction.
- All 20 ImageCAS raw files matched the existing lab's SHA-256 checksums.
- All 20 prepared case pairs passed 2 mm/RAS shape and affine checks.
- All 40 prepared NIfTI files passed generated SHA-256 checksums.
- Six offline tests cover split-disk boundary reads, corruption, ambiguous
  selections, rejection of non-range downloads, resampling, and unknown labels.

The raw ImageCHD annotations contain **33,538 voxels with ID 13 in case 1122**
and **565 voxels with ID 12 in case 1148**. The publisher documents only seven
anatomy IDs. The first strict preparation attempt stopped on this mismatch.
The successful timing run used `--unknown-labels preserve`; both extra IDs
remain in the prepared masks and are recorded as undocumented. This does not
establish their anatomical meaning. Select a handling policy before using
these outputs with the original seven-class training lab.

The 2 mm ImageCAS variant is substantially smaller but can lose fine coronary
detail. Its binary foreground survived in every case. Native-resolution raw
files are retained separately; these results are not equivalent to the
native-resolution coronary benchmark.

## Temporary Artifacts

- Raw downloads and transfer reports:
  `/tmp/miagent-lab-prep-benchmark/raw/{ImageCAS,ImageCHD}/`
- Validated prepared cases and preparation reports:
  `/tmp/miagent-lab-prep-benchmark/validated-prepared/{ImageCAS_lab,ImageCHD_lab}/`
- `/tmp/miagent-lab-prep-benchmark/prepared/` contains the initial test output,
  including the intentionally stopped strict ImageCHD run; use the validated
  directory above for complete outputs.

Existing `/home/ubuntu/ai/MIAgent/data` files were not changed.
