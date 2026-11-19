#!/usr/bin/env python3
"""Call an external LLM critic for a MIAgent challenge's research direction.

The script reads phase-appropriate challenge evidence, then asks the configured
critic model for a harsh, actionable critique. It writes a full report under
challenge/<name>/critics/ and can append a compact pointer to candidates.md.
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
import os
import pathlib
import textwrap
import urllib.error
import urllib.request
from typing import Any, Dict, Iterable, List, Optional

try:
    import yaml
except ImportError:  # pragma: no cover
    yaml = None


DEFAULT_PROFILE = "skills/compute/profiles/example.yaml"
DEFAULT_PROVIDER = "nvidia_claude"
DEFAULT_SYSTEM_PROMPT = """You are a harsh external research critic for a medical-imaging challenge agent.

Your job is to attack the current plan, baselines, and experiments, not to be encouraging.
Be direct, skeptical, and specific. Criticize unsupported assumptions, weak
baselines, missing data/evaluator checks, leakage risks, challenge-rule risks,
pretrained-model licensing or label-contract risks, metric mismatch, vague
experiment scope, overinterpreted results, wasted compute, and missing kill rules.
For initial discovery, compare the preserved Independent Scientific Thesis,
Open Research Findings, Revised Scientific Direction, and candidates. Attack
whether research actually tested the thesis or merely replaced model intuition
with the easiest well-cited pipeline. Conversely, identify decisive current
evidence the thesis missed: exact-task winners, stronger recent successors,
relevant general or domain foundation models, usable official implementations
or weights, applicable repository skills, external data, or leakage and license
risks. Do not require a fixed search taxonomy, candidate quota, or extra logs.
Treat a strongest/latest claim as unsupported when the research did not test the
exact task or dataset and its immediate predecessor-to-successor chain through
the current date.

Initial discovery intentionally precedes implementation and experiments. Do not
criticize their absence or demand that they occur before candidate selection;
route runnable, evaluator, data, and compute uncertainties into next-phase
checks. Missing pretrained weights is not by itself a hard blocker when an
official trainable implementation exists and measured compute has not shown the
reconstruction infeasible.

Demand primary-source support for claims that drive the choice and a credible
complete pipeline for the selected direction. Distinguish a justified
evidence-led replacement from anchoring on published methods. Check that the
post-search audit records concrete findings rather than checkmarks, but do not
assume every audit area must supply a candidate. Missing packages, uncached
weights, setup time, and implementation difficulty are not scientific reasons
to prefer a weaker method.

Separate scientific preference from execution convenience. Attack any selected
direction that is merely the easiest installed control, any generic pretrained
family that was never composed into an actionable end-to-end candidate, and
any scratch or older substrate lacking a current pretrained near-drop-in
comparator. Require each serious candidate to be one complete committed
composition rather than a control with optional promotions. If the running
direction differs from the scientifically strongest unblocked candidate, treat
it only as a diagnostic control and require reconsideration of the selection;
setup-risk language is not a scientific blocker.
Also attack novelty theater: extra components without causal roles, unverified
critical assets, or a newer backbone with no credible complete-pipeline
advantage over the strongest reproducible exact/close-task method.

For external-loop re-entry, use the current state, decision trajectory, and
experiment evidence to attack whether the new search addresses the observed
plateau. Reject repeated candidates that do not offer a credible escape from
the established failure mode.

Check independent risk areas before synthesizing:
- task/evaluator: task contract, metric, ranking, submission, rules;
- data: access, splits, labels, leakage, preprocessing assumptions;
- literature: source coverage, source quality, novelty, code evidence;
- method: baseline recipes, component choices, transfer risk;
- experiment/reproducibility: run contracts, gates, reproducibility locks,
  success rules, kill rules, analysis validity.

Evaluator parity, output format, packaging, environment, and scheduling are
operational checks, not scientific literature components. Critique their
scientific implications inside the affected prediction component and route
their verification to the task or execution artifacts.

Do not invent metrics, citations, or job states. Do not claim you ran code.
Do not directly approve, select, promote, demote, pause, kill, or reprioritize a
candidate or job. Challenge comparative reasoning and state what evidence would
change it; the main agent owns the scientific decision. You provide soft
critique for the human/Codex loop to consider.

Return Markdown with these sections:
1. Brutal Summary
2. Risk-Area Findings
3. Highest-Risk Flaws
4. Baseline-And-Experiment Critique
5. Missing Evidence And Required Checks
6. Revise/Verify Recommendations (use kill/postpone only after linked experiment evidence warrants it)
7. Questions The Human Must Answer
8. What Would Change Your Mind
"""

INITIAL_DISCOVERY_CRITIC_ADDENDUM = """
For this INITIAL DISCOVERY pass, override the general report outline above.
Return only:
1. Scientific Summary
2. Missing Or Weak Decision Evidence
3. Thesis-To-Research Reasoning Risks
4. Candidate Composition Risks
5. Next-Phase Verification Gates
6. What Would Change The Concerns

