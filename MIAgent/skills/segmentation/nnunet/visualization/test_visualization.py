"""Small dependency-level tests for the reusable nnU-Net viewer."""

from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

import nibabel as nib
import numpy as np

from .training import parse_training_logs
from .viewer import visualize_run


def _epoch(epoch: int, train: float, val: float, dice: list[float]) -> str:
    return "\n".join(
        [
            f"2026-01-01 00:00:00: Epoch {epoch}",
            "2026-01-01 00:00:00: Current learning rate: 0.01",
            f"2026-01-01 00:00:00: train_loss {train}",
            f"2026-01-01 00:00:00: val_loss {val}",
            f"2026-01-01 00:00:00: Pseudo dice {dice}",
            "2026-01-01 00:00:00: Epoch time: 1.5 s",
        ]
    )


class VisualizationTest(unittest.TestCase):
    def test_resume_log_deduplication(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            first = root / "first.txt"
            resumed = root / "resumed.txt"
            first.write_text(_epoch(0, 1.0, 2.0, [0.1]) + "\n" + _epoch(1, 0.9, 1.9, [0.2]))
            resumed.write_text(_epoch(1, 0.8, 1.8, [0.3]) + "\n" + _epoch(2, 0.7, 1.7, [0.4]))
            records = parse_training_logs([first, resumed])
            self.assertEqual([item["epoch"] for item in records], [0, 1, 2])
            self.assertEqual(records[1]["train_loss"], 0.8)

    def test_numpy_scalar_pseudo_dice(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            log = Path(directory) / "training_log.txt"
            log.write_text(_epoch(0, 1.0, 2.0, [0.5]).replace("[0.5]", "[np.float32(0.6539)]"))
            records = parse_training_logs([log])
            self.assertAlmostEqual(records[0]["mean_pseudo_dice"], 0.6539)

    def test_integrated_viewer(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            image = np.zeros((8, 9, 10), dtype=np.float32)
            image[2:6, 2:7, 2:8] = 1
            mask = np.zeros_like(image, dtype=np.uint8)
            mask[3:6, 3:7, 3:8] = 1
            image_path, gt_path, pred_path = (root / name for name in ("image.nii.gz", "gt.nii.gz", "pred.nii.gz"))
            nib.save(nib.Nifti1Image(image, np.eye(4)), image_path)
            nib.save(nib.Nifti1Image(mask, np.eye(4)), gt_path)
            nib.save(nib.Nifti1Image(mask, np.eye(4)), pred_path)
            log = root / "training_log.txt"
            log.write_text(_epoch(0, 1.0, 2.0, [0.5]))
            manifest = {
                "provenance": {"checkpoint": "checkpoint_final.pth"},
                "viewer": {"title": "test viewer", "labels": {"1": "target"}},
                "training": {"logs": [str(log)], "class_names": ["target"]},
                "cases": [
                    {
                        "case_id": "case_001",
                        "inputs": {"image": str(image_path)},
                        "ground_truth": {"mask": str(gt_path)},
                        "prediction": {"mask": str(pred_path)},
                        "metrics": {"classes": {"1": {"Dice": 1.0, "HD95": 0.0}}},
                    }
                ],
            }
            manifest_path = root / "manifest.json"
            manifest_path.write_text(json.dumps(manifest))
            viewer_path = visualize_run(manifest_path, root / "result_viewer.html")
            document = viewer_path.read_text()
            self.assertIn("Training diagnostics", document)
            self.assertIn("case_001", document)
            self.assertTrue((root / "viewer_assets/training_curves.png").is_file())
            self.assertTrue((root / "viewer_assets/case_001.png").is_file())

    def test_multimodal_viewer_preserves_all_inputs(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            image = np.zeros((8, 9, 10), dtype=np.float32)
            mask = np.zeros_like(image, dtype=np.uint8)
            mask[2:5, 3:7, 4:8] = 1
            paths = {}
            for index, name in enumerate(("T2", "FLAIR", "T1", "T1c")):
                path = root / f"{name}.nii.gz"
                nib.save(nib.Nifti1Image(image + index, np.eye(4)), path)
                paths[name] = str(path)
            gt_path = root / "gt.nii.gz"
            pred_path = root / "pred.nii.gz"
            nib.save(nib.Nifti1Image(mask, np.eye(4)), gt_path)
            nib.save(nib.Nifti1Image(mask, np.eye(4)), pred_path)
            manifest = {
                "viewer": {"labels": {"1": "target"}},
                "cases": [{
                    "case_id": "case_multi",
                    "inputs": {"image": paths},
                    "ground_truth": {"mask": str(gt_path)},
                    "prediction": {"mask": str(pred_path)},
                }],
            }
            viewer_path = visualize_run(manifest, root / "result_viewer.html")
            document = viewer_path.read_text()
            for name in paths:
                self.assertIn(f"image ({name})", document)
            self.assertTrue((root / "viewer_assets/case_multi.png").is_file())


if __name__ == "__main__":
    unittest.main()
