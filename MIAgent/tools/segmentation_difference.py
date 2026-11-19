#!/usr/bin/env python3
"""Build a compact categorical NIfTI error map from uint8 label volumes."""

from __future__ import annotations

import argparse
import gzip
import json
import struct
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class NiftiUint8:
    raw: bytes
    endian: str
    shape: tuple[int, int, int]
    voxel_offset: int
    voxel_count: int

    @property
    def voxels(self) -> bytes:
        return self.raw[self.voxel_offset : self.voxel_offset + self.voxel_count]


def read_nifti_uint8(path: Path) -> NiftiUint8:
    raw = gzip.decompress(path.read_bytes()) if path.name.endswith(".gz") else path.read_bytes()
    if len(raw) < 352:
        raise ValueError(f"NIfTI file is too short: {path}")
    if struct.unpack("<I", raw[:4])[0] == 348:
        endian = "<"
    elif struct.unpack(">I", raw[:4])[0] == 348:
        endian = ">"
    else:
        raise ValueError(f"Not a NIfTI-1 single-file image: {path}")

    dims = struct.unpack(endian + "8h", raw[40:56])
    if dims[0] < 3 or any(value != 1 for value in dims[4 : dims[0] + 1]):
        raise ValueError(f"Expected one 3D label volume, found dimensions {dims}: {path}")
    shape = (int(dims[1]), int(dims[2]), int(dims[3]))
    datatype = struct.unpack(endian + "h", raw[70:72])[0]
    bits = struct.unpack(endian + "h", raw[72:74])[0]
    if datatype != 2 or bits != 8:
        raise ValueError(f"Only uint8 label NIfTI is supported, found datatype={datatype}, bitpix={bits}: {path}")
    voxel_offset = int(struct.unpack(endian + "f", raw[108:112])[0])
    voxel_count = shape[0] * shape[1] * shape[2]
    if voxel_offset < 352 or len(raw) < voxel_offset + voxel_count:
        raise ValueError(f"Invalid voxel offset or truncated voxel data: {path}")
    return NiftiUint8(raw, endian, shape, voxel_offset, voxel_count)


def assert_same_geometry(truth: NiftiUint8, prediction: NiftiUint8) -> None:
    if truth.shape != prediction.shape:
        raise ValueError(f"Shape mismatch: truth={truth.shape}, prediction={prediction.shape}")
    # pixdim, qform/sform codes and transforms must match before voxelwise comparison.
    for start, stop, name in ((76, 108, "spacing"), (252, 328, "spatial transform")):
        if truth.raw[start:stop] != prediction.raw[start:stop]:
            raise ValueError(f"NIfTI {name} mismatch between truth and prediction")


def build_error_map(truth: bytes, prediction: bytes) -> tuple[bytes, dict[str, int]]:
    output = bytearray(len(truth))
    counts = {"background": 0, "true_positive": 0, "false_positive": 0, "false_negative": 0, "wrong_class": 0}
    for index, (target, guess) in enumerate(zip(truth, prediction)):
        if target == guess:
            if target == 0:
                counts["background"] += 1
            else:
                output[index] = 1
                counts["true_positive"] += 1
        elif target == 0:
            output[index] = 2
            counts["false_positive"] += 1
        elif guess == 0:
            output[index] = 3
            counts["false_negative"] += 1
        else:
            output[index] = 4
            counts["wrong_class"] += 1
    return bytes(output), counts


def write_error_nifti(truth: NiftiUint8, voxels: bytes, output: Path) -> None:
    raw = bytearray(truth.raw[: truth.voxel_offset] + voxels)
    struct.pack_into(truth.endian + "f", raw, 124, 4.0)  # cal_max
    struct.pack_into(truth.endian + "f", raw, 128, 0.0)  # cal_min
    description = b"MIAgent errors: 1=TP 2=FP 3=FN 4=wrong-class"
    raw[148:228] = description.ljust(80, b"\0")
    output.parent.mkdir(parents=True, exist_ok=True)
    payload = gzip.compress(bytes(raw), compresslevel=6, mtime=0) if output.name.endswith(".gz") else bytes(raw)
    output.write_bytes(payload)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--truth", type=Path, required=True)
    parser.add_argument("--prediction", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()

    truth = read_nifti_uint8(args.truth)
    prediction = read_nifti_uint8(args.prediction)
    assert_same_geometry(truth, prediction)
    error_voxels, counts = build_error_map(truth.voxels, prediction.voxels)
    write_error_nifti(truth, error_voxels, args.output)
    print(json.dumps({"output": str(args.output.resolve()), "shape": truth.shape, "counts": counts}, indent=2))


if __name__ == "__main__":
    main()
