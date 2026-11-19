"""Adaptive GPU-capacity policy shared by local training adapters.

The policy intentionally avoids fixed ladders.  It learns a memory slope from
completed probes, jumps by up to 8x while headroom permits, and then brackets
the 92% target with interpolation if a large jump is too large.
"""

from __future__ import annotations

import math
from typing import Any, Iterable


POLICY_VERSION = "adaptive-headroom-v1"


def peak_gpu_mb(probe: dict[str, Any]) -> float:
    return float(probe.get("telemetry", {}).get("peak.gpu.used_mb", 0.0))


def total_gpu_mb(probe: dict[str, Any]) -> float:
    return float(probe.get("telemetry", {}).get("peak.gpu.total_mb", 0.0))


def is_safe(
    probe: dict[str, Any],
    target_fraction: float | None = None,
    memory_limit_mb: float | None = None,
) -> bool:
    total = total_gpu_mb(probe)
    if target_fraction is None and memory_limit_mb is None:
        raise ValueError("a run-specific target_fraction or memory_limit_mb is required")
    target_mb = total if target_fraction is None else total * target_fraction
    if memory_limit_mb is not None:
        target_mb = min(target_mb, float(memory_limit_mb))
    return not bool(probe.get("oom")) and total > 0 and peak_gpu_mb(probe) <= target_mb


def next_effective_patches(
    probes: Iterable[dict[str, Any]],
    *,
    target_fraction: float | None = None,
    memory_limit_mb: float | None = None,
    max_growth: int = 8,
    max_effective_patches: int = 1024,
) -> tuple[int | None, str]:
    """Choose the next capacity probe from observed process-memory peaks.

    Returns the next effective patch count and a concise machine-readable
    decision reason.  A target-exceeding stable result is a bracket upper bound
    just like an OOM: it is not selected for training.
    """
    values = sorted((dict(probe) for probe in probes), key=lambda item: int(item["effective_patches"]))
    safe = [item for item in values if is_safe(item, target_fraction, memory_limit_mb)]
    unsafe = [item for item in values if not is_safe(item, target_fraction, memory_limit_mb)]
    if not safe:
        return None, "no_safe_probe"
    lower = max(safe, key=lambda item: int(item["effective_patches"]))
    lower_effective = int(lower["effective_patches"])
    upper_values = [int(item["effective_patches"]) for item in unsafe if int(item["effective_patches"]) > lower_effective]
    if upper_values:
        upper = min(upper_values)
        candidate = (lower_effective + upper) // 2
        if candidate <= lower_effective:
            return None, "target_bracket_converged"
        return candidate, "refine_oom_or_target_bracket"

    # Fit process memory = intercept + slope * effective patches.  The most
    # recent two safe probes are enough and avoid assuming a zero-memory model.
    slope = 0.0
    intercept = peak_gpu_mb(lower)
    if len(safe) >= 2:
        left, right = safe[-2], safe[-1]
        dx = int(right["effective_patches"]) - int(left["effective_patches"])
        if dx > 0:
            slope = max(0.0, (peak_gpu_mb(right) - peak_gpu_mb(left)) / dx)
            intercept = max(0.0, peak_gpu_mb(right) - slope * int(right["effective_patches"]))
    total = total_gpu_mb(lower)
    target_mb = total if target_fraction is None else total * target_fraction
    if memory_limit_mb is not None:
        target_mb = min(target_mb, float(memory_limit_mb))
    if slope > 0:
        estimate = max(lower_effective + 1, int(math.floor((target_mb - intercept) / slope * 0.98)))
        candidate = min(lower_effective * max_growth, estimate, max_effective_patches)
        return max(lower_effective + 1, candidate), "headroom_slope_jump"
    return min(lower_effective * max_growth, max_effective_patches), "initial_8x_headroom_jump"
