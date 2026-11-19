#!/usr/bin/env python3
"""Harness-neutral helpers for the MIAgent SynthSeg skill.

This command intentionally stops at source/bootstrap, label preparation,
synthesis smoke, and evidence validation. Scientific trainers belong to the
challenge baseline that owns the model, split, preprocessing, and evaluator.
"""

from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import random
import subprocess
import sys
import time
from pathlib import Path
from typing import Any, Iterable, Mapping


UPSTREAM_REPOSITORY = "https://github.com/brudfors/synthseg-monai.git"
UPSTREAM_COMMIT = "9b25434ccbf3a7b4bd902008c4a2514213ac9e6c"
CORNUCOPIA_COMMIT = "8b326481e799bff827cb4e245633631c26db435e"
ALLOWED_MODES = {"augmentation_only", "synthetic_pretraining", "finetuning"}
ALLOWED_SPLITS = {"train", "validation", "test"}


class ContractError(RuntimeError):
    """Raised when an input would violate the reusable skill contract."""


def repository_root() -> Path:
    return Path(__file__).resolve().parents[4]


def default_upstream_dir() -> Path:
    return repository_root() / "runtime" / "upstreams" / "synthseg-monai" / UPSTREAM_COMMIT


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def sha256_json(value: object) -> str:
    encoded = json.dumps(value, sort_keys=True, separators=(",", ":")).encode()
    return hashlib.sha256(encoded).hexdigest()


