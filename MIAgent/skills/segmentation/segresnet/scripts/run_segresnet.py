#!/usr/bin/env python3
"""Configuration-driven MONAI SegResNet runner for multiclass NIfTI data."""

from __future__ import annotations

import argparse
import contextlib
import csv
import hashlib
import html
import inspect
import json
import math
import os
from collections import Counter
from pathlib import Path
import random
import sys
import time
from typing import Any

import nibabel as nib
import numpy as np
from scipy import ndimage
import torch
from torch.utils.data import DataLoader, Dataset, Subset, WeightedRandomSampler
import yaml

from monai.inferers import SlidingWindowInferer
from monai.losses import DiceCELoss
from monai.networks.nets import SegResNet
from monai.transforms import (
    ClassesToIndicesd,
    Compose,
    RandAffined,
    RandCropByLabelClassesd,
    RandFlipd,
)
from monai.utils import set_determinism


TOOLS = Path("/workspace/tools")
if TOOLS.is_dir():
    sys.path.insert(0, str(TOOLS))
try:
    import experiment_tracking as tracking
except ImportError:  # direct validation outside MIAgent
    tracking = None


def read_yaml(path: Path) -> dict[str, Any]:
    value = yaml.safe_load(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"YAML root must be a mapping: {path}")
    return value


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def seed_everything(seed: int) -> None:
    random.seed(seed)
    np.random.seed(seed)
    torch.manual_seed(seed)
    if torch.cuda.is_available():
        torch.cuda.manual_seed_all(seed)
    set_determinism(seed=seed, use_deterministic_algorithms=False)


def resolve_dataset(contract_path: Path) -> tuple[dict[str, Any], Path, dict[str, Any]]:
    contract = read_yaml(contract_path)
    for key in ("dataset", "image", "label", "geometry", "evaluation"):
        if not isinstance(contract.get(key), dict):
            raise ValueError(f"dataset contract missing mapping: {key}")
    root = Path(str(contract["dataset"]["root"]))
    split_path = Path(str(contract["dataset"]["split_file"]))
    if not split_path.is_absolute():
        split_path = root / split_path
    split = json.loads(split_path.read_text(encoding="utf-8"))
    return contract, root, split


def class_map(contract: dict[str, Any]) -> dict[int, str]:
    return {int(key): str(value) for key, value in contract["label"]["classes"].items()}


def conversion(contract: dict[str, Any]) -> tuple[float, float]:
    item = contract["image"]["physical_conversion"]
    if str(item.get("operation")) != "affine":
        raise ValueError("SegResNet runner currently requires affine physical_conversion")
    return float(item["scale"]), float(item["offset"])


def physical_image(stored: np.ndarray, contract: dict[str, Any]) -> np.ndarray:
    scale, offset = conversion(contract)
    return (stored.astype(np.float32) * scale + offset).astype(np.float32)


def load_case(root: Path, item: dict[str, Any], contract: dict[str, Any]) -> dict[str, Any]:
    image_path = Path(str(item["image"]))
    label_path = Path(str(item["label"]))
    if not image_path.is_absolute():
        image_path = root / image_path
    if not label_path.is_absolute():
        label_path = root / label_path
    image_nii = nib.load(str(image_path))
    label_nii = nib.load(str(label_path))
    stored = np.asarray(image_nii.dataobj, dtype=np.float32)
    label = np.asarray(label_nii.dataobj, dtype=np.int16)
    if stored.shape != label.shape:
        raise ValueError(f"{item['case_id']}: image/label shape mismatch")
    if not np.allclose(image_nii.affine, label_nii.affine):
        raise ValueError(f"{item['case_id']}: image/label affine mismatch")
    return {
        "case_id": str(item["case_id"]),
        "image_path": image_path,
        "label_path": label_path,
        "stored": stored,
        "image": physical_image(stored, contract),
        "label": label,
        "affine": np.asarray(image_nii.affine),
    }


def windows(contract: dict[str, Any], config: dict[str, Any]) -> list[tuple[float, float]]:
    known = contract["image"]["recommended_windows_hu"]
    selected = config["input"].get("windows", [])
    if not selected:
        raise ValueError("experiment input.windows must select at least one dataset window")
    result = []
    for name in selected:
        if name not in known:
            raise ValueError(f"unknown dataset window {name!r}; choose from {sorted(known)}")
        low, high = map(float, known[name])
        if not low < high:
            raise ValueError(f"invalid window {name}: {known[name]}")
        result.append((low, high))
    return result


def scale_window(image: np.ndarray, low: float, high: float) -> np.ndarray:
    return np.clip((image - low) / (high - low), 0.0, 1.0).astype(np.float32)


