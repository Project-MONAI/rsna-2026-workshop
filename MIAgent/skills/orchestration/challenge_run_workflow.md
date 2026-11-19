# Challenge Run Workflow

Complete operating contract for medical-imaging challenge work.

- One active session operates one durable `challenge/<task>` folder initialized
  from `challenge/challenge_template/`.
- This file owns phase order, gates, continuous execution, and handoff. Raw
  templates own artifact fields and update rules; `skills/` owns techniques.

```text
understand -> readiness -> independent thesis -> open research -> candidate gate
-> discovery seal -> implementation-plan gate -> implement/smoke
-> internal loop -> external loop when valuable -> freeze
```

## File Ownership

A filled artifact remains governed by the raw template named in its
`miagent-template-source`. Reload that template before creating or materially
updating the artifact, and after resume or context compaction. Write an event in
its narrowest owner and link it elsewhere instead of copying it.

| Artifact | Purpose | Update When |
|---|---|---|
| `challenge.md` | Stable task, data, metric, rule, and submission contract | Initial understanding, or a fact/assumption changes |
| `dashboard.md` | Live authorization, resources, jobs, heartbeat, blockers, and important-result index | Operational truth, queue, or next wake changes |
| `literature.md` | Preserved independent thesis, decision-changing research, and revised direction | Initial discovery or focused re-search changes evidence |
| `candidates.md` | Scientific selection and living external-direction map | A direction, judgment, blocker, or decisive next test changes |
| `baselines/<baseline>/baseline.md` | Current implementation contract and living Internal Exploration | Plan/adopted implementation changes, or valid evidence changes an internal possibility |
| `runs/<exp>/experiment.md` | One scientific intervention's immutable Intent, evidence, Outcome, and diagnosis | Before launch and after a valid decision-bearing result |
| `runs/<exp>/jobs/` | Commands, jobs, retries, resumes, and execution evidence | An execution stage changes |
| `trajectory.md` | Concise causal index of consequential agent decisions and human steering | Focus, direction, plan, authority, or stop outcome changes |
| `state.md` | Small current scientific-state reset and continue/switch/freeze judgment | Current focus, exploration pointer, constraint, or judgment changes |

For a valid result: write the experiment Outcome first; update the affected
baseline or candidate map; append the decision and decisive evidence to
`trajectory.md` only if the decision changed; update `state.md` last only if the
current scientific state changed. Keep `dashboard.md` operationally current.
Retain human steering in `state.md` only while it constrains current work.

## The 10 Steps

1. **Understand.**
   - Initialize or verify `challenge.md`. Resolve blocking questions; use a
     stated assumption only when work can safely continue.
   - Natural-language human steering can redirect, pause, or stop the run at any
     time. On pause/stop, verify process state and launch nothing; kill work only
     when requested or when a recorded kill rule applies.

2. **Establish readiness and authority.**
   - Record readiness, objective/target, compute budget, and authorization in
     `dashboard.md`. Before discovery is sealed, allow only task facts,
     split-safe data characterization, rule/evaluator clarification, downloads,
     and general resource checks—no method-specific artifact, probe, or GPU job.
   - Prior MIAgent or comparison-session results are benchmark history when the
     user excludes them. Public papers, official leaderboards, winner methods,
     and released implementations remain normal research evidence unless the
     user forbids them. Never inspect protected labels or case-level protected
     summaries.
   - `:/auto` supplies the initial candidate and plan approvals, plus later
     direction authority, only after each gate's reasoning is complete. It does
     not authorize ambiguous rules, invalid evaluation, human-only access, or
     unapproved expensive compute. Record it in `dashboard.md` and `trajectory.md`.

