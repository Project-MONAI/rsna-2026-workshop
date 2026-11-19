#!/usr/bin/env bash
set -euo pipefail

script_dir="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
export OPENCODE_ENABLE_EXA=1

model="${OPENCODE_MODEL:-miagent-llm/Qwen/Qwen3.8-27B-FP8}"
api_base="${MIAgent_LLM_API_BASE_URL:-http://llm:8000/v1}"
api_key="${MIAgent_LLM_API_KEY:-local}"

if ! command -v opencode >/dev/null 2>&1; then
  echo "opencode is not available. Run this script from the MIAgent VS Code web terminal." >&2
  exit 1
fi

if [[ -z "$api_key" ]]; then
  echo "The active LLM endpoint has no API key configured." >&2
  exit 1
fi

if ! curl -fsS --max-time 15 -H "Authorization: Bearer ${api_key}" "${api_base%/}/models" >/dev/null; then
  echo "The configured LLM endpoint is unavailable or rejected its API key: ${api_base}" >&2
  exit 1
fi

exec opencode "$script_dir" --model "$model" --auto