def validate_contract(contract_path: Path, config_path: Path) -> dict[str, Any]:
    contract, root, split = resolve_dataset(contract_path)
    config = read_yaml(config_path)
    foreground = [int(value) for value in contract["label"]["foreground"]]
    classes = class_map(contract)
    if set(foreground) - set(classes):
        raise ValueError("foreground contains labels absent from label.classes")
    if set(map(int, contract["evaluation"]["labels"])) != set(foreground):
        raise ValueError("evaluation.labels must match label.foreground")
    ratios = {int(key): float(value) for key, value in contract["label"]["recommended_sampling_ratios"].items()}
    if set(ratios) != set(classes):
        raise ValueError("recommended_sampling_ratios must cover every declared class")
    train, val = split.get("training", []), split.get("validation", [])
    train_ids = {str(item["case_id"]) for item in train}
    val_ids = {str(item["case_id"]) for item in val}
    if not train or not val or train_ids & val_ids:
        raise ValueError("split requires nonempty, nonoverlapping training and validation")
    expected_labels = set(classes)
    cases = [load_case(root, item, contract) for item in [*train, *val]]
    train_labels: set[int] = set()
    stored_min, stored_max = math.inf, -math.inf
    physical_min, physical_max = math.inf, -math.inf
    fg_low = fg_high = fg_total = 0
    low, high = map(float, contract["image"]["preflight_window_hu"])
    per_case = []
    for case in cases:
        observed = set(map(int, np.unique(case["label"])))
        unknown = observed - expected_labels
        if unknown:
            raise ValueError(f"{case['case_id']}: undeclared labels {sorted(unknown)}")
        if case["case_id"] in train_ids:
            train_labels.update(observed)
        foreground_mask = np.isin(case["label"], foreground)
        count = int(foreground_mask.sum())
        fg_total += count
        fg_low += int(np.count_nonzero(case["image"][foreground_mask] <= low))
        fg_high += int(np.count_nonzero(case["image"][foreground_mask] >= high))
        stored_min = min(stored_min, float(case["stored"].min()))
        stored_max = max(stored_max, float(case["stored"].max()))
        physical_min = min(physical_min, float(case["image"].min()))
        physical_max = max(physical_max, float(case["image"].max()))
        per_case.append({
            "case_id": case["case_id"], "shape": list(case["image"].shape),
            "labels": sorted(observed), "stored_min": float(case["stored"].min()),
            "stored_max": float(case["stored"].max()),
            "physical_min": float(case["image"].min()), "physical_max": float(case["image"].max()),
        })
    missing = set(foreground) - train_labels
    if missing:
        raise ValueError(f"training split lacks foreground classes {sorted(missing)}")
    if fg_total == 0:
        raise ValueError("no foreground voxels found")
    low_fraction, high_fraction = fg_low / fg_total, fg_high / fg_total
    limits = contract["image"]["preflight_limits"]
    if low_fraction > float(limits["maximum_foreground_fraction_clipped_low"]):
        raise ValueError(f"foreground low-window clipping {low_fraction:.4f} exceeds contract")
    if high_fraction > float(limits["maximum_foreground_fraction_clipped_high"]):
        raise ValueError(f"foreground high-window clipping {high_fraction:.4f} exceeds contract")
    selected_windows = windows(contract, config)
    report = {
        "status": "passed", "dataset_contract": str(contract_path),
        "dataset_contract_sha256": sha256(contract_path), "split_sha256": sha256(root / contract["dataset"]["split_file"]),
        "training_cases": sorted(train_ids), "validation_cases": sorted(val_ids),
        "classes": classes, "foreground": foreground,
        "physical_conversion": contract["image"]["physical_conversion"],
        "stored_range": [stored_min, stored_max], "physical_range": [physical_min, physical_max],
        "preflight_window": [low, high],
        "foreground_fraction_clipped_low": low_fraction,
        "foreground_fraction_clipped_high": high_fraction,
        "selected_windows": selected_windows, "cases": per_case,
    }
    return report


def architecture(config: dict[str, Any]) -> str:
    value = str(config["architecture"]).lower()
    aliases = {"segresnet2d": "segresnet2d", "2.5d": "segresnet2d", "2_5d_segresnet": "segresnet2d",
               "segresnet3d": "segresnet3d", "3d": "segresnet3d", "3d_segresnet": "segresnet3d"}
    if value not in aliases:
        raise ValueError("architecture must be segresnet2d or segresnet3d")
    return aliases[value]


def launcher_architecture(config: dict[str, Any]) -> str:
    return "2_5d_segresnet" if architecture(config) == "segresnet2d" else "3d_segresnet"


