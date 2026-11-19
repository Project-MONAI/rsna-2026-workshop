---
name: synthseg
description: Integrate and use pinned SynthSeg-MONAI/Cornucopia label-to-image synthesis for medical-image segmentation augmentation or synthetic pretraining. Use for SynthSeg-style workflows built from segmentation label maps; not for ordinary MONAI training, clinical use, or silently accessing held-out test data.
---

# SynthSeg

Use this skill to add a reproducible SynthSeg-style intervention to a medical
segmentation baseline. The skill is harness-neutral: its commands and evidence
are files and shell invocations, with no dependency on chat memory or a Codex
API.

## Non-negotiable boundaries

- Treat SynthSeg as a data-generation/training strategy, not as a model name.
- Keep challenge-specific label construction, splits, intensity assumptions,
  model choice, evaluator, and conclusions in the challenge baseline.
- Use only training-split label maps for synthesis and pretraining. Do not read
  validation labels during training and do not access held-out test data before
  the challenge's model-selection policy permits it.
- Never edit the cached upstream checkout. Pin and verify its exact commit.
- Use an isolated extension image; do not install Cornucopia or SynthSeg
  dependencies into the host Python or the shared core image.
- A smoke result proves wiring only. It is not evidence that synthetic images
  resemble the target modality or improve segmentation.
- Creating this skill, building its image, creating a challenge baseline, and
  queueing a training experiment are separate actions. Do only the actions the
  human has authorized.

## Choose the mode

1. `augmentation_only`: transform real training images and labels together.
   Prefer this lower-cost control when the task has sparse or semantically weak
   label maps.
2. `synthetic_pretraining`: generate images from training label maps and
   pretrain a 3D model. Require a matched random-initialization, real-data-only
   control before attributing any improvement to synthesis.
3. `finetuning`: initialize from the selected synthetic-pretraining checkpoint
   and train on real images using the unchanged real-data comparison recipe.

Do not present synthetic images as realistic CT or MR without direct evidence.
The relevant scientific question is whether the intervention improves
validation performance and failure behavior after controlled real-data
training.

## Workflow

1. If operating inside a MIAgent challenge, first read `AGENTS.md`,
   `skills/orchestration/challenge_run_workflow.md`, the challenge's `state.md`,
   and `dashboard.md`. Preserve any human pause and existing queue.
2. Read [references/data_contract.md](references/data_contract.md) before
   defining label maps or manifests.
3. Read [references/upstream.md](references/upstream.md) before bootstrapping,
   building an image, importing upstream functions, or changing the pin.
4. Read [references/execution.md](references/execution.md) before implementing
   or running augmentation, pretraining, resume, fine-tuning, inference, or
   evaluation.
5. Read [references/tracking.md](references/tracking.md) before writing a
   trainer or accepting a metric-bearing run.
6. Copy and specialize the templates into the baseline. Do not edit templates
   in place for one challenge.
7. Validate the specialized config and manifest, bootstrap the pinned upstream
   source once, prepare training-only label maps, and pass the synthesis smoke.
8. Pass the dependency, transform, one-case optimizer, tracking/viewer, and
   core-regression gates before expensive compute.
9. For a MIAgent non-smoke training job, follow
   `skills/compute/gpu_optimization.md` and submit through
   `tools/miagent_local.py run --stage training`. Attach the required heartbeat
   whenever the submitted job remains active after the turn.
10. Analyze prediction-producing experiments with
    `skills/segmentation/result_analysis.md` and record the hypothesis,
    controlled difference, result, diagnosis, and conclusion.

## Public helper

Run the committed helper from the repository root:

```bash
python3 skills/segmentation/synthseg/scripts/run_synthseg.py --help
```

It provides:

- `validate-config`: fail fast on an invalid or unpinned skill configuration;
- `bootstrap`: clone the exact upstream commit into ignored runtime state;
- `verify-upstream`: prove commit, origin, and clean worktree before a run;
- `prepare-labels`: combine aligned binary masks into a documented multiclass
  training label map, defaulting to the train split only;
- `smoke-synthesis`: run deterministic/variable GPU synthesis checks and write
  NIfTI plus JSON evidence;
- `validate-evidence`: check the minimum durable tracking contract for a phase.

The helper intentionally does not contain a universal trainer. A baseline-owned
adapter composes its chosen network and real-data transforms with the pinned
upstream `SynthSegd` transform. This prevents a reusable skill from silently
owning challenge-specific scientific choices.

## Acceptance rule

Do not promote a long synthetic campaign merely because synthesis runs. Require
all small gates to pass, a matched control, valid per-case validation evidence,
and an explicit challenge-owned continuation rule. Preserve negative results;
dependency or geometry failures are engineering failures, while a valid matched
run without improvement is scientific evidence.
