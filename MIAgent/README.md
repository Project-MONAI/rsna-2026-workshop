# MIAgent v3.5

MIAgent is a Codex harness for human-guided medical-imaging challenge work.
The base model leads the problem solving; MIAgent supplies required seriousness
checks, inspectable evidence, and a durable human/agent decision trajectory.

## Quick Start

Clone the repo:

```text
git clone https://github.com/Project-MONAI/rsna-2026-workshop.git
cd rsna-2026-workshop/MIAgent
```

For the supported local GPU runtime, use the container setup instead of host
Python. It runs PyTorch/MONAI workloads, MLflow, TensorBoard, and the report UI
in Docker while preserving state on the host:

```text
python3 tools/miagent_local.py init
python3 tools/miagent_local.py build
python3 tools/miagent_local.py preflight
python3 tools/miagent_local.py up
python3 tools/miagent_local.py smoke
```

For the student workshop, start with [the lab overview](lab/01_overview.html).
Host preparation, dataset mounts, and service startup are documented in
[the lab preparation guide](../lab_prep/SETUP.md).

Open Codex in the `MIAgent` folder, then start a challenge with one of these
prompts.

Interactive mode, where Codex stops at the normal human gates:

```text
Solve this MSD Dataset Task09 Spleen challenge for me (http://medicaldecathlon.com/). Use the first 80% as training and the last 20% as a held-out test set. Make sure test Dice is over 0.98. Use the local machine with 1 GPU and unlimited time.
```

Auto mode, where Codex continues end-to-end unless blocked:

```text
:/auto Solve this MSD Dataset Task09 Spleen challenge for me (http://medicaldecathlon.com/). Use the first 80% as training and the last 20% as a held-out test set. Make sure test Dice is over 0.98. Use the local machine with 1 GPU and unlimited time.
```

The core model is simple:

```text
one challenge folder = one durable research record
one active session at a time
one active baseline direction at a time after candidate selection
```

- The challenge folder—not the Codex transcript—preserves rules, data handling,
  code, configs, jobs, failures, visual evidence, results, steering, and
  decisions.
- When a direction is no longer worthwhile, record why and continue in a new
  `baselines/baselineXXX_<direction>/` folder.
- A later session may take over after verifying live execution state.
- Before selection, `candidates.md` compares literature-backed alternatives:
  mature task methods, foundation/pretrained models, metric/anatomy priors,
  ensembles/robustness strategies, and a fallback.
- The compact human gate must not favor the first runnable baseline over a
  stronger uninspected direction.

## Setup With Codex

- Private cluster access and an external critic are optional.
- New users can run MIAgent locally, create challenge folders, use templates,
  and open the Web UI without DFW or NVIDIA critic credentials.

Private integrations are profile-based, but the human should not have to edit
the profile by hand. Ask Codex to create the setup from the minimum personal
facts:

```text
Set up MIAgent for me on DFW.
My DFW user id is <cluster_user>.
My NVIDIA Inference API key is <api_key>.
```

Codex should then create or update:

```text
skills/compute/profiles/<cluster_user>.yaml
```

- Start from `skills/compute/profiles/example.yaml`.
- Derive standard DFW paths from the user ID.
- Store the API key outside the repo at the configured key-file path.
- Never write secrets into tracked files.

For DFW, Codex should fill or verify:

```text
username = <cluster_user>
dataset root = /cluster/shared/users/<cluster_user>/MIAgent/dataset
MIAgent working root = /cluster/shared/users/<cluster_user>/MIAgent
SSH identity, account, container image, mount, and container Python
NVIDIA critic endpoint/model/key-file settings
```

- Ask only for facts that cannot be inferred or verified, such as a nonstandard
  SSH key, missing image, different account, or failed login.
- Probe SSH, SLURM, writable roots, container Python, and critic dry-run.
- If DFW or critic access is unavailable, mark it unavailable and continue
  locally or with the user's cluster/profile.
