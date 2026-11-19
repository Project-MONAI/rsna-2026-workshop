# MIAgent Codex Harness

Use these instructions whenever Codex works in this repository.

## Route

Handle ordinary repository tasks normally. For pretrained inference requests,
first follow `skills/general/inference/SKILL.md` and the selected model's skill.
Do not create a challenge or start the challenge workflow unless training,
fine-tuning, benchmarking, or evaluation is explicitly requested.

For any medical-imaging challenge,
dataset, benchmark, leaderboard, or experiment request, first read and follow:

```text
skills/orchestration/challenge_run_workflow.md
```

That workflow is the complete operating contract for challenge work: scientific
reasoning, research objects, human gates, continuous execution, context refresh,
artifact updates, and handoff. Do not run a challenge from `AGENTS.md` alone.

## Repository Roles

- `AGENTS.md` routes Codex into the correct repository workflow.
- `skills/orchestration/challenge_run_workflow.md` owns challenge behavior and
  phase order.
- `challenge/challenge_template/` owns each artifact's scope, fields, and update
  discipline. Filled artifacts remain governed by their raw templates.
- `skills/` owns specialized analysis, implementation, and compute techniques.
- The filled challenge folder owns the durable task evidence and trajectory;
  chat history does not.

Keep each rule in its narrowest authoritative owner. At points of use, reference
that owner instead of copying its instructions into another layer.