def patch_size(config: dict[str, Any]) -> tuple[int, int, int]:
    values = config["input"].get("patch_size", [256, 256, 32] if architecture(config) == "segresnet2d" else [128, 128, 64])
    result = tuple(int(value) for value in values)
    if len(result) != 3 or any(value < 16 for value in result):
        raise ValueError("input.patch_size must contain three integers >=16")
    return result


def expected_input_token(config: dict[str, Any]) -> str:
    count = len(config["input"]["windows"])
    coords = bool(config["input"].get("coordinates", False))
    if count == 1 and not coords:
        return "single"
    if count == 3 and not coords:
        return "windows3"
    if count == 3 and coords:
        return "windows3_coord3"
    raise ValueError("launcher supports one window or three windows, optionally with three coordinates")


def assert_launcher_tokens(args: argparse.Namespace, config: dict[str, Any]) -> None:
    expected_arch = launcher_architecture(config)
    supplied_arch = os.environ.get("CQ500_ARCHITECTURE", expected_arch)
    if supplied_arch != expected_arch:
        raise ValueError(f"CQ500_ARCHITECTURE={supplied_arch} does not match config {expected_arch}")
    expected_context = int(config["input"].get("context_slices", 7))
    if int(os.environ.get("CQ500_CONTEXT_SLICES", expected_context)) != expected_context:
        raise ValueError("CQ500_CONTEXT_SLICES does not match config")
    expected_patch = ",".join(map(str, patch_size(config)))
    if os.environ.get("CQ500_PATCH_SIZE", expected_patch) != expected_patch:
        raise ValueError("CQ500_PATCH_SIZE does not match config")
    if args.init_filters is not None and args.init_filters != int(config["model"]["init_filters"]):
        raise ValueError("--init-filters does not match config")
    if args.input_channels is not None and args.input_channels != expected_input_token(config):
        raise ValueError("--input-channels does not match config")


def volume_channels(image: np.ndarray, selected_windows: list[tuple[float, float]], coordinates: bool) -> np.ndarray:
    channels = [scale_window(image, *item) for item in selected_windows]
    if coordinates:
        h, w, d = image.shape
        x = np.linspace(-1, 1, h, dtype=np.float32)[:, None, None] * np.ones((1, w, d), np.float32)
        y = np.linspace(-1, 1, w, dtype=np.float32)[None, :, None] * np.ones((h, 1, d), np.float32)
        z = np.linspace(-1, 1, d, dtype=np.float32)[None, None, :] * np.ones((h, w, 1), np.float32)
        channels.extend([x, y, z])
    return np.stack(channels).astype(np.float32)


def slice_channels(image: np.ndarray, z: int, context: int, selected_windows: list[tuple[float, float]], coordinates: bool) -> np.ndarray:
    half = context // 2
    indices = np.clip(np.arange(z - half, z + half + 1), 0, image.shape[2] - 1)
    result = [scale_window(image[:, :, zi], *selected_windows[0]) for zi in indices]
    result.extend(scale_window(image[:, :, z], *item) for item in selected_windows[1:])
    if coordinates:
        h, w = image.shape[:2]
        x = np.linspace(-1, 1, h, dtype=np.float32)[:, None].repeat(w, 1)
        y = np.linspace(-1, 1, w, dtype=np.float32)[None, :].repeat(h, 0)
        zc = np.full((h, w), 2 * z / max(1, image.shape[2] - 1) - 1, np.float32)
        result.extend([x, y, zc])
    return np.stack(result).astype(np.float32)


class SliceDataset(Dataset):
    def __init__(self, cases: list[dict[str, Any]], config: dict[str, Any], selected_windows: list[tuple[float, float]], augment: bool):
        self.cases, self.config, self.windows = cases, config, selected_windows
        self.index = [(ci, z) for ci, case in enumerate(cases) for z in range(case["image"].shape[2])]
        counts: Counter[int] = Counter()
        for ci, z in self.index:
            counts.update(set(map(int, np.unique(cases[ci]["label"][:, :, z]))) - {0})
        self.weights = []
        for ci, z in self.index:
            present = set(map(int, np.unique(cases[ci]["label"][:, :, z]))) - {0}
            self.weights.append(0.05 + sum(1.0 / counts[value] for value in present))
        aug = config.get("augmentation", {})
        transforms = []
        if augment and float(aug.get("affine_probability", 0)) > 0:
            transforms.append(RandAffined(
                keys=["image", "label"], spatial_size=None, prob=float(aug["affine_probability"]),
                rotate_range=0.10, translate_range=(10, 10), scale_range=(0.08, 0.08),
                mode=("bilinear", "nearest"), padding_mode="zeros",
            ))
        if augment and float(aug.get("flip_probability", 0)) > 0:
            transforms.append(RandFlipd(keys=["image", "label"], prob=float(aug["flip_probability"]), spatial_axis=1))
        self.augment = Compose(transforms) if transforms else None

    def __len__(self) -> int:
        return len(self.index)

    def __getitem__(self, index: int) -> tuple[torch.Tensor, torch.Tensor]:
        ci, z = self.index[index]
        case = self.cases[ci]
        value = {
            "image": slice_channels(case["image"], z, int(self.config["input"]["context_slices"]), self.windows, bool(self.config["input"].get("coordinates", False))),
            "label": case["label"][:, :, z][None].astype(np.float32),
        }
        if self.augment:
            value = self.augment(value)
        return torch.as_tensor(value["image"], dtype=torch.float32), torch.as_tensor(value["label"], dtype=torch.long)