Do not include a baseline/experiment critique, kill/reprioritization advice, or
questions for the human merely because implementation has not started. Do not
recommend selecting, promoting, or demoting any candidate. The main agent will
decide how the evidence affects selection.
"""


def main() -> None:
    args = parse_args()
    challenge_dir = pathlib.Path(args.challenge).expanduser().resolve()
    if challenge_dir.is_file():
        challenge_dir = challenge_dir.parent
    profile = load_profile(pathlib.Path(args.profile).expanduser())
    provider = get_provider(profile, args.provider)

    endpoint = args.endpoint or provider.get("endpoint")
    model = args.model or provider.get("model")
    if not endpoint or not model:
        raise SystemExit("Missing endpoint or model. Configure the profile or pass CLI flags.")

    api_key = resolve_api_key(provider, args.api_key_env, args.api_key_file)
    initial_discovery = is_initial_discovery(challenge_dir, args.experiment_file)
    context = build_context(
        challenge_dir,
        args.experiment_file,
        args.max_chars,
        initial_discovery=initial_discovery,
    )
    messages = build_messages(context, args.extra_instruction, initial_discovery)
    request_body = {
        "model": model,
        "messages": messages,
        "max_tokens": args.max_tokens or provider.get("default_max_tokens", 4096),
        "temperature": args.temperature
        if args.temperature is not None
        else provider.get("default_temperature", 0.2),
    }

    if args.dry_run:
        print(json.dumps(redacted_request(endpoint, request_body, provider), indent=2))
        return

    if not api_key:
        raise SystemExit(
            "Missing API key. Set the configured env var or write the configured api_key_file."
        )

    response = call_chat_completion(endpoint, api_key, request_body, args.timeout)
    critique = extract_text(response)
    if not critique.strip():
        raise SystemExit("Critic response did not contain text.")

    report_path = write_report(challenge_dir, provider, model, critique, context)
    if args.append_candidates or args.append_ideas:
        append_critic_pointer(challenge_dir / "candidates.md", provider, report_path, critique)
    print(report_path)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run a harsh external critic on MIAgent candidates and baselines.")
    parser.add_argument("challenge", help="Challenge directory or path inside it.")
    parser.add_argument("--profile", default=DEFAULT_PROFILE, help="Compute profile YAML.")
    parser.add_argument("--provider", default=DEFAULT_PROVIDER, help="external_llm_critics provider key.")
    parser.add_argument("--endpoint", default=None, help="Override chat completions endpoint.")
    parser.add_argument("--model", default=None, help="Override model name.")
    parser.add_argument("--api-key-env", default=None, help="Override API key environment variable.")
    parser.add_argument("--api-key-file", default=None, help="Override API key file.")
    parser.add_argument(
        "--experiment-file",
        action="append",
        default=[],
        help="Specific experiment record to critique.",
    )
    parser.add_argument("--extra-instruction", default="", help="Extra critic instruction.")
    parser.add_argument("--max-chars", type=int, default=60000, help="Maximum context characters to send.")
    parser.add_argument("--max-tokens", type=int, default=None, help="Response max tokens.")
    parser.add_argument("--temperature", type=float, default=None, help="Sampling temperature.")
    parser.add_argument("--timeout", type=int, default=120, help="HTTP timeout seconds.")
    parser.add_argument("--append-candidates", action="store_true", help="Append a compact pointer to candidates.md.")
    parser.add_argument("--append-ideas", action="store_true", help="Alias for --append-candidates.")
    parser.add_argument("--dry-run", action="store_true", help="Print redacted request context without calling the API.")
    return parser.parse_args()


def load_profile(path: pathlib.Path) -> Dict[str, Any]:
    if not path.is_absolute():
        path = pathlib.Path.cwd() / path
    if not path.exists():
        raise SystemExit(f"Profile not found: {path}")
    if yaml is None:
        raise SystemExit("PyYAML is required to read compute profile YAML.")
    with path.open("r", encoding="utf-8") as f:
        data = yaml.safe_load(f) or {}
    if not isinstance(data, dict):
        raise SystemExit(f"Profile must be a YAML object: {path}")
    return data


def get_provider(profile: Dict[str, Any], provider_name: str) -> Dict[str, Any]:
    providers = profile.get("external_llm_critics") or {}
    provider = providers.get(provider_name)
    if not isinstance(provider, dict):
        names = ", ".join(sorted(providers)) or "none"
        raise SystemExit(f"Provider {provider_name!r} not found. Available: {names}")
    return provider


def resolve_api_key(
    provider: Dict[str, Any],
    api_key_env_override: Optional[str],
    api_key_file_override: Optional[str],
) -> str:
    env_name = api_key_env_override or provider.get("api_key_env")
    if env_name:
        value = os.environ.get(str(env_name), "").strip()
        if value:
            return value
    key_file = api_key_file_override or provider.get("api_key_file")
    if key_file:
        path = pathlib.Path(str(key_file)).expanduser()
        if path.exists():
            return path.read_text(encoding="utf-8").strip()
    return ""


def build_context(
    challenge_dir: pathlib.Path,
    experiment_file_args: Iterable[str],
    max_chars: int,
    *,
    initial_discovery: bool = False,
) -> str:
    parts: List[str] = []
    add_file(parts, challenge_dir / "challenge.md", "CHALLENGE")
    if not initial_discovery:
        add_file(parts, challenge_dir / "state.md", "CURRENT RESEARCH STATE")
        add_file(parts, challenge_dir / "trajectory.md", "DECISION TRAJECTORY")
        add_file(parts, challenge_dir / "dashboard.md", "LIVE EXECUTION DASHBOARD")
    add_file(parts, challenge_dir / "candidates.md", "CANDIDATES")
    add_file(parts, challenge_dir / "literature.md", "LITERATURE")
    explicit = [pathlib.Path(p).expanduser() for p in experiment_file_args]
    if initial_discovery:
        experiment_files = []
    elif explicit:
        experiment_files = explicit
    else:
        experiment_files = []
        experiment_files.extend(sorted(challenge_dir.glob("baselines/*/baseline.md")))
        experiment_files.extend(sorted(challenge_dir.glob("baselines/*/runs/exp*/experiment.md")))
        experiment_files.extend(sorted(challenge_dir.glob("baselines/*/exp*/experiment.md")))  # legacy layout

    for path in experiment_files:
        if not path.is_absolute():
            path = (pathlib.Path.cwd() / path).resolve()
        if path.name == "baseline.md":
            add_file(parts, path, f"BASELINE: {path.parent.name}")
            continue
        title = f"EXPERIMENT: {path.name} ({path.parent.name})"
        add_file(parts, path, title)

    context = "\n\n".join(parts)
    if len(context) > max_chars:
        context = context[:max_chars] + "\n\n[TRUNCATED: context exceeded max_chars]\n"
    return context


def is_initial_discovery(
    challenge_dir: pathlib.Path,
    experiment_file_args: Iterable[str],
) -> bool:
    if list(experiment_file_args):
        return False
    actual_baselines = [
        path
        for path in challenge_dir.glob("baselines/*/baseline.md")
        if path.parent.name != "baseline_template"
    ]
    experiments = list(challenge_dir.glob("baselines/*/runs/exp*/experiment.md"))
    experiments.extend(challenge_dir.glob("baselines/*/exp*/experiment.md"))
    return not actual_baselines and not experiments


def add_file(parts: List[str], path: pathlib.Path, title: str) -> None:
    if not path.exists():
        parts.append(f"## {title}\n\nMissing: {path}")
        return
    text = path.read_text(encoding="utf-8", errors="replace")
    parts.append(f"## {title}\n\nPath: {path}\n\n{text}")


def build_messages(
    context: str,
    extra_instruction: str,
    initial_discovery: bool = False,
) -> List[Dict[str, str]]:
    phase_instruction = ""
    if initial_discovery:
        phase_instruction = """PHASE: INITIAL DISCOVERY. The workflow deliberately forbids implementation,