- If the external critic is unavailable, use a fresh critic subagent or, when
  delegation is unavailable, a dedicated self-critique. Provider failure alone
  does not complete discovery.

## Human Workflow

Use natural language by default. There is only one command:

```text
:/auto    run end-to-end without stopping at the normal human gates
```

Without `:/auto`, Codex stops twice:

1. after it proposes baseline candidates;
2. after the selected baseline has a detailed implementation plan.

Human approval can be plain language, such as `approve baseline001`, `go ahead`,
`run it`, or `change the loss first`.

At a high level, the challenge loop is:

```text
understand challenge -> decompose and search each problem
-> compare candidates and alternatives -> choose one direction
-> write implementation plan -> implement and smoke test
-> internal loop: run, analyze, update state, and optimize the baseline
-> external loop when plateaued: re-search and recombine affected components
-> stop when the challenge stop condition is met
```

- Create a thread heartbeat for long GPU/SLURM jobs, usually every 15 minutes.
- Keep it active across empty queues and direction changes until completion or
  human pause/stop.
- Stay quiet when nothing changes; report meaningful results, direction
  changes, blockers, submissions, and a compact status at least every four
  active hours.
- A new session verifies jobs and establishes its own heartbeat.
- This thread-monitor interval is distinct from the local challenge queue:
  `tools/challenge_heartbeat.py` reconciles local jobs at least every two
  minutes so completed work releases dependencies promptly.

- Ask the human instead of guessing when facts, access, rules, evaluator
  validity, or expensive-compute authority are unresolved.

- [Challenge run workflow](skills/orchestration/challenge_run_workflow.md):
  complete operating contract.
- `AGENTS.md`: repository routing bootstrap.
- Challenge templates: artifact scopes and fields.
- Skills: specialized techniques.
- Filled artifacts never replace their templates; reload the raw
  `miagent-template-source` before creation or material edits.

## Challenge Folder

New challenges start from:

```text
challenge/challenge_template/
```

Expected layout:

```text
challenge/<name>/
  challenge.md       stable task, data, rules, metric, submission facts
  dashboard.md       live readiness, resources, results, and per-baseline job queue
  state.md           short current-focus attention reset
  trajectory.md      append-only decisions and meaningful direction shifts
  candidates.md      concise baseline candidates and human selection
  literature.md       problem-wise search evidence and current recomposition
  critics/           external critic reports when available
  shared/
    visualization/   task-specific renderer reused by every baseline
  baselines/
    baseline001_<direction>/
      baseline.md    workspace for this solution direction
      config/
      code/
      env/
      runs/
        exp001_smoke/
          experiment.md    Intent before launch; Outcome after a valid result
          per_case_dice/
          result_viewers/result_viewer.html generated by evaluation
          visualization_manifests/
          jobs/
        exp002_<change>/
          experiment.md    Intent before launch; Outcome after a valid result
          per_case_dice/
          result_viewers/result_viewer.html generated by evaluation
          visualization_manifests/
          jobs/
```

## What Humans Read

Before choosing a baseline:

```text
candidates.md
```

After a baseline is selected:

```text
state.md
dashboard.md
```

While one baseline agent is working:

```text
baselines/<baseline>/baseline.md
```

For a specific experiment:

```text
baselines/<baseline>/runs/<exp>/experiment.md
baselines/<baseline>/runs/<exp>/result_viewers/result_viewer.html
```

## File Purposes

- `challenge.md`: stable facts, MIAgent harness version/tag, and open human
  questions.
- `dashboard.md`: shared challenge readiness, resource use, result index, and
  one compact execution board per baseline. Active jobs are grouped by
  scientific experiment; every available result viewer and other important
  completed experiments remain linked, while planned experiments link to their
  run evidence.
- `state.md`: the small current attention reset—stage objective, bottleneck,
  pointers to both exploration maps, active human constraint, and the continue/
  switch/freeze judgment. It contains no evidence history, planned action, or
  duplicate research queue.