class PatchDataset(Dataset):
    def __init__(self, cases: list[dict[str, Any]], config: dict[str, Any], selected_windows: list[tuple[float, float]], contract: dict[str, Any], augment: bool):
        self.samples = int(config["training"]["samples_per_epoch"])
        indexer = ClassesToIndicesd(keys=["label"], num_classes=len(class_map(contract)), max_samples_per_class=100000)
        self.items = []
        for case in cases:
            item = {"image": torch.from_numpy(volume_channels(case["image"], selected_windows, bool(config["input"].get("coordinates", False)))),
                    "label": torch.from_numpy(case["label"][None].astype(np.int16))}
            self.items.append(indexer(item))
        ratios_map = {int(key): float(value) for key, value in contract["label"]["recommended_sampling_ratios"].items()}
        ratios = [ratios_map[index] for index in range(len(ratios_map))]
        transforms: list[Any] = [RandCropByLabelClassesd(
            keys=["image", "label"], label_key="label", spatial_size=patch_size(config), ratios=ratios,
            num_classes=len(ratios), num_samples=1, indices_key="label_cls_indices", allow_smaller=False,
        )]
        if augment and float(config.get("augmentation", {}).get("flip_probability", 0)) > 0:
            probability = float(config["augmentation"]["flip_probability"])
            transforms.extend([RandFlipd(keys=["image", "label"], prob=probability, spatial_axis=axis) for axis in (0, 1, 2)])
        self.transform = Compose(transforms)

    def __len__(self) -> int:
        return self.samples

    def __getitem__(self, index: int) -> tuple[torch.Tensor, torch.Tensor]:
        value = self.transform(self.items[index % len(self.items)])
        value = value[0] if isinstance(value, list) else value
        return torch.as_tensor(value["image"], dtype=torch.float32), torch.as_tensor(value["label"], dtype=torch.long)


def make_dataset(cases: list[dict[str, Any]], config: dict[str, Any], selected_windows: list[tuple[float, float]], contract: dict[str, Any], augment: bool) -> Dataset:
    if architecture(config) == "segresnet2d":
        return SliceDataset(cases, config, selected_windows, augment)
    return PatchDataset(cases, config, selected_windows, contract, augment)


def make_loader(dataset: Dataset, config: dict[str, Any], train: bool) -> DataLoader:
    values = config["training"]
    batch = int(values["batch_size"] if train else values.get("validation_batch_size", values["batch_size"]))
    workers = int(values.get("workers", 0)) if train else 0
    if train and architecture(config) == "segresnet2d":
        sampler = WeightedRandomSampler(dataset.weights, num_samples=int(values["samples_per_epoch"]), replacement=True)  # type: ignore[attr-defined]
        return DataLoader(dataset, batch_size=batch, sampler=sampler, num_workers=workers, persistent_workers=workers > 0, pin_memory=True)
    return DataLoader(dataset, batch_size=batch, shuffle=train, num_workers=workers, persistent_workers=workers > 0, pin_memory=True)


def make_model(config: dict[str, Any], selected_windows: list[tuple[float, float]], classes: int) -> SegResNet:
    coords = 3 if config["input"].get("coordinates", False) else 0
    if architecture(config) == "segresnet2d":
        channels = int(config["input"]["context_slices"]) + len(selected_windows) - 1 + coords
        dims = 2
    else:
        channels, dims = len(selected_windows) + coords, 3
    return SegResNet(
        spatial_dims=dims, in_channels=channels, out_channels=classes,
        init_filters=int(config["model"]["init_filters"]), dropout_prob=float(config["model"].get("dropout", 0.1)),
        blocks_down=(1, 2, 2, 4), blocks_up=(1, 1, 1),
    )


def autocast(config: dict[str, Any], device: torch.device):
    enabled = device.type == "cuda" and str(config["training"].get("precision", "bf16")).lower() == "bf16"
    return torch.autocast("cuda", dtype=torch.bfloat16) if enabled else contextlib.nullcontext()


