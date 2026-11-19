"""Offline checks for split offsets, CRCs, and image/label resampling."""
import io
import json
from pathlib import Path
import struct
import tempfile
import unittest
from unittest.mock import MagicMock, patch
import zipfile

import nibabel as nib
import numpy as np

from prepare import COHORTS, RangeArchive, SplitZip, prepare, select_members


class LocalRanges(RangeArchive):
    def __init__(self, parts):
        from collections import OrderedDict
        self.data = parts
        self.parts = [{"totalBytes": len(p)} for p in parts]
        self.starts = [0, len(parts[0])]
        self.size = sum(map(len, parts))
        self.block_size = 64
        self.cache = OrderedDict()
        self.position = 0

    def fetch(self, disk, offset, length):
        return self.data[disk][offset:offset + length]

    def close(self):
        io.RawIOBase.close(self)


def split_fixture(corrupt=False):
    stream = io.BytesIO()
    payload = bytes(range(256)) * 10
    with zipfile.ZipFile(stream, "w", compression=zipfile.ZIP_STORED) as archive:
        archive.writestr("1-200/90.img.nii.gz", payload)
        archive.writestr("1-200/90.label.nii.gz", b"labels")
    blob = bytearray(stream.getvalue())
    with zipfile.ZipFile(io.BytesIO(blob)) as archive:
        infos = archive.infolist()
        central = archive.start_dir
    boundary = 128
    cursor = central
    for info in infos:
        volume = int(info.header_offset >= boundary)
        struct.pack_into("<H", blob, cursor + 34, volume)
        struct.pack_into("<L", blob, cursor + 42, info.header_offset - boundary * volume)
        cursor += 46 + len(info.filename.encode()) + len(info.extra) + len(info.comment)
    end = blob.rfind(b"PK\x05\x06")
    struct.pack_into("<HH", blob, end + 4, 1, 1)
    struct.pack_into("<L", blob, end + 16, central - boundary)
    if corrupt:
        blob[100] ^= 1
    return LocalRanges([bytes(blob[:boundary]), bytes(blob[boundary:])]), payload


