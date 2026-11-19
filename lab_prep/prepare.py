#!/usr/bin/env python3
"""Download fixed lab cases using HTTP ranges, then optionally resample."""

import argparse
from collections import OrderedDict
import hashlib
import io
import json
import math
from pathlib import Path
import re
import shutil
import struct
import time
from urllib.parse import quote
import zipfile

import requests


COHORTS = {
    "ImageCAS": {
        "slug": "xiaoweixumedicalai/imagecas", "archive": "1-200",
        "training": ["90", "91", "96", "97", "99"],
        "validation": ["92", "93", "94", "95", "98"],
        "labels": list(range(2)), "hu_offset": 0,
        "classes": {0: "background", 1: "coronary_artery"},
    },
    "ImageCHD": {
        "slug": "xiaoweixumedicalai/imagechd", "archive": "ImageCHD_dataset",
        "training": ["1135", "1139", "1145", "1147", "1170"],
        "validation": ["1122", "1138", "1140", "1143", "1148"],
        "labels": list(range(8)), "hu_offset": -1024,
        "classes": dict(enumerate(["background", "left_ventricle", "right_ventricle",
                                  "left_atrium", "right_atrium", "myocardium", "aorta",
                                  "pulmonary_artery"])),
    },
}


def write_json(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=2) + "\n")


class RangeArchive(io.RawIOBase):
    """Seek across split ZIP disks without downloading whole archive parts."""

    def __init__(self, slug, block_size=4 * 1024**2):
        self.session = requests.Session()
        self.slug = slug
        self.block_size = block_size
        self.urls = {}
        self.cache = OrderedDict()
        self.position = 0
        self.network_bytes = 0
        self.network_seconds = 0.0
        self.requests_count = 0
        files = []
        token = ""
        while True:
            response = self.session.get(
                f"https://www.kaggle.com/api/v1/datasets/list/{slug}",
                params={"pageSize": 100, "pageToken": token}, timeout=60,
            )
            response.raise_for_status()
            payload = response.json()
            files.extend(payload["datasetFiles"])
            token = payload.get("nextPageToken", "")
            if not token:
                break
        archive = next(c["archive"] for c in COHORTS.values() if c["slug"] == slug)
        disks = sorted(
            (f for f in files if re.fullmatch(re.escape(archive) + r"\.z\d+", f["name"])),
            key=lambda f: int(f["name"].rsplit(".z", 1)[1]),
        )
        last = next(f for f in files if f["name"] == archive + ".change2zip")
        self.parts = disks + [last]
        self.starts = []
        total = 0
        for part in self.parts:
            self.starts.append(total)
            total += part["totalBytes"]
        self.size = total

    def seekable(self):
        return True

    def readable(self):
        return True

    def tell(self):
        return self.position

    def seek(self, offset, whence=0):
        self.position = offset if whence == 0 else (self.position if whence == 1 else self.size) + offset
        if self.position < 0:
            raise ValueError("Negative seek")
        return self.position

    def fetch(self, disk, offset, length):
        if not length:
            return b""
        url = self.urls.get(disk)
        if url is None:
            name = quote(self.parts[disk]["name"], safe="")
            url = f"https://www.kaggle.com/api/v1/datasets/download/{self.slug}/{name}?raw=true"
        started = time.perf_counter()
        with self.session.get(
            url, headers={"Range": f"bytes={offset}-{offset + length - 1}",
                          "Accept-Encoding": "identity"},
            timeout=(30, 120), stream=True,
        ) as response:
            # Never fall back to silently downloading a multi-GB archive.
            if response.status_code != 206:
                raise RuntimeError(f"HTTP range unavailable for disk {disk}: status {response.status_code}")
            expected = f"bytes {offset}-{offset + length - 1}/{self.parts[disk]['totalBytes']}"
            if response.headers.get("Content-Range") != expected:
                raise RuntimeError("Unexpected Content-Range; source archive may have changed")
            data = response.content
            if len(data) != length:
                raise RuntimeError("Truncated range response")
            self.urls[disk] = response.url
        self.network_bytes += len(data)
        self.network_seconds += time.perf_counter() - started
        self.requests_count += 1
        return data

    def read(self, size=-1):
        size = min(self.size - self.position, size if size >= 0 else self.size)
        result = bytearray()
        while size > 0:
            disk = max(i for i, start in enumerate(self.starts) if start <= self.position)
            offset = self.position - self.starts[disk]
            block = offset // self.block_size
            key = (disk, block)
            if key not in self.cache:
                start = block * self.block_size
                length = min(self.block_size, self.parts[disk]["totalBytes"] - start)
                self.cache[key] = self.fetch(disk, start, length)
                if len(self.cache) > 4:
                    self.cache.popitem(last=False)
            self.cache.move_to_end(key)
            data = self.cache[key]
            start = offset % self.block_size
            take = min(size, len(data) - start)
            result.extend(data[start:start + take])
            self.position += take
            size -= take
        return bytes(result)

    def close(self):
        self.session.close()
        super().close()


