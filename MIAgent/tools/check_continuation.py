#!/usr/bin/env python3
"""Read-only validation for an active challenge's durable continuation record."""
from __future__ import annotations

import argparse
import json
import re
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent.parent
ACTION_MARKERS = ("<!-- next-concrete-action: begin -->", "<!-- next-concrete-action: end -->")
CONTRACT_MARKERS = ("<!-- continuation-contract: begin -->", "<!-- continuation-contract: end -->")
DECISION_MARKERS = ("<!-- current-decision-record: begin -->", "<!-- current-decision-record: end -->")
REQUIRED_FIELDS = ("Evidence reviewed", "Current decision", "Next concrete action", "Owner", "Next monitoring time", "Disposition")


def block(text: str, markers: tuple[str, str]) -> str | None:
    if markers[0] not in text or markers[1] not in text:
        return None
    value = text.split(markers[0], 1)[1].split(markers[1], 1)[0].strip()
    return value or None


def load_jobs(challenge: Path) -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []
    for path in sorted(challenge.glob("baselines/*/runs/*/job.json")):
        try:
            record = json.loads(path.read_text())
        except (OSError, json.JSONDecodeError):
            records.append({"path": path, "state": "invalid"})
            continue
        if isinstance(record, dict):
            record["path"] = path
            records.append(record)
    return records


def check(challenge: Path) -> dict[str, Any]:
    dashboard_path, state_path = challenge / "dashboard.md", challenge / "state.md"
    errors: list[str] = []
    warnings: list[str] = []
    if not dashboard_path.is_file() or not state_path.is_file():
        return {"ok": False, "errors": ["missing dashboard.md or state.md"], "warnings": warnings, "jobs": {}}
    dashboard, state = dashboard_path.read_text(), state_path.read_text()
    action = block(dashboard, ACTION_MARKERS)
    contract = block(dashboard, CONTRACT_MARKERS)
    decision = block(state, DECISION_MARKERS)
    if not action:
        errors.append("dashboard is missing a non-empty next concrete action")
    if not contract:
        errors.append("dashboard is missing a non-empty Continuation Contract")
    else:
        for field in REQUIRED_FIELDS:
            if not re.search(rf"^\|\s*{re.escape(field)}\s*\|\s*[^|\n]+\|", contract, re.MULTILINE):
                errors.append(f"Continuation Contract missing populated field: {field}")
    if not decision:
        errors.append("state.md is missing a non-empty Current Decision Record")
    records = load_jobs(challenge)
    active = [record for record in records if record.get("state") in {"queued", "running"}]
    terminal = [record for record in records if record.get("state") in {"completed", "failed", "exited_unverified"}]
    if active and action:
        names = [str(record.get("experiment", "")) for record in active]
        if not any(name and name in action for name in names):
            errors.append("next concrete action does not name an active or queued experiment")
    if terminal:
        newest = max(terminal, key=lambda record: str(record.get("finished_at", record.get("queued_at_utc", ""))))
        if not (Path(newest["path"]).parent / "summary.md").is_file():
            warnings.append(f"latest terminal experiment lacks summary.md: {newest.get('experiment', Path(newest['path']).parent.name)}")
    if "| Run state | active |" in dashboard and not active and contract and not any(token in contract.lower() for token in ("codex-owned", "human-owned blocker", "stop decision")):
        errors.append("active challenge has neither a live job nor a valid Codex/human/stop disposition")
    return {"ok": not errors, "errors": errors, "warnings": warnings, "jobs": {"active": [record.get("experiment") for record in active], "terminal": [record.get("experiment") for record in terminal]}}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("challenge", help="Challenge name or challenge directory")
    args = parser.parse_args()
    supplied = Path(args.challenge)
    challenge = supplied.resolve() if supplied.is_dir() else ROOT / "challenge" / args.challenge
    result = check(challenge)
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0 if result["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