def class_weights(cases: list[dict[str, Any]], classes: int, mode: str, device: torch.device) -> torch.Tensor | None:
    if mode == "none":
        return None
    if mode != "sqrt_inverse_frequency":
        raise ValueError("class_weighting must be none or sqrt_inverse_frequency")
    counts = np.zeros(classes, np.float64)
    for case in cases:
        counts += np.bincount(case["label"].ravel(), minlength=classes)
    result = np.sqrt(counts.sum() / np.maximum(counts, 1))
    result /= result.mean()
    result[0] *= 0.25
    return torch.tensor(result, dtype=torch.float32, device=device)


def dice_values(prediction: np.ndarray, truth: np.ndarray, labels: list[int]) -> list[float]:
    result = []
    for value in labels:
        pred, target = prediction == value, truth == value
        result.append(float((2 * np.count_nonzero(pred & target) + 1e-6) / (np.count_nonzero(pred) + np.count_nonzero(target) + 1e-6)))
    return result


def largest_components(prediction: np.ndarray, labels: list[int]) -> np.ndarray:
    result = np.zeros_like(prediction)
    structure = ndimage.generate_binary_structure(3, 2)
    for value in labels:
        components, count = ndimage.label(prediction == value, structure=structure)
        if count:
            sizes = np.bincount(components.ravel()); sizes[0] = 0
            result[components == sizes.argmax()] = value
    return result


@torch.inference_mode()
def predict(model: torch.nn.Module, case: dict[str, Any], config: dict[str, Any], selected_windows: list[tuple[float, float]], device: torch.device) -> np.ndarray:
    model.eval()
    if architecture(config) == "segresnet3d":
        inputs = torch.from_numpy(volume_channels(case["image"], selected_windows, bool(config["input"].get("coordinates", False))))[None]
        inferer = SlidingWindowInferer(
            roi_size=patch_size(config), sw_batch_size=int(config["training"].get("validation_batch_size", 2)),
            overlap=float(config.get("inference", {}).get("overlap", 0.5)), mode="gaussian",
            sw_device=device, device="cpu", cache_roi_weight_map=True,
        )
        with autocast(config, device):
            logits = inferer(inputs, model)[0]
        return logits.argmax(0).numpy().astype(np.uint8)
    context = int(config["input"]["context_slices"])
    batch_size = int(config["training"].get("validation_batch_size", 24))
    values = []
    for start in range(0, case["image"].shape[2], batch_size):
        stop = min(start + batch_size, case["image"].shape[2])
        batch = np.stack([slice_channels(case["image"], z, context, selected_windows, bool(config["input"].get("coordinates", False))) for z in range(start, stop)])
        with autocast(config, device):
            logits = model(torch.from_numpy(batch).to(device))
        values.append(logits.argmax(1).cpu().numpy().astype(np.uint8))
    return np.moveaxis(np.concatenate(values), 0, 2)


def run_root(args: argparse.Namespace) -> Path:
    value = args.output_dir or os.environ.get("MIAgent_RUN_DIR")
    if not value:
        raise ValueError("--output-dir or MIAgent_RUN_DIR is required")
    path = Path(value); path.mkdir(parents=True, exist_ok=True)
    return path


def viewer_offset(contract: dict[str, Any]) -> float:
    scale, offset = conversion(contract)
    if scale != 1.0:
        return 0.0
    return -offset


