#!/usr/bin/env bash
set -euo pipefail

usage() {
  cat <<'USAGE'
Validate that a ReX-MLE Codex process produced a genuine challenge completion.

Usage:
  benchmark/submission/validate_rex_mle_completion.sh TASK [--version VERSION]
USAGE
}

if (($# < 1)); then
  usage >&2
  exit 2
fi

task_id=$1
shift
version=v3.5

while (($#)); do
  case "$1" in
    --version) version=${2:?missing value for --version}; shift 2 ;;
    -h|--help) usage; exit 0 ;;
    *) printf 'Unknown argument: %s\n' "$1" >&2; exit 2 ;;
  esac
done

if [[ ! "$task_id" =~ ^[A-Za-z0-9._-]+$ ]] ||
   [[ ! "$version" =~ ^[A-Za-z0-9._-]+$ ]]; then
  printf '%s\n' 'TASK and VERSION contain unsupported characters' >&2
  exit 2
fi

repo_root=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/../.." && pwd)
final_path="$repo_root/benchmark/submission/.runs/rex_task_${version}_${task_id}_nbhel/final.txt"
challenge_dir="$repo_root/challenge/ReX-MLE_${version}_${task_id}"
dashboard_path="$challenge_dir/dashboard.md"

if [[ ! -s "$final_path" ]]; then
  printf 'Completion validation failed for %s: missing final response\n' "$task_id" >&2
  exit 1
fi
if ! rg -qi '^completed\b' "$final_path"; then
  printf 'Completion validation failed for %s: final response is not Completed\n' "$task_id" >&2
  exit 1
fi
if [[ ! -s "$dashboard_path" ]]; then
  printf 'Completion validation failed for %s: missing dashboard.md\n' "$task_id" >&2
  exit 1
fi
if ! rg -qi 'official.*(private|protected)|(private|protected).*official' \
  "$final_path" "$dashboard_path"; then
  printf 'Completion validation failed for %s: no official protected-evaluation evidence\n' \
    "$task_id" >&2
  exit 1
fi
if ! find "$challenge_dir" -type f \
  \( -iname '*official*eval*.json' -o -iname '*private*eval*.json' \
     -o -path '*official_private_eval*/report.json' \) -print -quit | rg -q .; then
  printf 'Completion validation failed for %s: no official evaluation result artifact\n' \
    "$task_id" >&2
  exit 1
fi

python3 "$repo_root/tools/check_consistency.py" --strict "$challenge_dir"
printf 'Validated genuine ReX-MLE completion: %s\n' "$task_id"