class SplitZip(zipfile.ZipFile):
    """Use stdlib ZIP decoding/CRC validation with disk-relative offsets."""

    def _RealGetContents(self):
        remote = self.fp
        last = len(remote.parts) - 1
        length = min(65557, remote.parts[last]["totalBytes"])
        tail = remote.fetch(last, remote.parts[last]["totalBytes"] - length, length)
        index = tail.rfind(b"PK\x05\x06")
        if index < 0:
            raise zipfile.BadZipFile("Missing ZIP end record")
        end = struct.unpack("<4s4H2LH", tail[index:index + 22])
        _, disk, cd_disk, _, entries, cd_size, cd_offset, _ = end
        if disk != last or cd_disk >= len(remote.parts) or entries == 65535 or cd_offset == 0xffffffff or cd_size == 0xffffffff:
            raise zipfile.BadZipFile("Unsupported ZIP64 directory or unexpected disk count")
        directory_start = remote.starts[cd_disk] + cd_offset
        remote.seek(directory_start)
        central = remote.read(cd_size)
        # Parse central records with zipfile, retaining each member's disk number.
        synthetic = central + struct.pack("<4s4H2LH", b"PK\x05\x06", 0, 0, entries, entries, cd_size, 0, 0)
        self.fp = io.BytesIO(synthetic)
        try:
            super()._RealGetContents()
        finally:
            self.fp = remote
        self.start_dir = directory_start
        for info in self.filelist:
            info.header_offset += remote.starts[info.volume]
        end_offset = directory_start
        for info in sorted(self.filelist, key=lambda x: x.header_offset, reverse=True):
            info._end_offset = end_offset
            end_offset = info.header_offset


def select_members(infos, case):
    matches = {"image": [], "label": []}
    for info in infos:
        name = info.filename.replace("\\", "/")
        if not re.search(r"\.nii(?:\.gz)?$", name, re.I):
            continue
        stem = re.sub(r"\.nii(?:\.gz)?$", "", name.rsplit("/", 1)[-1], flags=re.I)
        # ImageCAS: 90.img.nii.gz / 90.label.nii.gz; ImageCHD: image/1122.nii.gz.
        if not re.search(r"(?<!\d)" + re.escape(case) + r"(?!\d)", stem):
            continue
        kind = "label" if re.search(r"label|mask|seg", name, re.I) else "image"
        matches[kind].append(info)
    if any(len(values) != 1 for values in matches.values()):
        raise RuntimeError(f"Case {case}: expected one image and label; found "
                           + str({k: [i.filename for i in v] for k, v in matches.items()}))
    return {k: v[0] for k, v in matches.items()}


def download(dataset, output, list_only=False):
    cohort = COHORTS[dataset]
    started = time.perf_counter()
    with RangeArchive(cohort["slug"]) as remote, SplitZip(remote) as archive:
        chosen = {case: select_members(archive.infolist(), case)
                  for case in cohort["training"] + cohort["validation"]}
        if list_only:
            print(json.dumps({case: {k: v.filename for k, v in pair.items()} for case, pair in chosen.items()}, indent=2))
            return
        source_files = []
        for case, pair in chosen.items():
            for kind, info in pair.items():
                suffix = ".nii.gz" if info.filename.endswith(".gz") else ".nii"
                path = output / dataset / "cases" / case / (kind + suffix)
                if path.exists():
                    raise FileExistsError(f"Use an empty output directory: {path}")
                path.parent.mkdir(parents=True, exist_ok=True)
                temporary = path.with_name(path.name + ".part")
                with archive.open(info) as source, temporary.open("wb") as target:
                    shutil.copyfileobj(source, target, length=1024**2)
                temporary.rename(path)
                source_files.append({"case": case, "kind": kind, "member": info.filename,
                                     "crc32": f"{info.CRC:08x}", "bytes": info.file_size})
            print(f"Downloaded {dataset} case {case}", flush=True)
        seconds = time.perf_counter() - started
        report = {"dataset": dataset, "source": cohort["slug"], "cases": len(chosen),
                  "archive_total_bytes": remote.size, "downloaded_bytes": remote.network_bytes,
                  "range_requests": remote.requests_count, "network_seconds": remote.network_seconds,
                  "archive_parts": [{"name": p["name"], "bytes": p["totalBytes"]} for p in remote.parts],
                  "download_and_extract_seconds": seconds,
                  "network_mbps": remote.network_bytes * 8 / remote.network_seconds / 1e6,
                  "effective_mbps": remote.network_bytes * 8 / seconds / 1e6,
                  "measurement_note": "Range payload bytes only; listing/HTTP headers excluded. Network seconds include request latency.",
                  "files": source_files}
        write_json(output / dataset / "download_report.json", report)
        print(json.dumps({k: v for k, v in report.items() if k != "files"}, indent=2), flush=True)


