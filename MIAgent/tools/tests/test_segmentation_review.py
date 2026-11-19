"""Regression checks for colocated segmentation review artifacts."""

from __future__ import annotations

import gzip
import hashlib
import json
import os
import struct
import sys
import tempfile
import unittest
from pathlib import Path

TOOLS = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(TOOLS))

from segmentation_difference import read_nifti_uint8  # noqa: E402
from segmentation_review import generate_manifest_reviews  # noqa: E402


def _write_uint8_nifti(path: Path, voxels: bytes) -> None:
    raw = bytearray(352 + len(voxels))
    struct.pack_into("<I", raw, 0, 348)
    struct.pack_into("<8h", raw, 40, 3, 2, 2, 2, 1, 1, 1, 1)
    struct.pack_into("<h", raw, 70, 2)
    struct.pack_into("<h", raw, 72, 8)
    struct.pack_into("<8f", raw, 76, 1, 1, 1, 1, 1, 1, 1, 1)
    struct.pack_into("<f", raw, 108, 352)
    raw[344:348] = b"n+1\0"
    raw[352:] = voxels
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(gzip.compress(bytes(raw), mtime=0))


class SegmentationReviewTest(unittest.TestCase):
    def test_manifest_generation_is_colocated_recorded_and_deterministic(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            tmp_path = Path(directory)
            run = tmp_path / "run"
            prediction = run / "selected_predictions" / "case1_prediction.nii.gz"
            image = tmp_path / "data" / "case1" / "image.nii.gz"
            truth = tmp_path / "data" / "case1" / "label.nii.gz"
            _write_uint8_nifti(prediction, bytes([0, 1, 2, 3, 0, 2, 1, 1]))
            _write_uint8_nifti(truth, bytes([0, 1, 0, 3, 2, 1, 0, 2]))
            image.parent.mkdir(parents=True, exist_ok=True)
            image.write_bytes(b"viewer only")
            manifest = run / "visualization_manifest.json"
            manifest.parent.mkdir(parents=True, exist_ok=True)
            manifest.write_text(json.dumps({"run": "exp009_train_3d_x3", "cases": [{
                "case_id": "case1",
                "image": os.path.relpath(image, run),
                "label": os.path.relpath(truth, run),
                "prediction": "selected_predictions/case1_prediction.nii.gz",
                "metrics": {"dice": 0.75, "dice_class_1": 0.8},
            }]}))

            payload, results = generate_manifest_reviews(manifest, hu_offset=1024, data_root=tmp_path / "data")
            error = prediction.parent / "case1_error.nii.gz"
            review = prediction.parent / "case1_review.html"
            self.assertEqual(results[0]["counts"], {
                "background": 1,
                "true_positive": 2,
                "false_positive": 2,
                "false_negative": 1,
                "wrong_class": 2,
            })
            self.assertEqual(read_nifti_uint8(error).voxels, bytes([0, 1, 2, 1, 3, 4, 2, 4]))
            self.assertEqual(set(read_nifti_uint8(error).voxels), {0, 1, 2, 3, 4})
            self.assertEqual(payload["cases"][0]["error"], "selected_predictions/case1_error.nii.gz")
            self.assertEqual(payload["cases"][0]["review"], "selected_predictions/case1_review.html")
            rendered = review.read_text()
            self.assertIn("Prediction</button>", rendered)
            self.assertIn("Ground truth</button>", rendered)
            self.assertIn("Difference</button>", rendered)
            self.assertNotIn("Hide overlay</button>", rendered)
            self.assertIn("Overlay opacity", rendered)
            self.assertIn("Single custom color", rendered)
            self.assertIn("const errorPalette", rendered)
            self.assertIn('mode === "difference"', rendered)
            self.assertIn("Experiment: exp009_train_3d_x3", rendered)
            self.assertIn("Mean Dice: 0.7500", rendered)
            self.assertIn("LV: 0.8000", rendered)
            self.assertIn("const huOffset = 1024.0", rendered)
            self.assertIn('"kind": "data", "path": "case1/image.nii.gz"', rendered)
            self.assertIn("data-files/${value.path}", rendered)

            before = (hashlib.sha256(error.read_bytes()).hexdigest(), hashlib.sha256(review.read_bytes()).hexdigest())
            generate_manifest_reviews(manifest, hu_offset=1024, data_root=tmp_path / "data")
            after = (hashlib.sha256(error.read_bytes()).hexdigest(), hashlib.sha256(review.read_bytes()).hexdigest())
            self.assertEqual(after, before)


if __name__ == "__main__":
    unittest.main()