data/evaluator execution, baseline plans, and experiments until after candidate
selection. Their absence is expected, not a flaw, blocker, or human question.
State those items only as concise next-phase verification gates when relevant.
Critique the scientific thesis, research, synthesis, and candidate decision."""
    scope_instruction = (
        "Be harsh about vague or unsupported scientific claims and candidate compositions."
        if initial_discovery
        else "Be harsh. Treat vague or unsupported baselines/experiments as failures."
    )
    user = f"""Criticize the current medical-imaging challenge candidates, baseline direction, and runs below.

{scope_instruction} If this is a smoke test or simulation, explicitly criticize
any risk that fake numbers or mock state could leak into real decision-making.

{phase_instruction}

{extra_instruction.strip()}

<challenge_context>
{context}
</challenge_context>
"""
    system_prompt = DEFAULT_SYSTEM_PROMPT
    if initial_discovery:
        system_prompt += INITIAL_DISCOVERY_CRITIC_ADDENDUM
    return [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": user},
    ]


def call_chat_completion(
    endpoint: str,
    api_key: str,
    request_body: Dict[str, Any],
    timeout: int,
) -> Dict[str, Any]:
    data = json.dumps(request_body).encode("utf-8")
    req = urllib.request.Request(
        endpoint,
        data=data,
        headers={
            "Content-Type": "application/json",
            "Authorization": f"Bearer {api_key}",
        },
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout) as response:
            raw = response.read().decode("utf-8")
    except urllib.error.HTTPError as exc:
        body = exc.read().decode("utf-8", errors="replace")
        raise SystemExit(f"HTTP {exc.code} from critic endpoint: {body}") from exc
    return json.loads(raw)


def extract_text(response: Dict[str, Any]) -> str:
    choices = response.get("choices") or []
    if not choices:
        return ""
    message = choices[0].get("message") or {}
    content = message.get("content", "")
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        chunks = []
        for item in content:
            if isinstance(item, dict):
                chunks.append(str(item.get("text") or item.get("content") or ""))
            else:
                chunks.append(str(item))
        return "\n".join(chunks)
    return str(content)


def write_report(
    challenge_dir: pathlib.Path,
    provider: Dict[str, Any],
    model: str,
    critique: str,
    context: str,
) -> pathlib.Path:
    out_dir = challenge_dir / "critics"
    out_dir.mkdir(parents=True, exist_ok=True)
    stamp = dt.datetime.now().strftime("%Y%m%d_%H%M%S")
    provider_name = safe_slug(str(provider.get("display_name") or "external_critic"))
    report_path = out_dir / f"{stamp}_{provider_name}.md"
    body = f"""# External Critic Report