def prepare(dataset, raw, output, spacing, unknown_labels="background"):
    import nibabel as nib
    from nibabel.processing import resample_from_to, resample_to_output
    import numpy as np

    cohort = COHORTS[dataset]
    started = time.perf_counter()
    root = output / (dataset + "_lab")
    if root.exists():
        raise FileExistsError(f"Use an empty output directory: {root}")
    records = []
    checksums = []
    undocumented = set()
    for case in cohort["training"] + cohort["validation"]:
        case_started = time.perf_counter()
        source = raw / dataset / "cases" / case
        images = list(source.glob("image.nii*"))
        labels = list(source.glob("label.nii*"))
        if len(images) != 1 or len(labels) != 1:
            raise ValueError(f"Missing or ambiguous image/label pair: {source}")
        image, label = nib.load(images[0]), nib.load(labels[0])
        if image.ndim != 3 or image.shape != label.shape or not np.allclose(image.affine, label.affine, atol=1e-4):
            raise ValueError(f"Image/label geometry mismatch: {case}")
        source_shape = list(image.shape)
        source_spacing = [float(x) for x in image.header.get_zooms()]
        label_values = np.asanyarray(label.dataobj)
        original_labels = np.unique(label_values)
        if not np.isfinite(original_labels).all() or not np.equal(original_labels, np.rint(original_labels)).all():
            raise ValueError(f"Non-integer or non-finite labels in {case}")
        if original_labels.min() < 0 or original_labels.max() > 255:
            raise ValueError(f"Label IDs outside uint8 range in {case}")
        unexpected = set(original_labels) - set(cohort["labels"])
        unexpected_counts = {int(v): int(np.count_nonzero(label_values == v)) for v in unexpected}
        if unexpected:
            if unknown_labels == "error":
                raise ValueError(f"Unexpected label IDs in {case}: {sorted(unexpected)}. "
                                 "Choose --unknown-labels preserve or background explicitly.")
            if unknown_labels == "background":
                label_values = np.array(label_values, copy=True)
                label_values[np.isin(label_values, list(unexpected))] = 0
                label = nib.Nifti1Image(label_values, label.affine)
            else:
                undocumented.update(int(v) for v in unexpected)
            print(f"{dataset} case {case}: undocumented labels {unexpected_counts}; policy={unknown_labels}", flush=True)
        del label_values
        # Float CT interpolation avoids quantization; labels retain integer IDs.
        voxels = image.get_fdata(dtype=np.float32)
        if not np.isfinite(voxels).all():
            raise ValueError(f"Non-finite CT values: {case}")
        image = nib.Nifti1Image(voxels, image.affine)
        del voxels
        image = resample_to_output(image, voxel_sizes=(spacing,) * 3, order=1, mode="nearest")
        label = resample_from_to(label, image, order=0, mode="constant", cval=0)
        label = nib.Nifti1Image(np.asarray(label.dataobj, dtype=np.uint8), image.affine)
        if not set(np.unique(np.asanyarray(label.dataobj))).issubset(set(original_labels) | {0}):
            raise ValueError(f"Resampling introduced label IDs: {case}")
        for kind, volume in (("image", image), ("label", label)):
            target = root / "cases" / case / (kind + ".nii.gz")
            target.parent.mkdir(parents=True, exist_ok=True)
            nib.save(volume, target)
            saved = nib.load(target)
            if saved.shape != image.shape or not np.allclose(saved.affine, image.affine):
                raise ValueError(f"Saved geometry mismatch: {target}")
            with target.open("rb") as stream:
                hasher = hashlib.sha256()
                for chunk in iter(lambda: stream.read(1024**2), b""):
                    hasher.update(chunk)
                digest = hasher.hexdigest()
            checksums.append(f"{digest}  {target.relative_to(root)}")
        records.append({"case": case, "shape": list(image.shape),
                        "source_shape": source_shape, "source_spacing_mm": source_spacing,
                        "seconds": time.perf_counter() - case_started,
                        "original_labels": original_labels.tolist(),
                        "undocumented_source_labels": unexpected_counts,
                        "unknown_label_policy": unknown_labels,
                        "retained_labels": np.unique(np.asanyarray(label.dataobj)).tolist()})
        print(f"Prepared {dataset} case {case}: {records[-1]['seconds']:.2f}s", flush=True)
    split = {group: [{"case_id": case, "image": f"cases/{case}/image.nii.gz",
                       "label": f"cases/{case}/label.nii.gz"} for case in cohort[group]]
             for group in ("training", "validation")}
    write_json(root / "split.json", {"dataset": dataset + "_lab", **split, "test": []})
    write_json(root / "dataset.json", {"source": cohort["slug"], "spacing_mm": [spacing] * 3,
               "orientation": "RAS", "hu_offset": cohort["hu_offset"],
               "hu_conversion": f"HU = stored_value + ({cohort['hu_offset']})",
               "labels": cohort["labels"] + sorted(undocumented), "split_file": "split.json",
               "undocumented_labels": sorted(undocumented), "unknown_label_policy": unknown_labels,
               "note": "Resampled workshop variant; ImageCAS differs from the native-resolution lab."})
    # JSON is valid YAML, avoiding an extra YAML dependency for the data contract.
    write_json(root / "dataset.yaml", {
        "schema_version": 1,
        "dataset": {"name": dataset + "_lab", "root": "/data/" + dataset + "_lab",
                    "modality": "CT", "source_dataset": dataset, "split_file": "split.json"},
        "image": {"file_format": "nifti", "physical_units": "HU",
                  "stored_units": "hounsfield_units" if cohort["hu_offset"] == 0 else "shifted_hounsfield_units",
                  "physical_conversion": {"operation": "affine", "scale": 1.0,
                                          "offset": cohort["hu_offset"],
                                          "equation": f"HU = stored_value + ({cohort['hu_offset']})"},
                  "recommended_windows_hu": {"broad": [-300, 1200], "cardiac_soft_tissue": [-100, 500]}},
        "label": {"background": 0, "foreground": cohort["labels"][1:] + sorted(undocumented),
                  "classes": {**cohort["classes"], **{v: f"undocumented_{v}" for v in undocumented}},
                  "undocumented_ids": sorted(undocumented), "unknown_label_policy": unknown_labels,
                  "file_format": "nifti",
                  "task": "binary_segmentation" if dataset == "ImageCAS" else "mutually_exclusive_multiclass"},
        "geometry": {"orientation": "RAS", "spacing_mm": [spacing] * 3,
                     "image_interpolation": "linear", "label_interpolation": "nearest"},
        "evaluation": {"metric": "mean_foreground_dice", "labels": cohort["labels"][1:],
                       "excluded_undocumented_ids": sorted(undocumented),
                       "aggregation": "mean_per_class_then_mean_across_validation_cases"},
    })
    (root / "checksums.sha256").write_text("\n".join(checksums) + "\n")
    report = {"dataset": dataset, "cases": records, "spacing_mm": spacing,
              "preprocessing_seconds": time.perf_counter() - started,
              "output_bytes": sum(p.stat().st_size for p in root.rglob("*.nii.gz"))}
    write_json(root / "preprocessing_report.json", report)
    print(f"{dataset} preparation: {report['preprocessing_seconds']:.2f}s", flush=True)


def main():
    folder = Path(__file__).resolve().parent
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("stage", choices=["list", "download", "resample", "all"])
    parser.add_argument("--dataset", choices=["ImageCAS", "ImageCHD", "both"], default="both")
    parser.add_argument("--raw-dir", type=Path, default=folder / "raw")
    parser.add_argument("--output-dir", type=Path, default=folder / "prepared")
    parser.add_argument("--spacing-mm", type=float, default=2.0)
    parser.add_argument("--unknown-labels", choices=["error", "preserve", "background"], default="background",
                        help="Policy for source annotation IDs outside the published label contract.")
    args = parser.parse_args()
    if not math.isfinite(args.spacing_mm) or args.spacing_mm <= 0:
        parser.error("--spacing-mm must be positive")
    for dataset in COHORTS if args.dataset == "both" else [args.dataset]:
        if args.stage in ("list", "download", "all"):
            download(dataset, args.raw_dir, list_only=args.stage == "list")
        if args.stage in ("resample", "all"):
            prepare(dataset, args.raw_dir, args.output_dir, args.spacing_mm, args.unknown_labels)


if __name__ == "__main__":
    main()