def publish(run: Path, contract: dict[str, Any], rows: list[dict[str, Any]], predictions: dict[str, np.ndarray]) -> tuple[Path, Path]:
    pred_dir = run / "predictions"; pred_dir.mkdir(parents=True, exist_ok=True)
    manifest_dir = run / "visualization_manifests"; manifest_dir.mkdir(parents=True, exist_ok=True)
    table_dir = run / "per_case_dice"; table_dir.mkdir(parents=True, exist_ok=True)
    manifest_cases = []
    for row in rows:
        case = row["case"]
        pred_path = pred_dir / f"{case['case_id']}_prediction.nii.gz"
        nib.save(nib.Nifti1Image(predictions[case["case_id"]].astype(np.uint8), case["affine"]), str(pred_path))
        manifest_cases.append({
            "case_id": case["case_id"], "image": str(case["image_path"]), "label": str(case["label_path"]),
            "prediction": str(pred_path), "metrics": {"dice": row["mean"], **{f"dice_class_{i+1}": value for i, value in enumerate(row["classes"])}},
        })
    csv_path = table_dir / "per_case_dice.csv"
    with csv_path.open("w", newline="", encoding="utf-8") as stream:
        writer = csv.writer(stream); writer.writerow(["case_id", "mean_dice", *[f"class_{i+1}" for i in range(len(rows[0]["classes"]))]])
        for row in rows:
            writer.writerow([row["case"]["case_id"], row["mean"], *row["classes"]])
    manifest = manifest_dir / "visualization_manifest.json"
    manifest.write_text(json.dumps({"run": run.name, "cases": manifest_cases}, indent=2) + "\n", encoding="utf-8")
    try:
        from segmentation_review import generate_manifest_reviews
        payload, reviews = generate_manifest_reviews(manifest, hu_offset=viewer_offset(contract))
        review_by_case = {str(item["case_id"]): Path(item["review"]) for item in reviews}
    except Exception as exc:
        payload, review_by_case = json.loads(manifest.read_text()), {}
        (run / "review_error.txt").write_text(str(exc) + "\n", encoding="utf-8")
    viewer_dir = run / "result_viewers"; viewer_dir.mkdir(parents=True, exist_ok=True)
    viewer = viewer_dir / "result_viewer.html"
    links = []
    for case in payload["cases"]:
        cid = str(case["case_id"])
        target = review_by_case.get(cid)
        href = os.path.relpath(target, viewer.parent) if target else os.path.relpath(Path(case["prediction"]), viewer.parent)
        links.append(f'<li><a href="{html.escape(href)}">Case {html.escape(cid)}</a> — Dice {float(case["metrics"]["dice"]):.4f}</li>')
    viewer.write_text("<!doctype html><meta charset='utf-8'><title>SegResNet results</title><style>body{font:16px system-ui;max-width:900px;margin:40px auto;background:#111827;color:#eee}a{color:#7dd3fc}li{margin:12px}</style><h1>SegResNet validation results</h1><ul>" + "".join(links) + "</ul>", encoding="utf-8")
    return manifest, viewer


def evaluate(model: torch.nn.Module, cases: list[dict[str, Any]], config: dict[str, Any], contract: dict[str, Any], selected_windows: list[tuple[float, float]], device: torch.device, save: bool, run: Path) -> dict[str, Any]:
    labels = [int(value) for value in contract["evaluation"]["labels"]]
    raw_predictions, lcc_predictions, raw_rows, lcc_rows = {}, {}, [], []
    for case in cases:
        raw = predict(model, case, config, selected_windows, device)
        lcc = largest_components(raw, labels)
        raw_values, lcc_values = dice_values(raw, case["label"], labels), dice_values(lcc, case["label"], labels)
        raw_predictions[case["case_id"]], lcc_predictions[case["case_id"]] = raw, lcc
        raw_rows.append({"case": case, "classes": raw_values, "mean": float(np.mean(raw_values))})
        lcc_rows.append({"case": case, "classes": lcc_values, "mean": float(np.mean(lcc_values))})
    raw_mean, lcc_mean = float(np.mean([row["mean"] for row in raw_rows])), float(np.mean([row["mean"] for row in lcc_rows]))
    use_lcc = bool(config.get("inference", {}).get("largest_component_per_class", True)) and lcc_mean > raw_mean
    rows, predictions = (lcc_rows, lcc_predictions) if use_lcc else (raw_rows, raw_predictions)
    result = {
        "dice": max(raw_mean, lcc_mean) if use_lcc else raw_mean, "dice_raw": raw_mean, "dice_lcc": lcc_mean,
        "postprocessing": "largest_component_per_class" if use_lcc else "none",
        "per_case": [{"case_id": row["case"]["case_id"], "mean": row["mean"], "classes": row["classes"]} for row in rows],
    }
    if save:
        manifest, viewer = publish(run, contract, rows, predictions)
        result.update({"manifest": str(manifest), "viewer": str(viewer)})
    return result


def load_splits(contract_path: Path) -> tuple[dict[str, Any], dict[str, Any], list[dict[str, Any]], list[dict[str, Any]]]:
    contract, root, split = resolve_dataset(contract_path)
    return contract, split, [load_case(root, item, contract) for item in split["training"]], [load_case(root, item, contract) for item in split["validation"]]