| Field | Value |
|---|---|
| generated at | {dt.datetime.now().isoformat(timespec="seconds")} |
| provider | {provider.get("display_name", "unknown")} |
| model | `{model}` |
| context characters | {len(context)} |

{critique.strip()}
"""
    report_path.write_text(body, encoding="utf-8")
    return report_path


def append_critic_pointer(
    candidates_path: pathlib.Path,
    provider: Dict[str, Any],
    report_path: pathlib.Path,
    critique: str,
) -> None:
    if not candidates_path.exists():
        return
    text = candidates_path.read_text(encoding="utf-8")
    date = dt.date.today().isoformat()
    critic = str(provider.get("display_name") or "external critic")
    summary = summarize_critique_for_table(critique)
    rel_path = report_path.relative_to(candidates_path.parent)
    row = f"| {date} | {critic} | {escape_table(summary)} | `{rel_path}` | pending |\n"
    heading = "## External Critic Reviews"
    if heading not in text:
        text += f"\n\n{heading}\n\n| Date | Critic | Main objection | Report | Decision |\n|---|---|---|---|---|\n"
    text += row
    candidates_path.write_text(text, encoding="utf-8")


def summarize_critique_for_table(critique: str) -> str:
    lines = [line.strip(" -*#\t") for line in critique.splitlines()]
    lines = [line for line in lines if line]
    joined = " ".join(lines[:4])
    return textwrap.shorten(joined, width=220, placeholder="...")


def critic_detail_entry(date: str, critic: str, rel_path: pathlib.Path, critique: str) -> str:
    key_objections = extract_key_objections(critique)
    return f"""
### {date} Critic Review

**Critic**: {critic}

**Report path**: `{rel_path}`

**Key objections**:

{key_objections}

**Suggestions to accept**:

- pending Codex response

**Suggestions to reject or defer**:

- pending Codex response

**Codex response / idea regeneration**:

- pending Codex response
"""


def extract_key_objections(critique: str, max_items: int = 8) -> str:
    lines = []
    for raw in critique.splitlines():
        line = raw.strip()
        if not line:
            continue
        if line.startswith(("#", "|", "```")):
            continue
        line = line.lstrip("-*0123456789. \t")
        if len(line) < 20:
            continue
        lines.append(textwrap.shorten(line, width=240, placeholder="..."))
        if len(lines) >= max_items:
            break
    if not lines:
        return "- No concise objections extracted; see report path."
    return "\n".join(f"- {line}" for line in lines)


def escape_table(value: str) -> str:
    return value.replace("|", "\\|").replace("\n", " ")


def safe_slug(value: str) -> str:
    out = []
    for ch in value.lower():
        if ch.isalnum():
            out.append(ch)
        elif ch in {" ", "-", "_", ".", "/"}:
            out.append("_")
    slug = "".join(out).strip("_")
    while "__" in slug:
        slug = slug.replace("__", "_")
    return slug or "external_critic"


def redacted_request(
    endpoint: str,
    request_body: Dict[str, Any],
    provider: Dict[str, Any],
) -> Dict[str, Any]:
    return {
        "endpoint": endpoint,
        "provider": provider.get("display_name"),
        "api_key": "<redacted>",
        "request_body": request_body,
    }


if __name__ == "__main__":
    main()
