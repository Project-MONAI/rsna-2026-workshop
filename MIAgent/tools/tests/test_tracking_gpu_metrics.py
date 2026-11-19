"""Ensure GPU telemetry cannot clutter TensorBoard or MLflow metric streams."""

from __future__ import annotations

import json
import os
import tempfile
import unittest
from pathlib import Path

from tools import experiment_tracking
from tools.gpu_optimization_policy import is_safe, next_effective_patches
from tools.miagent_local import parser as local_parser


class _Writer:
    def __init__(self) -> None:
        self.scalars: list[tuple[str, float, int]] = []

    def add_scalar(self, name: str, value: float, step: int) -> None:
        self.scalars.append((name, value, step))

    def flush(self) -> None:
        pass

    def close(self) -> None:
        pass


class TrackingGpuMetricTest(unittest.TestCase):
    def test_gpu_scalar_is_diverted_from_learning_metrics(self) -> None:
        previous = os.environ.get("MIAgent_RUN_DIR")
        with tempfile.TemporaryDirectory() as directory:
            run = Path(directory)
            os.environ["MIAgent_RUN_DIR"] = str(run)
            writer = _Writer()
            experiment_tracking._WRITERS[run] = writer
            try:
                experiment_tracking.record_metrics(
                    {"training.loss": 0.25, "gpu.memory_allocated_mb": 1234}, step=7
                )
            finally:
                experiment_tracking._WRITERS.pop(run, None)
                if previous is None:
                    os.environ.pop("MIAgent_RUN_DIR", None)
                else:
                    os.environ["MIAgent_RUN_DIR"] = previous

            metric_events = [json.loads(line) for line in (run / "tracking/metrics.jsonl").read_text().splitlines()]
            telemetry_events = [json.loads(line) for line in (run / "tracking/telemetry.jsonl").read_text().splitlines()]
            self.assertEqual([event["name"] for event in metric_events], ["training.loss"])
            self.assertEqual([event["name"] for event in telemetry_events], ["gpu.memory_allocated_mb"])
            self.assertEqual(writer.scalars, [("training.loss", 0.25, 7)])

    def test_shared_memory_limit_overrides_whole_card_target(self) -> None:
        probes = [
            {"effective_patches": 1, "telemetry": {"peak.gpu.used_mb": 10000, "peak.gpu.total_mb": 97887}},
            {"effective_patches": 2, "telemetry": {"peak.gpu.used_mb": 15000, "peak.gpu.total_mb": 97887}},
        ]
        self.assertTrue(is_safe(probes[-1], 0.92, memory_limit_mb=20000))
        self.assertFalse(is_safe(
            {"effective_patches": 3, "telemetry": {"peak.gpu.used_mb": 21000, "peak.gpu.total_mb": 97887}},
            0.92,
            memory_limit_mb=20000,
        ))
        candidate, reason = next_effective_patches(probes, memory_limit_mb=20000)
        self.assertEqual((candidate, reason), (3, "headroom_slope_jump"))

    def test_capacity_policy_requires_a_project_boundary(self) -> None:
        probe = {"effective_patches": 1, "telemetry": {"peak.gpu.used_mb": 10000, "peak.gpu.total_mb": 97887}}
        with self.assertRaisesRegex(ValueError, "run-specific"):
            is_safe(probe)

    def test_launcher_does_not_impose_a_universal_shared_budget(self) -> None:
        args = local_parser().parse_args([
            "optimize-gpu",
            "--challenge", "future-project",
            "--baseline", "baseline001",
            "--experiment", "profile",
            "--shared-gpu",
            "--gpu-budget-mb", "24000",
            "--", "python3", "profile.py",
        ])
        self.assertTrue(args.shared_gpu)
        self.assertEqual(args.gpu_budget_mb, 24000)


if __name__ == "__main__":
    unittest.main()