def profile(args: argparse.Namespace, config: dict[str, Any]) -> dict[str, Any]:
    assert_launcher_tokens(args, config)
    preflight = validate_contract(args.dataset, args.config)
    contract, split, train_cases, val_cases = load_splits(args.dataset)
    selected_windows = windows(contract, config)
    device = torch.device("cuda")
    dataset = make_dataset(train_cases, config, selected_windows, contract, augment=True)
    loader = make_loader(dataset, config, train=True)
    model = make_model(config, selected_windows, len(class_map(contract))).to(device)
    values = config["training"]
    loss = DiceCELoss(include_background=False, to_onehot_y=True, softmax=True)
    optimizer = torch.optim.AdamW(model.parameters(), lr=float(values["learning_rate"]))
    torch.cuda.reset_peak_memory_stats()
    image, label = next(iter(loader)); image, label = image.to(device), label.to(device)
    optimizer.zero_grad(set_to_none=True)
    with autocast(config, device):
        objective = loss(model(image), label)
    objective.backward(); optimizer.step()
    probe = evaluate(model, val_cases[:1], config, contract, selected_windows, device, False, run_root(args))
    peak = torch.cuda.max_memory_allocated() / 1024**2
    budget = int(os.environ.get("MIAgent_GPU_BUDGET_MB", "0") or 0)
    approved = budget > 0 and peak <= budget * 0.9
    selected = {
        "architecture": launcher_architecture(config), "context_slices": int(config["input"].get("context_slices", 7)),
        "init_filters": int(config["model"]["init_filters"]), "input_channels": expected_input_token(config),
        "patch": list(patch_size(config)), "batch_size": int(values["batch_size"]),
        "patches_per_image": float(values["samples_per_epoch"]) / len(train_cases), "effective_patches": int(values["batch_size"]),
        "cache_rate": 0.0, "source_case_count": len(train_cases),
    }
    report = {
        "approved": approved, "policy_version": "adaptive-headroom-v1", "measured_peak_mb": peak,
        "current_budget_mb": budget, "safety_reserve_mb": budget - peak, "selected": selected,
        "phases": {"real_step_loss": float(objective.detach().cpu()), "real_validation_probe_dice": probe["dice"]},
        "split_hash": preflight["split_sha256"], "dataset_contract_hash": preflight["dataset_contract_sha256"],
        "config_fingerprint": sha256(args.config),
    }
    baseline = run_root(args).parents[1]
    arch = selected["architecture"]
    suffix = f"_{arch}"
    if selected["context_slices"] != 7: suffix += f"_ctx{selected['context_slices']}"
    if arch == "3d_segresnet" and selected["init_filters"] != 16: suffix += f"_f{selected['init_filters']}"
    if selected["input_channels"] != "single": suffix += f"_{selected['input_channels']}"
    patch_token = ",".join(map(str, selected["patch"]))
    if patch_token != "128,128,32": suffix += f"_p{patch_token.replace(',', 'x')}"
    record = baseline / "gpu_optimization" / f"approved{suffix}.json"
    record.parent.mkdir(parents=True, exist_ok=True); record.write_text(json.dumps(report, indent=2) + "\n")
    (run_root(args) / "optimization_report.json").write_text(json.dumps(report, indent=2) + "\n")
    if not approved:
        raise RuntimeError(f"profile peak {peak:.0f} MiB is not approved under {budget} MiB budget")
    return report