3. **Think, search, and synthesize.**
   - Before literature, specialized method skills, implementations, package
     probes, prior solutions, or candidate ranking, the main agent writes the
     Independent Scientific Thesis in `literature.md` from the task and its own
     knowledge. Preserve it rather than rewriting hindsight into it.
   - Use one fresh research subagent when available. Give it `challenge.md` and
     the thesis without inherited chat, prior candidates, or a prescribed search
     taxonomy. It searches freely for evidence that may challenge or extend the
     thesis, including current primary sources, implementations, weights,
     applicable repository skills, and permitted prior-task evidence. During an
     external loop, also give it the current bottleneck and affected directions.
   - The subagent fills only Open Research Findings and returns decisive Evidence
     IDs and blockers; it does not choose the solution. If delegation is
     unavailable, preserve the same think-first separation locally. While it
     runs, the main agent may do only the neutral readiness work from Step 2.
   - The main agent spot-checks decisive sources, writes the Revised Scientific
     Direction, and completes the post-search omission audit. Search only gaps
     that could change the decision. Published pipelines are evidence and
     reusable components, not boundaries on the agent's solution.
   - Draft `candidates.md`, then run the external critic on the thesis, findings,
     revised direction, and candidates. Integrate only objections that change the
     judgment. If the provider fails, use a fresh critic subagent, or a dedicated
     self-critique only when delegation is unavailable. Provider failure is not
     a passed critic gate. Clear all discovery-checker warnings.

4. **Select one baseline.**
   - Select the complete pipeline the agent judges most likely to maximize the
     objective. Record how research verified, refined, replaced, or rejected the
     thesis and compare the strongest alternative. Evidence informs judgment but
     does not force an existing published pipeline.
   - Do not demote the strongest direction for setup time, unfamiliarity, cached
     dependencies, or a desire to start. Only a verified rule/license/access,
     asset, interface, or minimum-compute blocker can justify selecting another
     direction. A simple control may be diagnostic but cannot replace the
     selected pipeline.
   - Present the candidate gate and wait unless `:/auto` is active. Record the
     result in `candidates.md`, `trajectory.md`, and `dashboard.md`, then run:

     ```text
     python3 tools/check_consistency.py --phase discovery --strict --seal challenge/<name>
     ```

     The initial seal must precede baseline, code, environment, experiment, or
     job artifacts. Do not initialize `state.md` yet.

5. **Plan implementation.**
   - After the seal, create the selected baseline and write its serious,
     multi-component Implementation Plan. Prefer and inspect mature reusable
     implementations; define component roles, interfaces, reuse/build
     boundaries, compute use, GPU efficiency, and human-inspectable evidence.
   - When the implementation directly uses MONAI APIs, read
     `skills/monai/SKILL.md` and the references it routes to. A task-specific
     skill, official MONAI Bundle, or nnU-Net skill owns its established path.
     If SegResNet is selected, read
     `skills/segmentation/segresnet/SKILL.md` and use its configuration-driven
     runner rather than writing a replacement training and evaluation stack.
   - Leave Internal Exploration empty until a valid performance result reveals
     what is worth improving. Do not pre-commit a generic science checklist.
   - Draft the shared visualization contract. Start no experiment before the
     plan gate.

6. **Pass the implementation-plan gate.**
   - Present `baseline.md` and wait unless `:/auto` is active; revise in place.
   - After approval, append the decision to `trajectory.md`, initialize
     `state.md` with one focus plus baseline/external pointers, and activate the
     dashboard. Its internal pointer may say the first decision-bearing result
     will seed Internal Exploration. Later directions retain authorization unless
     paused or new authority is required.

7. **Implement and smoke.**
   - Implement the complete selected composition and shared visualizer. Before
     launch, create `exp001_smoke/experiment.md` Intent, add it to the dashboard,
     and establish one session heartbeat covering every asynchronous job.
   - Keep every stage under the experiment's `jobs/`; reconcile real process
     state, keep evaluation provenances distinct, profile representative GPU
     use, produce the viewer, and complete Implementation Acceptance. A
     control-only smoke does not prove the selected composition.
   - Smoke/probes are diagnostic, not performance Outcomes. Establish a
     meaningful reference result; after its Outcome, seed Internal Exploration
     with only task-specific possibilities supported by evidence or judgment.
   - Before non-smoke training, complete readiness/acceptance, write every
     planned Intent, and pass `python3 tools/check_consistency.py --strict
     challenge/<name>`. Every warning blocks admission.
   - On the supported local host, read `skills/compute/local_docker.md` and
     submit jobs through `python3 tools/miagent_local.py run`. Workloads run in
     the already-running persistent `training` container; the challenge agent
     does not own that container's start, stop, restart, or recreation.
     Before non-smoke training, also follow
     `skills/compute/gpu_optimization.md` and launch the admitted workload with
     `--stage training` so the local GPU gate can enforce its evidence.

