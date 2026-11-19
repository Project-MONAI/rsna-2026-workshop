from __future__ import annotations

import importlib.util
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


SKILL_ROOT = Path(__file__).resolve().parents[1]
SCRIPT = SKILL_ROOT / "scripts" / "run_synthseg.py"
TEMPLATE = SKILL_ROOT / "templates" / "synthseg_config.yaml"


def load_module():
    spec = importlib.util.spec_from_file_location("miagent_synthseg_helper", SCRIPT)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class ConfigContractTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.module = load_module()

    def test_committed_template_is_valid(self) -> None:
        config = self.module.load_yaml(TEMPLATE)
        self.module.validate_config_data(config)

    def test_synthesis_cannot_include_validation(self) -> None:
        config = self.module.load_yaml(TEMPLATE)
        config["data"]["synthesis_splits"] = ["train", "validation"]
        with self.assertRaisesRegex(self.module.ContractError, "exactly \\[train\\]"):
            self.module.validate_config_data(config)

    def test_effective_patches_must_match(self) -> None:
        config = self.module.load_yaml(TEMPLATE)
        config["training"]["batch_size"] = 2
        config["training"]["patches_per_image"] = 3
        config["training"]["effective_patches"] = 5
        with self.assertRaisesRegex(self.module.ContractError, "batch_size"):
            self.module.validate_config_data(config)

    def test_test_access_requires_explicit_flag(self) -> None:
        config = self.module.load_yaml(TEMPLATE)
        config["tracking"]["held_out_test_accessed"] = True
        with self.assertRaisesRegex(self.module.ContractError, "explicit"):
            self.module.validate_config_data(config)
        self.module.validate_config_data(config, allow_held_out_test=True)


class LabelPreparationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        try:
            import nibabel  # noqa: F401
            import numpy  # noqa: F401
            import yaml  # noqa: F401
        except ImportError as exc:
            raise unittest.SkipTest(f"label preparation dependencies unavailable: {exc}")

    def write_case(self, root: Path, case_id: str) -> dict[str, object]:
        import nibabel as nib
        import numpy as np

        case_dir = root / case_id
        case_dir.mkdir()
        affine = np.diag([0.5, 0.5, 2.5, 1.0])
        image = np.full((6, 6, 4), 40.0, dtype=np.float32)
        brain = np.zeros_like(image, dtype=np.uint8)
        brain[1:5, 1:5, 1:3] = 1
        target = np.zeros_like(brain)
        target[2:4, 2:4, 1:2] = 1
        paths: dict[str, str] = {}
        for name, array in (("image", image), ("brain", brain), ("target", target)):
            path = case_dir / f"{name}.nii.gz"
            nib.save(nib.Nifti1Image(array, affine), str(path))
            paths[name] = str(path.relative_to(root))
        return {
            "case_id": case_id,
            "image": paths["image"],
            "sources": {"anatomy": paths["brain"], "target": paths["target"]},
        }

    def test_default_preparation_emits_train_only_and_resolves_overlap(self) -> None:
        import nibabel as nib
        import numpy as np
        import yaml

        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            train_case = self.write_case(root, "train_case")
            train_case["split"] = "train"
            val_case = self.write_case(root, "val_case")
            val_case["split"] = "validation"
            manifest = root / "manifest.yaml"
            manifest.write_text(yaml.safe_dump({"schema_version": 1, "cases": [train_case, val_case]}))
            output = root / "prepared"
            completed = subprocess.run(
                [
                    sys.executable,
                    str(SCRIPT),
                    "prepare-labels",
                    "--config",
                    str(TEMPLATE),
                    "--manifest",
                    str(manifest),
                    "--output-dir",
                    str(output),
                ],
                capture_output=True,
                text=True,
            )
            self.assertEqual(completed.returncode, 0, completed.stderr)
            self.assertTrue((output / "train_case.nii.gz").is_file())
            self.assertFalse((output / "val_case.nii.gz").exists())
            labels = np.asarray(nib.load(str(output / "train_case.nii.gz")).dataobj)
            self.assertEqual(set(np.unique(labels).tolist()), {0, 1, 2})
            self.assertEqual(int(labels[2, 2, 1]), 2)
            evidence = json.loads((output / "prepared_manifest.json").read_text())
            self.assertEqual(evidence["selected_splits"], ["train"])
            self.assertEqual([case["case_id"] for case in evidence["cases"]], ["train_case"])

    def test_validation_preparation_needs_explicit_evaluation_flag(self) -> None:
        import yaml

        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            case = self.write_case(root, "val_case")
            case["split"] = "validation"
            manifest = root / "manifest.yaml"
            manifest.write_text(yaml.safe_dump({"schema_version": 1, "cases": [case]}))
            completed = subprocess.run(
                [
                    sys.executable,
                    str(SCRIPT),
                    "prepare-labels",
                    "--config",
                    str(TEMPLATE),
                    "--manifest",
                    str(manifest),
                    "--output-dir",
                    str(root / "prepared"),
                    "--include-split",
                    "validation",
                ],
                capture_output=True,
                text=True,
            )
            self.assertEqual(completed.returncode, 2)
            self.assertIn("--allow-evaluation-splits", completed.stderr)


if __name__ == "__main__":
    unittest.main()
