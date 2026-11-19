<!-- miagent-template-source: challenge/challenge_template/critics/README.md -->
<!-- miagent-template-contract: active; keep the miagent-template-source loaded for creation/material updates; reload after resume or compaction -->
# Critics

External critic reports live here.

The critic checks whether open research genuinely challenged the preserved
independent thesis; it does not choose the solution or impose a search taxonomy.
It should expose a missed stronger method, convenience-driven control, unsupported
replacement of model intuition, unverified critical asset, or novelty theater.

During initial discovery, run it after the Independent Scientific Thesis, Open
Research Findings, Revised Scientific Direction, coverage audit, and draft
candidates exist. Run it again after targeted external-loop research. Summarize
accepted and rejected points in `literature.md`; revise the direction or
candidates only when the objection changes the scientific judgment.

If the configured critic provider fails, use a fresh critic subagent with only
the discovery artifacts. If delegation is unavailable, save a dedicated
self-critique report. A timeout or provider error alone does not complete the
critic gate.

Run for initial discovery:

```text
python3 tools/critic_ideas.py challenge/<name>
```

For later advisory critiques, optionally append a pointer:

```text
python3 tools/critic_ideas.py challenge/<name> --append-candidates
```

For an external-loop review, use `--extra-instruction` to name the state issue
or plateau that triggered the new search.