class PreparationTests(unittest.TestCase):
    def test_member_crosses_split_boundary(self):
        remote, payload = split_fixture()
        with SplitZip(remote) as archive:
            selected = select_members(archive.infolist(), "90")
            self.assertEqual(archive.read(selected["image"]), payload)
            self.assertEqual(archive.read(selected["label"]), b"labels")

    def test_corruption_rejected(self):
        remote, _ = split_fixture(corrupt=True)
        with SplitZip(remote) as archive:
            with self.assertRaises(zipfile.BadZipFile):
                archive.read("1-200/90.img.nii.gz")

    def test_ambiguous_case_rejected(self):
        with self.assertRaises(RuntimeError):
            select_members([zipfile.ZipInfo("90.img.nii.gz")], "90")

    def test_range_fallback_rejected_before_reading_body(self):
        remote, _ = split_fixture()
        remote.urls = {0: "https://example.invalid/archive"}
        remote.session = MagicMock()
        response = remote.session.get.return_value.__enter__.return_value
        response.status_code = 200
        with self.assertRaisesRegex(RuntimeError, "HTTP range unavailable"):
            RangeArchive.fetch(remote, 0, 0, 4)
        remote.session.get.assert_called_once()

    def test_resampling_grid_labels_and_intensity(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            cohort = {**COHORTS["ImageCHD"], "training": ["1122"], "validation": []}
            case = root / "raw/ImageCHD/cases/1122"
            case.mkdir(parents=True)
            affine = np.diag([-1.0, 1.0, 3.0, 1.0])
            nib.save(nib.Nifti1Image(np.full((8, 8, 8), 1100, dtype=np.int16), affine), case / "image.nii.gz")
            label = np.zeros((8, 8, 8), dtype=np.uint8)
            label[2:6, 2:6, 2:6] = 7
            nib.save(nib.Nifti1Image(label, affine), case / "label.nii.gz")
            with patch.dict(COHORTS, {"ImageCHD": cohort}):
                prepare("ImageCHD", root / "raw", root / "output", 2)
            image = nib.load(root / "output/ImageCHD_lab/cases/1122/image.nii.gz")
            label = nib.load(root / "output/ImageCHD_lab/cases/1122/label.nii.gz")
            self.assertEqual(nib.aff2axcodes(image.affine), ("R", "A", "S"))
            np.testing.assert_allclose(image.header.get_zooms(), [2, 2, 2])
            np.testing.assert_allclose(image.affine, label.affine)
            np.testing.assert_allclose(image.get_fdata(), 1100)
            self.assertEqual(set(np.unique(label.get_fdata())), {0, 7})
            self.assertEqual(image.shape, label.shape)
            self.assertTrue((root / "output/ImageCHD_lab/dataset.yaml").exists())

    def test_undocumented_label_policy_overrides(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            cohort = {**COHORTS["ImageCHD"], "training": ["1122"], "validation": []}
            case = root / "raw/ImageCHD/cases/1122"
            case.mkdir(parents=True)
            affine = np.eye(4)
            nib.save(nib.Nifti1Image(np.zeros((4, 4, 4), dtype=np.int16), affine), case / "image.nii.gz")
            nib.save(nib.Nifti1Image(np.full((4, 4, 4), 13, dtype=np.uint8), affine), case / "label.nii.gz")
            with patch.dict(COHORTS, {"ImageCHD": cohort}):
                with self.assertRaisesRegex(ValueError, "Unexpected label IDs"):
                    prepare("ImageCHD", root / "raw", root / "strict", 2, "error")
                prepare("ImageCHD", root / "raw", root / "preserved", 2, "preserve")
                prepare("ImageCHD", root / "raw", root / "background", 2, "background")
            for name, expected in [("preserved", {0, 13}), ("background", {0})]:
                label = nib.load(root / name / "ImageCHD_lab/cases/1122/label.nii.gz")
                self.assertEqual(set(np.unique(label.get_fdata())), expected)
            contract = json.loads((root / "preserved/ImageCHD_lab/dataset.yaml").read_text())
            self.assertIn(13, contract["label"]["foreground"])
            self.assertIn(13, contract["evaluation"]["excluded_undocumented_ids"])

    def test_default_clears_ids_12_and_13_but_preserves_known_labels(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            cohort = {**COHORTS["ImageCHD"], "training": ["1122"], "validation": []}
            case = root / "raw/ImageCHD/cases/1122"
            case.mkdir(parents=True)
            affine = np.diag([2.0, 2.0, 2.0, 1.0])
            values = np.zeros((4, 4, 4), dtype=np.uint8)
            values[0] = 12
            values[1] = 13
            values[2] = 7
            nib.save(nib.Nifti1Image(np.zeros(values.shape, dtype=np.int16), affine), case / "image.nii.gz")
            nib.save(nib.Nifti1Image(values, affine), case / "label.nii.gz")
            with patch.dict(COHORTS, {"ImageCHD": cohort}):
                prepare("ImageCHD", root / "raw", root / "output", 2)
            folder = root / "output/ImageCHD_lab"
            label = nib.load(folder / "cases/1122/label.nii.gz").get_fdata()
            expected = values.copy()
            expected[np.isin(expected, [12, 13])] = 0
            np.testing.assert_array_equal(label, expected)
            contract = json.loads((folder / "dataset.yaml").read_text())
            self.assertEqual(contract['label']['foreground'], [1, 2, 3, 4, 5, 6, 7])
            self.assertEqual(contract['label']['unknown_label_policy'], 'background')
            report = json.loads((folder / "preprocessing_report.json").read_text())
            self.assertEqual(report['cases'][0]['undocumented_source_labels'], {'12': 16, '13': 16})


if __name__ == "__main__":
    unittest.main()