def train(args: argparse.Namespace, config: dict[str, Any], smoke: bool = False) -> dict[str, Any]:
    assert_launcher_tokens(args, config)
    preflight = validate_contract(args.dataset, args.config)
    contract, split, train_cases, val_cases = load_splits(args.dataset)
    if smoke:
        val_cases = val_cases[:1]
    selected_windows = windows(contract, config)
    seed_everything(int(config.get("seed", 0)))
    device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
    dataset = make_dataset(train_cases, config, selected_windows, contract, augment=True)
    loader = make_loader(dataset, config, train=True)
    values = config["training"]
    epochs = 1 if smoke else int(values["epochs"])
    val_epochs = {1} if smoke else set(map(int, values["validation_epochs"]))
    samples = min(int(values["batch_size"]), len(dataset)) if smoke else int(values["samples_per_epoch"])
    if smoke:
        if architecture(config) == "segresnet2d":
            loader = DataLoader(dataset, batch_size=samples, sampler=WeightedRandomSampler(dataset.weights, samples, replacement=True), num_workers=0)  # type: ignore[attr-defined]
        else:
            loader = DataLoader(Subset(dataset, range(samples)), batch_size=min(samples, int(values["batch_size"])), shuffle=False, num_workers=0)
    steps_per_epoch = len(loader)
    model = make_model(config, selected_windows, len(class_map(contract))).to(device)
    weight = class_weights(train_cases, len(class_map(contract)), str(values.get("class_weighting", "none")), device)
    loss_fn = DiceCELoss(
        include_background=False, to_onehot_y=True, softmax=True, weight=weight,
        lambda_dice=float(values.get("dice_weight", 1)), lambda_ce=float(values.get("cross_entropy_weight", 0.5)),
    )
    optimizer = torch.optim.AdamW(model.parameters(), lr=float(values["learning_rate"]), weight_decay=float(values.get("weight_decay", 0.0001)))
    scheduler = torch.optim.lr_scheduler.CosineAnnealingLR(optimizer, T_max=epochs, eta_min=float(values["learning_rate"]) * 0.05)
    run = run_root(args); checkpoint_dir = run / "checkpoints"; checkpoint_dir.mkdir(parents=True, exist_ok=True)
    if tracking:
        tracking.record_parameters({
            "model": f"SegResNet-{architecture(config)}-f{config['model']['init_filters']}", "dataset_contract": str(args.dataset),
            "dataset_contract_hash": preflight["dataset_contract_sha256"], "split_hash": preflight["split_sha256"],
            "physical_conversion": json.dumps(contract["image"]["physical_conversion"]), "input_channels": expected_input_token(config),
            "windows": json.dumps(config["input"]["windows"]), "crop": ",".join(map(str, patch_size(config))),
            "context_slices": int(config["input"].get("context_slices", 7)), "batch_size": int(values["batch_size"]),
            "samples_per_epoch": samples, "steps_per_epoch": steps_per_epoch, "total_optimizer_steps": steps_per_epoch * epochs,
            "epochs": epochs, "validation_interval_epochs": ",".join(map(str, sorted(val_epochs))), "precision": values.get("precision", "bf16"),
            "learning_rate": float(values["learning_rate"]), "class_weighting": values.get("class_weighting", "none"),
        })
        tracking.record_tags({"task": "multiclass_segmentation", "model_family": "SegResNet", "run_kind": "smoke" if smoke else "training"})
        tracking.record_description(f"Configuration-driven SegResNet {'smoke' if smoke else 'training'} using {args.dataset}. Physical conversion is executed before windows. {steps_per_epoch} optimizer steps/epoch, {steps_per_epoch * epochs} total.")
    history, best = [], {"dice": -1.0, "epoch": 0, "checkpoint": None}
    started = time.perf_counter()
    for epoch in range(1, epochs + 1):
        model.train(); losses = []
        for image, label in loader:
            image, label = image.to(device, non_blocking=True), label.to(device, non_blocking=True)
            optimizer.zero_grad(set_to_none=True)
            with autocast(config, device):
                objective = loss_fn(model(image), label)
            objective.backward(); optimizer.step(); losses.append(float(objective.detach().cpu()))
        scheduler.step()
        row: dict[str, Any] = {"epoch": epoch, "training_loss": float(np.mean(losses)), "lr": optimizer.param_groups[0]["lr"]}
        if tracking: tracking.record_metrics({"training.loss": row["training_loss"], "training.learning_rate": row["lr"]}, step=epoch)
        if epoch in val_epochs:
            result = evaluate(model, val_cases, config, contract, selected_windows, device, False, run)
            row["validation"] = result
            if tracking:
                metrics = {"validation.dice": result["dice"]}
                for index, value in enumerate(np.mean([item["classes"] for item in result["per_case"]], axis=0), 1): metrics[f"validation.dice.class_{index}"] = float(value)
                tracking.record_metrics(metrics, step=epoch)
            if result["dice"] > best["dice"]:
                target = checkpoint_dir / "best.pt"
                torch.save({"model": model.state_dict(), "epoch": epoch, "dice": result["dice"], "config": config}, target)
                best = {"dice": result["dice"], "epoch": epoch, "checkpoint": str(target)}
        history.append(row); print(json.dumps(row), flush=True)
    if best["checkpoint"] is None:
        raise RuntimeError("no scheduled validation produced a checkpoint")
    state = torch.load(best["checkpoint"], map_location=device, weights_only=False); model.load_state_dict(state["model"])
    final = evaluate(model, val_cases, config, contract, selected_windows, device, True, run)
    output = {
        "status": "completed", "smoke": smoke, "architecture": architecture(config), "best": best,
        "final": final, "steps_per_epoch": steps_per_epoch, "total_optimizer_steps": steps_per_epoch * epochs,
        "wall_seconds": time.perf_counter() - started, "history": history, "preflight": preflight,
    }
    (run / "output.json").write_text(json.dumps(output, indent=2) + "\n", encoding="utf-8")
    return output


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=["preflight", "smoke", "profile", "train", "api"])
    parser.add_argument("--dataset", type=Path, required=False)
    parser.add_argument("--config", type=Path, required=False)
    parser.add_argument("--output-dir")
    parser.add_argument("--init-filters", type=int)
    parser.add_argument("--input-channels", choices=["single", "windows3", "windows3_coord3", "windows3_coordz"])
    args = parser.parse_args()
    if args.command == "api":
        print(json.dumps({"SegResNet": str(inspect.signature(SegResNet)), "RandCropByLabelClassesd": str(inspect.signature(RandCropByLabelClassesd))}, indent=2)); return
    if not args.dataset or not args.config:
        parser.error("--dataset and --config are required")
    config = read_yaml(args.config)
    if args.command == "preflight": result = validate_contract(args.dataset, args.config)
    elif args.command == "profile": result = profile(args, config)
    elif args.command == "smoke": result = train(args, config, smoke=True)
    else: result = train(args, config)
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
