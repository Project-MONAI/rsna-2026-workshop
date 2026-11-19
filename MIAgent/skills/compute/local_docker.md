# Local persistent Docker compute

Use this backend when work is running on the local teaching server. Slurm
skills remain available only when a human explicitly selects a real cluster.

- `training` is the sole persistent scientific GPU execution environment. It
  contains the core PyTorch/MONAI stack plus nnUNet and SynthSeg dependencies.
- Treat `python3 tools/miagent_local.py preflight` as the authoritative runtime
  inventory; run it once and use its reported packages and commands instead of
  rediscovering them with speculative imports. The local training image pins
  nnU-Net v2 as the `nnunetv2==2.6.2` distribution. Its Python namespace is
  `nnunetv2` (never the obsolete `nnunet` namespace), and its primary commands
  are `nnUNetv2_plan_and_preprocess`, `nnUNetv2_train`, and
  `nnUNetv2_predict`.
- `llm` is the persistent Qwen inference service. Its allocation is owned by
  the current runtime configuration and must be measured rather than assumed;
  it is not a scientific job runner.
- Submit work only through `python3 tools/miagent_local.py run` (or
  `optimize-gpu`). The launcher performs admission, experiment tracking, and
  `docker compose exec training`.
- The `miagent` control container intentionally has no GPU device or
  `nvidia-smi`. Do not probe for either there. The managed launcher queries GPU
  capacity through the GPU-owning `training` service and records admission
  evidence; use that result instead of inventing a control-container bridge.
- MIAgent must not start, stop, restart, or recreate `training`. If it is not
  running or healthy, report that operator-owned condition. An operator uses
  `docker compose up -d training` or `docker compose restart training`.
- While `llm` is running, only jobs explicitly admitted with
  `--shared-gpu --gpu-budget-mb <run-specific MiB>` may run, including
  `optimize-gpu`. Derive that budget from the current GPU, active allocations,
  the human's co-residency requirement, and a documented safety reserve; do not
  reuse a limit from another challenge. Admission budgets are not hard VRAM
  partitions, so the workload must measure and respect its own peak. Exclusive
  work remains unavailable while the LLM stays running.
- The training container is health-checked periodically with `nvidia-smi -L`.
  Repeated failures cause its internal watchdog to exit so Docker's restart
  policy can recover it; timing and retry values belong to runtime
  configuration, not this reusable skill.
- `miagent`, `tracking`, `chat`, and `gateway` are complementary browser/control
  services. They do not execute training workloads.
- NiiVue is a code-server extension in `miagent`, not another container.