8. **Run the internal loop.**
   - From the state focus and living Internal Exploration, choose the
     highest-value question; add a new one when evidence or intuition reveals a
     better opportunity. Write Intents before scheduling.
   - Within the one active baseline, use adaptive racing when resources allow:
     run fair recipe, component, architecture, fold, or seed screens in parallel
     on the same evaluation contract; promote the best one or two and useful
     complements; deepen them; then confirm robustly. A screen must be
     decision-bearing, and one weak fold/seed or undertrained run cannot reject a
     method family. Mature evidence may justify going directly to robust training.
   - Monitor actual processes. Repair code, environment, OOM, preemption,
     timeout, and scheduler failures in the same experiment without a
     performance Outcome; they are not scientific evidence.
   - For each valid result, create the viewer and Outcome, update only affected
     exploration/implementation judgments, and follow the artifact propagation
     order above. Use `skills/proposal/result_analysis.md` for important,
     surprising, weak, or suspicious results.
   - At each focus boundary, ask whether any plausible within-direction change
     is still likely to produce a large gain. Use the state template's reminders
     to challenge the judgment, but test only relevant ideas. Checklist
     completion, implementation difficulty, default/smoke completion, a weak
     plateau, ordinary failure, or an empty queue does not justify exit.
   - Switch to the external loop when its expected scientific value exceeds
     further local tuning. A competent reference is useful, but need not be
     exhaustively optimized when evidence points to a method-class mismatch or
     stronger formulation.
   - Maintain the heartbeat until freeze, completion, or human pause/stop. At
     each wake, do one bounded scheduler/log/result reconciliation. Before
     yielding while work continues, schedule/execute the next action and record
     its dashboard link and next wake.
     Use a 15-minute thread heartbeat by default. This is separate from
     `tools/challenge_heartbeat.py`, whose local dependency queue reconciles at
     least every 120 seconds.

9. **Run the external loop.**
   - Record the switch in Internal Exploration, `trajectory.md`, and `state.md`.
     Return to Step 3 for focused research on the current bottleneck; preserve
     the original thesis, add only decision-changing findings, rerun the critic,
     and update the external map.
   - Select the unblocked direction now judged most likely to maximize the
     objective and reseal discovery. Reuse the baseline only for a compatible
     extension; otherwise create and approve a new baseline. Keep one active
     baseline—select and activate an independent direction before its first
     experiment, then use parallel racing within it. Do not require experimental
     proof that can only exist after the switch.
   - Continue while an external direction is plausibly likely to produce a large
     gain. Candidate rows need not all be mechanically closed; the agent may
     judge one not worthwhile with a causal comparison. Difficulty or lack of an
     implementation attempt is not evidence that it is scientifically weak.

10. **Freeze or stop.**
    - A one-shot held-out limit controls evaluation timing, not exploration.
      Freeze only when the result is trustworthy and `state.md` explains why
      neither internal work nor an external direction is likely to produce a
      large gain. An explicit terminal target or human stop may end sooner;
      crossing a reference score alone does not end budgeted maximization.
    - Compute limits execution, not scientific imagination, and need not be
      depleted. Useful remaining compute plus a plausible large-gain test means
      continue. A verified resource limit may narrow the fair test but must not
      become a scientific rejection.
    - If the frozen method retrains on all data or changes checkpoints, code,
      preprocessing, or inference from the validated path, run a train-only
      final-path canary. It proves technical equivalence only and cannot replace
      validation, folds, seeds, or ensembles; prefer the validated ensemble when
      all-data equivalence is uncertain.
    - Record a justified freeze in `trajectory.md`, then `state.md`, then
      dashboard readiness. Pass the strict checker before protected/final
      evaluation. Record completion through the same owner-to-state order and
      end the heartbeat only on freeze/completion or human pause/stop.
