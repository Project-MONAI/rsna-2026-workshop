#!/usr/bin/env python3
"""Verify the local container runtime has the expected GPU imaging stack."""

from __future__ import annotations

import importlib.util
import json
import shutil
import subprocess
import sys
from importlib.metadata import version

import mlflow
import monai
import nibabel
import pydicom
import torch
from torch.utils.tensorboard import SummaryWriter


def main() -> int:
    smi = subprocess.run(["nvidia-smi", "--query-gpu=name,driver_version,memory.total", "--format=csv,noheader"], capture_output=True, text=True)
    nnunet = {
        "distribution": "nnunetv2",
        "version": version("nnunetv2"),
        "python_import": "nnunetv2",
        "python_import_available": importlib.util.find_spec("nnunetv2") is not None,
        "commands": {
            name: shutil.which(name)
            for name in (
                "nnUNetv2_plan_and_preprocess",
                "nnUNetv2_train",
                "nnUNetv2_predict",
            )
        },
        "note": "Use import nnunetv2; import nnunet is the obsolete v1 namespace.",
    }
    payload = {
        "python": sys.version.split()[0],
        "torch": torch.__version__,
        "torch_cuda": torch.version.cuda,
        "cuda_available": torch.cuda.is_available(),
        "device_count": torch.cuda.device_count(),
        "monai": monai.__version__,
        "mlflow": mlflow.__version__,
        "nibabel": nibabel.__version__,
        "pydicom": pydicom.__version__,
        "tensorboard": SummaryWriter.__module__,
        "nnunet": nnunet,
        "nvidia_smi": smi.stdout.strip(),
    }
    print(json.dumps(payload, indent=2))
    if (
        smi.returncode
        or not payload["cuda_available"]
        or payload["device_count"] < 1
        or not nnunet["python_import_available"]
        or any(path is None for path in nnunet["commands"].values())
    ):
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
