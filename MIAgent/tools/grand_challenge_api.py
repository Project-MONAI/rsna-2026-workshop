#!/usr/bin/env python3
"""Small Grand Challenge API helper.

Loads a personal token from GRAND_CHALLENGE_TOKEN, GRAND_CHALLENGE_AUTHORIZATION,
or ~/.config/miagent/grand_challenge.env. Never prints the token.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path


API_BASE = "https://grand-challenge.org/api/v1/"
TOKEN_FILE = Path.home() / ".config" / "miagent" / "grand_challenge.env"


def load_token() -> str:
    for name in ("GRAND_CHALLENGE_TOKEN", "GRAND_CHALLENGE_AUTHORIZATION"):
        value = os.environ.get(name)
        if value:
            return value.strip().split()[-1]
    if TOKEN_FILE.exists():
        for line in TOKEN_FILE.read_text(encoding="utf-8").splitlines():
            if line.startswith("GRAND_CHALLENGE_TOKEN="):
                return line.split("=", 1)[1].strip().split()[-1]
            if line.startswith("GRAND_CHALLENGE_AUTHORIZATION="):
                return line.split("=", 1)[1].strip().split()[-1]
    raise SystemExit(
        "Missing Grand Challenge token. Set GRAND_CHALLENGE_TOKEN or create "
        f"{TOKEN_FILE} with GRAND_CHALLENGE_TOKEN=<token>."
    )


def api_get(path: str, params: dict[str, str] | None = None) -> object:
    token = load_token()
    url = urllib.parse.urljoin(API_BASE, path)
    if params:
        url = f"{url}?{urllib.parse.urlencode(params)}"
    req = urllib.request.Request(
        url,
        headers={
            "Accept": "application/json",
            "Authorization": f"BEARER {token}",
            "User-Agent": "MIAgent-grand-challenge-api/3.0",
        },
    )
    with urllib.request.urlopen(req, timeout=60) as response:
        return json.loads(response.read().decode("utf-8"))


def html_probe(url: str) -> dict[str, object]:
    token = load_token()
    results: dict[str, object] = {}
    for prefix in ("BEARER", "Bearer", "Token"):
        req = urllib.request.Request(
            url,
            headers={
                "Authorization": f"{prefix} {token}",
                "User-Agent": "MIAgent-grand-challenge-api/3.0",
            },
        )
        try:
            with urllib.request.urlopen(req, timeout=30) as response:
                results[prefix] = {"status": "ok", "bytes": len(response.read())}
        except urllib.error.HTTPError as exc:
            results[prefix] = {"status": "http_error", "code": exc.code}
        except Exception as exc:  # noqa: BLE001 - diagnostic command
            results[prefix] = {"status": "error", "type": type(exc).__name__}
    return results


def command_self(_: argparse.Namespace) -> object:
    return api_get("profiles/users/self/")


def command_challenge(args: argparse.Namespace) -> object:
    return api_get(f"challenges/{args.slug}/")


def command_evaluations(args: argparse.Namespace) -> object:
    data = api_get("evaluations/", {"limit": str(args.limit), "offset": str(args.offset)})
    short_name = args.challenge_short_name
    if short_name:
        data["results"] = [
            row
            for row in data.get("results", [])
            if row.get("submission", {})
            .get("phase", {})
            .get("challenge", {})
            .get("short_name")
            == short_name
        ]
    return data


def command_html_probe(args: argparse.Namespace) -> object:
    return {"url": args.url, "auth_header_probe": html_probe(args.url)}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(required=True)

    self_cmd = sub.add_parser("self", help="Verify the authenticated account.")
    self_cmd.set_defaults(func=command_self)

    challenge_cmd = sub.add_parser("challenge", help="Fetch challenge metadata by slug.")
    challenge_cmd.add_argument("slug")
    challenge_cmd.set_defaults(func=command_challenge)

    eval_cmd = sub.add_parser("evaluations", help="Fetch recent evaluations.")
    eval_cmd.add_argument("--limit", type=int, default=20)
    eval_cmd.add_argument("--offset", type=int, default=0)
    eval_cmd.add_argument("--challenge-short-name")
    eval_cmd.set_defaults(func=command_evaluations)

    html_cmd = sub.add_parser("html-probe", help="Check whether API token opens an HTML page.")
    html_cmd.add_argument("url")
    html_cmd.set_defaults(func=command_html_probe)

    args = parser.parse_args()
    print(json.dumps(args.func(args), indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