- `trajectory.md`: an append-only record of agent decisions and human steering
  that changed the work, with a reasoning summary, evidence, and action.
- `candidates.md`: short post-critic comparison, selection record, and
  external-direction exploration queue.
- `literature.md`: challenge decomposition, problem-wise search evidence, and
  recomposition into a unified direction; targeted re-search updates affected
  problems during the external loop.
- `shared/visualization/`: one challenge-level debugging renderer shared by all
  baselines. It provides `visualize_case(...)` for quick debugging and
  `visualize_run(...)` plus a CLI for per-experiment viewers; baseline-specific
  code only adapts native outputs to this contract.
- `baseline.md`: one solution direction's serious implementation plan,
  living Internal Exploration, visualization and logging design, implementation
  acceptance evidence, and implementation steering.
- `experiment.md`: one scientific experiment's immutable pre-run Intent and,
  after a valid result, its Outcome, evidence, diagnosis, decision, and concise
  downstream updates. Routine execution failures remain in `jobs/` and the
  dashboard.
- `result_viewers/result_viewer.html`: per-experiment visual and per-case
  evidence generated by the shared renderer after every experiment that
  produces predictions and expanded for key experiments. Repeated per-case
  tables and manifests live under `per_case_dice/` and
  `visualization_manifests/`; predictions remain colocated with their generated
  error NIfTIs and interactive case-review pages.

- For a valid result, complete its evidence, viewer, and Outcome.
- If it creates or resolves within-direction work, update Internal Exploration;
  if it creates an independent pipeline, update Candidate Comparison. Record
  consequential decisions in `trajectory.md`.
- Update `state.md` only when its focus, exploration pointer, active constraint,
  or scientific judgment changes; design the next experiment from that state
  and the linked exploration owner.
- Continue the internal loop until the direction reaches target or an
  evidence-backed plateau.
- At a below-target plateau, preserve the decision in `trajectory.md`, change
  focus in `state.md`, and re-search/recombine affected components.
- Create a new baseline only for an independent direction.
- One `expXXX` is one decision-bearing experiment—not one command or job. Keep
  train/resume/infer/eval/visualize/package/submit/repair stages in its `jobs/`.
- Create a new experiment only for a new hypothesis, intervention, comparison,
  or decision-bearing diagnostic.
- Store decisionful human steering in its owning artifact; add a concise
  trajectory link for cross-stage changes. `state.md` links only active steering.

## Detailed Contracts And Skills

The workflow points to the detailed contracts and skills:

- [Literature template](challenge/challenge_template/literature.md): complete
  initial-discovery and focused re-search contract, artifact structure, and
  evidence requirements.
- [Result analysis](skills/proposal/result_analysis.md): valid result diagnosis
  and decision; routine failures are repaired without a new Outcome.
- `skills/<task>/result_analysis.md`: task-specific evidence and diagnostic
  knowledge.
- [MONAI](skills/monai/SKILL.md): cross-cutting guidance for code that directly
  uses MONAI transforms, datasets, segmentation components, or inferers.
- [Compute skills](skills/compute/README.md): GPU-efficiency technique, cluster
  paths, and SLURM usage.

Task-specific evidence lives under:

```text
skills/segmentation/
skills/registration/
skills/generation/
skills/representation/
skills/vlm/
```

## Web UI

Run the read-only local challenge file browser with:

```text
python3 tools/webui/app.py --challenge challenge/<name> --port 8765
```

- The left pane shows the challenge folder.
- Markdown renders as a document; logs, configs, code, images, and PDFs open
  directly.
- Experiment records, jobs/logs, results, and viewers are ordinary links.
- `result_viewers/result_viewer.html` renders with its relative image assets in
  the right pane.

## Checks

Run after multi-file updates:

```text
python3 tools/check_consistency.py challenge/<name>
```

Seal an approved scientific direction before method-specific implementation:

```text
python3 tools/check_consistency.py --phase discovery --strict --seal challenge/<name>
```