def write_json(path: Path, value: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n")


def load_yaml(path: Path) -> dict[str, Any]:
    try:
        import yaml
    except ImportError as exc:  # pragma: no cover - environment-dependent
        raise ContractError("PyYAML is required to read SynthSeg configs") from exc
    value = yaml.safe_load(path.read_text())
    if not isinstance(value, dict):
        raise ContractError(f"{path}: expected a YAML mapping")
    return value


def require_mapping(value: object, field: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise ContractError(f"{field} must be a mapping")
    return value


def require_positive_int(value: object, field: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
        raise ContractError(f"{field} must be a positive integer")
    return value


def require_triplet(value: object, field: str) -> list[float]:
    if not isinstance(value, list) or len(value) != 3:
        raise ContractError(f"{field} must contain exactly three values")
    try:
        result = [float(item) for item in value]
    except (TypeError, ValueError) as exc:
        raise ContractError(f"{field} values must be numeric") from exc
    if any(item <= 0 for item in result):
        raise ContractError(f"{field} values must be positive")
    return result


def validate_config_data(config: Mapping[str, Any], *, allow_held_out_test: bool = False) -> None:
    if config.get("schema_version") != 1:
        raise ContractError("schema_version must be 1")
    if config.get("mode") not in ALLOWED_MODES:
        raise ContractError(f"mode must be one of {sorted(ALLOWED_MODES)}")

    upstream = require_mapping(config.get("upstream"), "upstream")
    if upstream.get("repository") != UPSTREAM_REPOSITORY:
        raise ContractError(f"upstream.repository must be {UPSTREAM_REPOSITORY}")
    if upstream.get("commit") != UPSTREAM_COMMIT:
        raise ContractError(f"upstream.commit must be the reviewed pin {UPSTREAM_COMMIT}")
    if upstream.get("cornucopia_commit") != CORNUCOPIA_COMMIT:
        raise ContractError("upstream.cornucopia_commit does not match the reviewed pin")

    data = require_mapping(config.get("data"), "data")
    synthesis_splits = data.get("synthesis_splits")
    if synthesis_splits != ["train"]:
        raise ContractError("data.synthesis_splits must be exactly [train]")

    labels = require_mapping(config.get("labels"), "labels")
    background_id = labels.get("background_id")
    if background_id != 0:
        raise ContractError("labels.background_id must be 0")
    classes = labels.get("classes")
    if not isinstance(classes, list) or len(classes) < 2:
        raise ContractError("labels.classes must contain background and at least one foreground class")
    class_ids: list[int] = []
    class_names: set[str] = set()
    for index, item in enumerate(classes):
        cls = require_mapping(item, f"labels.classes[{index}]")
        class_id = cls.get("id")
        name = cls.get("name")
        if isinstance(class_id, bool) or not isinstance(class_id, int):
            raise ContractError(f"labels.classes[{index}].id must be an integer")
        if not isinstance(name, str) or not name.strip() or name in class_names:
            raise ContractError(f"labels.classes[{index}].name must be nonempty and unique")
        class_ids.append(class_id)
        class_names.add(name)
        if class_id == 0:
            if cls.get("source") is not None:
                raise ContractError("background class must not declare a source")
        elif not isinstance(cls.get("source"), str) or not cls["source"].strip():
            raise ContractError(f"foreground class {name!r} must declare a source")
        excludes = cls.get("exclude", [])
        if not isinstance(excludes, list) or not all(isinstance(value, str) for value in excludes):
            raise ContractError(f"labels.classes[{index}].exclude must be a list of source names")
    if sorted(class_ids) != list(range(len(class_ids))):
        raise ContractError("label IDs must be unique and contiguous from 0")

    containment = labels.get("containment", [])
    if not isinstance(containment, list):
        raise ContractError("labels.containment must be a list")
    for index, item in enumerate(containment):
        rule = require_mapping(item, f"labels.containment[{index}]")
        if not all(isinstance(rule.get(key), str) and rule[key] for key in ("inner", "outer")):
            raise ContractError(f"labels.containment[{index}] requires inner and outer source names")
        threshold = rule.get("max_outside_fraction")
        if not isinstance(threshold, (int, float)) or not 0 <= float(threshold) <= 1:
            raise ContractError("containment max_outside_fraction must be between 0 and 1")

    geometry = require_mapping(config.get("geometry"), "geometry")
    require_triplet(geometry.get("target_spacing_mm"), "geometry.target_spacing_mm")
    require_triplet(geometry.get("patch_size"), "geometry.patch_size")
    if geometry.get("label_interpolation") != "nearest":
        raise ContractError("geometry.label_interpolation must be nearest")

    training = require_mapping(config.get("training"), "training")
    batch_size = require_positive_int(training.get("batch_size"), "training.batch_size")
    patches = require_positive_int(training.get("patches_per_image"), "training.patches_per_image")
    effective = require_positive_int(training.get("effective_patches"), "training.effective_patches")
    if effective != batch_size * patches:
        raise ContractError("training.effective_patches must equal batch_size * patches_per_image")

    tracking = require_mapping(config.get("tracking"), "tracking")
    held_out = tracking.get("held_out_test_accessed")
    if not isinstance(held_out, bool):
        raise ContractError("tracking.held_out_test_accessed must be boolean")
    if held_out and not allow_held_out_test:
        raise ContractError("held-out test access requires the explicit --allow-held-out-test flag")
    max_images = tracking.get("max_validation_images_per_pass")
    if isinstance(max_images, bool) or not isinstance(max_images, int) or not 0 <= max_images <= 2:
        raise ContractError("tracking.max_validation_images_per_pass must be an integer from 0 to 2")


def normalize_git_url(url: str) -> str:
    return url.removesuffix("/").removesuffix(".git")


def run_git(args: Iterable[str], *, cwd: Path | None = None) -> str:
    completed = subprocess.run(
        ["git", *args], cwd=cwd, check=True, capture_output=True, text=True
    )
    return completed.stdout.strip()


def verify_upstream(path: Path) -> dict[str, Any]:
    if not (path / ".git").exists():
        raise ContractError(f"{path} is not a Git checkout; run bootstrap first")
    head = run_git(["rev-parse", "HEAD"], cwd=path)
    origin = run_git(["remote", "get-url", "origin"], cwd=path)
    dirty = run_git(["status", "--porcelain"], cwd=path)
    if head != UPSTREAM_COMMIT:
        raise ContractError(f"upstream HEAD is {head}, expected {UPSTREAM_COMMIT}")
    if normalize_git_url(origin) != normalize_git_url(UPSTREAM_REPOSITORY):
        raise ContractError(f"upstream origin is {origin}, expected {UPSTREAM_REPOSITORY}")
    if dirty:
        raise ContractError("upstream checkout is modified; cached upstream source must remain pristine")
    required = ["LICENSE", "transforms_synthseg.py", "utils_synthseg.py", "requirements.txt"]
    missing = [name for name in required if not (path / name).is_file()]
    if missing:
        raise ContractError(f"upstream checkout is missing required files: {', '.join(missing)}")
    return {
        "repository": UPSTREAM_REPOSITORY,
        "commit": head,
        "path": str(path.resolve()),
        "clean": True,
        "required_files": required,
    }


def command_validate_config(args: argparse.Namespace) -> dict[str, Any]:
    config_path = Path(args.config).resolve()
    config = load_yaml(config_path)
    validate_config_data(config, allow_held_out_test=args.allow_held_out_test)
    return {"valid": True, "config": str(config_path), "sha256": sha256_file(config_path)}


def command_bootstrap(args: argparse.Namespace) -> dict[str, Any]:
    destination = Path(args.upstream_dir).resolve()
    if destination.exists():
        return verify_upstream(destination)
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.mkdir()
    try:
        run_git(["init"], cwd=destination)
        run_git(["remote", "add", "origin", UPSTREAM_REPOSITORY], cwd=destination)
        run_git(["fetch", "--depth", "1", "origin", UPSTREAM_COMMIT], cwd=destination)
        run_git(["checkout", "--detach", "FETCH_HEAD"], cwd=destination)
    except Exception as exc:
        raise ContractError(
            f"bootstrap failed in {destination}; preserve the partial checkout for diagnosis: {exc}"
        ) from exc
    evidence = verify_upstream(destination)
    provenance_path = destination.parent / f"{UPSTREAM_COMMIT}.provenance.json"
    write_json(provenance_path, {**evidence, "verified_at_unix": time.time()})
    evidence["provenance"] = str(provenance_path)
    return evidence


def command_verify_upstream(args: argparse.Namespace) -> dict[str, Any]:
    return verify_upstream(Path(args.upstream_dir).resolve())


def resolve_path(value: object, *, relative_to: Path, field: str) -> Path:
    if not isinstance(value, str) or not value:
        raise ContractError(f"{field} must be a nonempty path string")
    path = Path(value).expanduser()
    return path.resolve() if path.is_absolute() else (relative_to / path).resolve()


def load_nifti(path: Path, *, field: str) -> tuple[Any, Any]:
    try:
        import nibabel as nib
        import numpy as np
    except ImportError as exc:  # pragma: no cover - environment-dependent
        raise ContractError("nibabel and NumPy are required for label preparation") from exc
    if not path.is_file():
        raise ContractError(f"{field} does not exist: {path}")
    image = nib.load(str(path))
    array = np.asarray(image.dataobj)
    if array.ndim != 3:
        raise ContractError(f"{field} must be a 3D NIfTI, got shape {array.shape}")
    if not np.isfinite(array).all():
        raise ContractError(f"{field} contains non-finite values")
    return image, array


def validate_manifest_data(manifest: Mapping[str, Any]) -> list[dict[str, Any]]:
    if manifest.get("schema_version") != 1:
        raise ContractError("dataset manifest schema_version must be 1")
    cases = manifest.get("cases")
    if not isinstance(cases, list) or not cases:
        raise ContractError("dataset manifest cases must be a nonempty list")
    seen: set[str] = set()
    normalized: list[dict[str, Any]] = []
    for index, value in enumerate(cases):
        case = require_mapping(value, f"cases[{index}]")
        case_id = case.get("case_id")
        split = case.get("split")
        if not isinstance(case_id, str) or not case_id.strip() or case_id in seen:
            raise ContractError(f"cases[{index}].case_id must be nonempty and unique")
        if split not in ALLOWED_SPLITS:
            raise ContractError(f"cases[{index}].split must be one of {sorted(ALLOWED_SPLITS)}")
        if not isinstance(case.get("sources"), dict):
            raise ContractError(f"cases[{index}].sources must be a mapping")
        seen.add(case_id)
        normalized.append(dict(case))
    return normalized


def command_prepare_labels(args: argparse.Namespace) -> dict[str, Any]:
    try:
        import nibabel as nib
        import numpy as np
    except ImportError as exc:  # pragma: no cover - environment-dependent
        raise ContractError("nibabel and NumPy are required for label preparation") from exc

    config_path = Path(args.config).resolve()
    manifest_path = Path(args.manifest).resolve()
    output_dir = Path(args.output_dir).resolve()
    config = load_yaml(config_path)
    validate_config_data(config, allow_held_out_test=args.allow_held_out_test)
    cases = validate_manifest_data(load_yaml(manifest_path))

    selected_splits = set(args.include_split or ["train"])
    if not selected_splits <= ALLOWED_SPLITS:
        raise ContractError(f"unknown split(s): {sorted(selected_splits - ALLOWED_SPLITS)}")
    if "validation" in selected_splits and not args.allow_evaluation_splits:
        raise ContractError("validation preparation requires --allow-evaluation-splits")
    if "test" in selected_splits and not args.allow_held_out_test:
        raise ContractError("test preparation requires --allow-held-out-test")

    label_config = require_mapping(config["labels"], "labels")
    classes = [dict(item) for item in label_config["classes"]]
    foreground_classes = sorted(
        (item for item in classes if item["id"] != 0), key=lambda item: (item.get("priority", 0), item["id"])
    )
    containment = label_config.get("containment", [])
    selected = [case for case in cases if case["split"] in selected_splits]
    if not selected:
        raise ContractError(f"no cases belong to selected splits {sorted(selected_splits)}")
    output_dir.mkdir(parents=True, exist_ok=True)
    output_manifest = output_dir / "prepared_manifest.json"
    intended_outputs = [output_dir / f"{case['case_id']}.nii.gz" for case in selected] + [output_manifest]
    if not args.overwrite:
        existing_outputs = [path for path in intended_outputs if path.exists()]
        if existing_outputs:
            raise ContractError(f"refusing to overwrite {existing_outputs[0]}; pass --overwrite explicitly")

    records: list[dict[str, Any]] = []
    for case in selected:
        case_id = case["case_id"]
        image_path = resolve_path(case.get("image"), relative_to=manifest_path.parent, field=f"{case_id}.image")
        reference, image_array = load_nifti(image_path, field=f"{case_id}.image")
        sources: dict[str, Any] = {}
        source_records: dict[str, Any] = {}
        for source_name, source_value in case["sources"].items():
            source_path = resolve_path(
                source_value, relative_to=manifest_path.parent, field=f"{case_id}.sources.{source_name}"
            )
            source_image, source_array = load_nifti(source_path, field=f"{case_id}.sources.{source_name}")
            if source_array.shape != image_array.shape:
                raise ContractError(
                    f"{case_id}.{source_name} shape {source_array.shape} does not match image {image_array.shape}"
                )
            if not np.allclose(source_image.affine, reference.affine, rtol=0, atol=1e-5):
                raise ContractError(f"{case_id}.{source_name} affine does not match the image affine")
            sources[str(source_name)] = source_array > 0
            source_records[str(source_name)] = {
                "path": str(source_path),
                "sha256": sha256_file(source_path),
                "positive_voxels": int((source_array > 0).sum()),
            }

        for rule in containment:
            inner_name, outer_name = rule["inner"], rule["outer"]
            if inner_name not in sources or outer_name not in sources:
                raise ContractError(f"{case_id}: containment rule names an unavailable source")
            inner_count = int(sources[inner_name].sum())
            outside_count = int((sources[inner_name] & ~sources[outer_name]).sum())
            outside_fraction = outside_count / inner_count if inner_count else 0.0
            if outside_fraction > float(rule["max_outside_fraction"]):
                raise ContractError(
                    f"{case_id}: {inner_name} outside {outer_name} fraction {outside_fraction:.6f} "
                    f"exceeds {float(rule['max_outside_fraction']):.6f}"
                )

        output_array = np.zeros(image_array.shape, dtype=np.uint16)
        for cls in foreground_classes:
            source_name = cls["source"]
            if source_name not in sources:
                raise ContractError(f"{case_id}: class {cls['name']} source {source_name!r} is missing")
            mask = sources[source_name].copy()
            for excluded in cls.get("exclude", []):
                if excluded not in sources:
                    raise ContractError(f"{case_id}: excluded source {excluded!r} is missing")
                mask &= ~sources[excluded]
            if not mask.any() and not bool(cls.get("allow_empty", False)):
                raise ContractError(f"{case_id}: required class {cls['name']!r} is empty")
            output_array[mask] = int(cls["id"])

        observed_ids = sorted(int(value) for value in np.unique(output_array))
        allowed_ids = sorted(int(item["id"]) for item in classes)
        if not set(observed_ids) <= set(allowed_ids):
            raise ContractError(f"{case_id}: prepared labels contain undeclared IDs {observed_ids}")
        output_path = output_dir / f"{case_id}.nii.gz"
        header = reference.header.copy()
        header.set_data_dtype(np.uint16)
        nib.save(nib.Nifti1Image(output_array, reference.affine, header), str(output_path))
        records.append(
            {
                "case_id": case_id,
                "split": case["split"],
                "image": {
                    "path": str(image_path),
                    "sha256": sha256_file(image_path),
                    "shape": list(image_array.shape),
                    "spacing_mm": [float(value) for value in reference.header.get_zooms()[:3]],
                    "orientation": "".join(nib.aff2axcodes(reference.affine)),
                },
                "sources": source_records,
                "prepared_label": {
                    "path": str(output_path),
                    "sha256": sha256_file(output_path),
                    "observed_ids": observed_ids,
                    "voxel_counts": {
                        str(class_id): int((output_array == class_id).sum()) for class_id in observed_ids
                    },
                },
            }
        )

    evidence = {
        "schema_version": 1,
        "config": str(config_path),
        "config_sha256": sha256_file(config_path),
        "input_manifest": str(manifest_path),
        "input_manifest_sha256": sha256_file(manifest_path),
        "selected_splits": sorted(selected_splits),
        "cases": records,
    }
    evidence["content_sha256"] = sha256_json(evidence)
    write_json(output_manifest, evidence)
    return {"prepared_cases": len(records), "manifest": str(output_manifest), "sha256": sha256_file(output_manifest)}


def load_upstream_transform(upstream_dir: Path) -> Any:
    module_path = upstream_dir / "transforms_synthseg.py"
    spec = importlib.util.spec_from_file_location("miagent_pinned_transforms_synthseg", module_path)
    if spec is None or spec.loader is None:
        raise ContractError(f"could not load upstream transform module from {module_path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module.SynthSegd


def maybe_record_smoke(evidence: Mapping[str, Any], output_paths: Iterable[Path]) -> None:
    tools_dir = repository_root() / "tools"
    sys.path.insert(0, str(tools_dir))
    try:
        from experiment_tracking import (  # type: ignore
            record_artifact_hint,
            record_description,
            record_metrics,
            record_parameters,
            record_tags,
            record_telemetry,
        )
    except ImportError:
        return
    record_description(
        "SynthSeg transform-contract smoke: verify the pinned upstream transform, deterministic replay, "
        "seed-dependent variation, finite aligned outputs, label IDs, wall time, and GPU memory. This is "
        "wiring evidence, not a model-quality experiment."
    )
    record_tags({"run.kind": "smoke", "task": "segmentation", "synthesis.mode": "label_to_image"})
    record_parameters(
        {
            "upstream.repository": evidence["upstream"]["repository"],
            "upstream.commit": evidence["upstream"]["commit"],
            "synthesis.seed": evidence["seed"],
            "synthesis.patch_size": evidence["patch_size"],
            "labels.allowed_ids": evidence["allowed_label_ids"],
        }
    )
    record_metrics(
        {
            "synthesis.wall_seconds": float(evidence["wall_seconds"]),
        },
        step=0,
    )
    record_telemetry({"gpu.peak_memory_mb": float(evidence["peak_gpu_memory_mb"])}, step=0)
    for path in output_paths:
        record_artifact_hint(path)


def command_smoke_synthesis(args: argparse.Namespace) -> dict[str, Any]:
    try:
        import nibabel as nib
        import numpy as np
        import torch
        from monai.data.meta_tensor import MetaTensor
    except ImportError as exc:  # pragma: no cover - extension-image dependent
        raise ContractError("smoke-synthesis requires the SynthSeg extension image") from exc

    config_path = Path(args.config).resolve()
    label_path = Path(args.label).resolve()
    upstream_dir = Path(args.upstream_dir).resolve()
    output_dir = Path(args.output_dir).resolve()
    config = load_yaml(config_path)
    validate_config_data(config, allow_held_out_test=False)
    upstream = verify_upstream(upstream_dir)
    if not torch.cuda.is_available():
        raise ContractError("CUDA is required for the SynthSeg transform smoke")
    label_image, label_array = load_nifti(label_path, field="label")
    allowed_ids = sorted(int(item["id"]) for item in config["labels"]["classes"])
    observed_ids = sorted(int(value) for value in np.unique(label_array))
    if not set(observed_ids) <= set(allowed_ids):
        raise ContractError(f"input label IDs {observed_ids} exceed declared IDs {allowed_ids}")
    if not any(value > 0 for value in observed_ids):
        raise ContractError("input label has no foreground")

    patch_size = tuple(int(value) for value in config["geometry"]["patch_size"])
    parameters = dict(config["synthesis"]["parameters"])
    parameters["target_labels"] = [value for value in allowed_ids if value != 0]
    seed = int(config["synthesis"]["seed"])
    SynthSegd = load_upstream_transform(upstream_dir)
    source_tensor = torch.from_numpy(np.ascontiguousarray(label_array.astype(np.int16))).unsqueeze(0).cuda()

    def synthesize(local_seed: int) -> tuple[Any, Any]:
        random.seed(local_seed)
        np.random.seed(local_seed)
        torch.manual_seed(local_seed)
        torch.cuda.manual_seed_all(local_seed)
        label = MetaTensor(source_tensor.clone(), affine=torch.as_tensor(label_image.affine, device="cuda"))
        transform = SynthSegd(params=parameters, patch_size=patch_size)
        result = transform({"label": label})
        return result["image"].as_tensor().detach().cpu(), result["label"].as_tensor().detach().cpu()

    torch.cuda.reset_peak_memory_stats()
    started = time.monotonic()
    first_image, first_label = synthesize(seed)
    replay_image, replay_label = synthesize(seed)
    varied_image, varied_label = synthesize(seed + 1)
    wall_seconds = time.monotonic() - started
    if first_image.shape != first_label.shape:
        raise ContractError("synthesized image and label shapes differ")
    if not torch.isfinite(first_image).all():
        raise ContractError("synthesized image contains non-finite values")
    replay_max_abs_error = float(torch.max(torch.abs(first_image - replay_image)).item())
    replay_atol = 5e-7
    # CUDA interpolation in the pinned stack can differ by one float32 ULP
    # across identical invocations even when the categorical geometry is
    # exactly reproducible. Require exact labels and a deliberately tiny,
    # recorded absolute image tolerance so real RNG drift still fails.
    if not torch.equal(first_label, replay_label) or not torch.allclose(
        first_image, replay_image, rtol=0.0, atol=replay_atol
    ):
        raise ContractError(
            f"fixed-seed synthesis exceeded replay tolerance: max_abs_error={replay_max_abs_error:.9g}"
        )
    if torch.equal(first_image, varied_image) and torch.equal(first_label, varied_label):
        raise ContractError("different synthesis seeds produced identical image and label")
    output_ids = sorted(int(value) for value in torch.unique(first_label).tolist())
    if not set(output_ids) <= set(allowed_ids):
        raise ContractError(f"synthesized labels contain undeclared IDs {output_ids}")
    if not any(value > 0 for value in output_ids):
        raise ContractError("synthesized label has no foreground")

    output_dir.mkdir(parents=True, exist_ok=True)
    output_image_path = output_dir / "synth_image.nii.gz"
    output_label_path = output_dir / "synth_label.nii.gz"
    evidence_path = output_dir / "smoke_result.json"
    existing = [path for path in (output_image_path, output_label_path, evidence_path) if path.exists()]
    if existing and not args.overwrite:
        raise ContractError(f"refusing to overwrite {existing[0]}; pass --overwrite explicitly")
    image_out = first_image.squeeze(0).numpy().astype(np.float32)
    label_out = first_label.squeeze(0).numpy().astype(np.uint16)
    nib.save(nib.Nifti1Image(image_out, label_image.affine), str(output_image_path))
    nib.save(nib.Nifti1Image(label_out, label_image.affine), str(output_label_path))
    evidence = {
        "valid": True,
        "upstream": upstream,
        "config": str(config_path),
        "config_sha256": sha256_file(config_path),
        "input_label": str(label_path),
        "input_label_sha256": sha256_file(label_path),
        "seed": seed,
        "patch_size": list(patch_size),
        "allowed_label_ids": allowed_ids,
        "input_label_ids": observed_ids,
        "output_label_ids": output_ids,
        "output_shape": list(image_out.shape),
        "deterministic_replay": True,
        "deterministic_replay_image_atol": replay_atol,
        "deterministic_replay_image_max_abs_error": replay_max_abs_error,
        "deterministic_replay_labels_exact": True,
        "different_seed_varies": True,
        "wall_seconds": wall_seconds,
        "peak_gpu_memory_mb": torch.cuda.max_memory_allocated() / (1024 * 1024),
        "torch_version": torch.__version__,
        "cuda_version": torch.version.cuda,
        "gpu_name": torch.cuda.get_device_name(0),
        "outputs": {
            "image": {"path": str(output_image_path), "sha256": sha256_file(output_image_path)},
            "label": {"path": str(output_label_path), "sha256": sha256_file(output_label_path)},
        },
    }
    write_json(evidence_path, evidence)
    maybe_record_smoke(evidence, (output_image_path, output_label_path, evidence_path))
    return {"valid": True, "evidence": str(evidence_path), "wall_seconds": wall_seconds}


def command_validate_evidence(args: argparse.Namespace) -> dict[str, Any]:
    run_dir = Path(args.run_dir).resolve()
    tracking = run_dir / "tracking"
    required_files = [tracking / "params.json", tracking / "description.md", tracking / "metrics.jsonl"]
    if args.phase in {"pretrain", "finetune", "evaluate"}:
        required_files.append(run_dir / "summary.md")
    missing_files = [str(path) for path in required_files if not path.is_file()]
    if missing_files:
        raise ContractError(f"missing required evidence files: {', '.join(missing_files)}")
    params = json.loads((tracking / "params.json").read_text())
    if not isinstance(params, dict):
        raise ContractError("tracking/params.json must contain an object")
    common_parameters = {
        "upstream.repository",
        "upstream.commit",
        "synthesis.seed",
        "provenance.config_sha256",
        "provenance.manifest_sha256",
        "test.held_out_accessed",
    }
    training_parameters = {
        "training.architecture",
        "training.batch_size",
        "training.patches_per_image",
        "training.effective_patches",
        "training.loss",
        "training.learning_rate",
        "training.validation_policy",
    }
    required_parameters = common_parameters | (training_parameters if args.phase in {"pretrain", "finetune"} else set())
    missing_parameters = sorted(required_parameters - set(params))
    if missing_parameters:
        raise ContractError(f"missing required tracking parameters: {', '.join(missing_parameters)}")
    if params.get("upstream.commit") != UPSTREAM_COMMIT:
        raise ContractError("tracked upstream commit does not match the skill pin")

    metric_names: set[str] = set()
    for line_number, line in enumerate((tracking / "metrics.jsonl").read_text().splitlines(), start=1):
        try:
            event = json.loads(line)
        except json.JSONDecodeError as exc:
            raise ContractError(f"metrics.jsonl line {line_number} is invalid JSON") from exc
        if isinstance(event, dict) and isinstance(event.get("name"), str):
            metric_names.add(event["name"])
    required_metrics = (
        {"synthesis.wall_seconds", "gpu.peak_memory_mb"}
        if args.phase == "smoke"
        else {"training.loss", "training.dice", "validation.loss", "validation.dice"}
    )
    missing_metrics = sorted(required_metrics - metric_names)
    if missing_metrics:
        raise ContractError(f"missing required metrics: {', '.join(missing_metrics)}")
    return {
        "valid": True,
        "phase": args.phase,
        "run_dir": str(run_dir),
        "parameters_checked": sorted(required_parameters),
        "metrics_checked": sorted(required_metrics),
    }


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="command", required=True)

    validate = subparsers.add_parser("validate-config", help="validate a specialized SynthSeg YAML config")
    validate.add_argument("--config", required=True)
    validate.add_argument("--allow-held-out-test", action="store_true")
    validate.set_defaults(handler=command_validate_config)

    bootstrap = subparsers.add_parser("bootstrap", help="clone and verify the exact upstream commit")
    bootstrap.add_argument("--upstream-dir", default=str(default_upstream_dir()))
    bootstrap.set_defaults(handler=command_bootstrap)

    verify = subparsers.add_parser("verify-upstream", help="verify upstream origin, commit, files, and cleanliness")
    verify.add_argument("--upstream-dir", default=str(default_upstream_dir()))
    verify.set_defaults(handler=command_verify_upstream)

    prepare = subparsers.add_parser("prepare-labels", help="prepare multiclass label maps from aligned masks")
    prepare.add_argument("--config", required=True)
    prepare.add_argument("--manifest", required=True)
    prepare.add_argument("--output-dir", required=True)
    prepare.add_argument("--include-split", action="append", choices=sorted(ALLOWED_SPLITS))
    prepare.add_argument("--allow-evaluation-splits", action="store_true")
    prepare.add_argument("--allow-held-out-test", action="store_true")
    prepare.add_argument("--overwrite", action="store_true")
    prepare.set_defaults(handler=command_prepare_labels)

    smoke = subparsers.add_parser("smoke-synthesis", help="run the GPU transform-contract smoke")
    smoke.add_argument("--config", required=True)
    smoke.add_argument("--label", required=True)
    smoke.add_argument("--output-dir", required=True)
    smoke.add_argument("--upstream-dir", default=str(default_upstream_dir()))
    smoke.add_argument("--overwrite", action="store_true")
    smoke.set_defaults(handler=command_smoke_synthesis)

    evidence = subparsers.add_parser("validate-evidence", help="validate durable phase evidence")
    evidence.add_argument("--run-dir", required=True)
    evidence.add_argument("--phase", required=True, choices=["smoke", "pretrain", "finetune", "evaluate"])
    evidence.set_defaults(handler=command_validate_evidence)
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        result = args.handler(args)
    except (ContractError, OSError, subprocess.CalledProcessError, ValueError) as exc:
        print(json.dumps({"valid": False, "error": str(exc)}, indent=2), file=sys.stderr)
        return 2
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
