#!/usr/bin/env bash
set -euo pipefail

readonly ALL_TASKS=(
  dentex
  isles22
  ldct-iqa
  neurips-cellseg
  puma-track1-task1
  puma-track1-task2
  puma-track2-task1
  puma-track2-task2
  seg_a
  topbrain-track1
  topbrain-track2
  topcow-track1-task1
  topcow-track1-task2
  topcow-track1-task3
  topcow-track2-task1
  topcow-track2-task2
  topcow-track2-task3
  usenhance
)

usage() {
  cat <<'USAGE'
Submit independent ReX-MLE Codex sessions configured for nb-hel.

Usage:
  benchmark/submission/submit_rex_mle_nbhel.sh TASK... [options]
  benchmark/submission/submit_rex_mle_nbhel.sh --all [options]

Options:
  --all                 Use every prepared ReX-MLE benchmark task
  --version VERSION     Session version (default: v3.5)
  --max-parallel N      Concurrent Codex processes (default: 4)
  --model MODEL         Codex model (default inherited from submit.sh)
  --reasoning EFFORT    Reasoning effort (default inherited from submit.sh)
  --dry-run             Render prompts only (default)
  --submit              Start Codex processes
  -h, --help            Show this help

Examples:
  benchmark/submission/submit_rex_mle_nbhel.sh usenhance --dry-run
  benchmark/submission/submit_rex_mle_nbhel.sh usenhance --submit
  benchmark/submission/submit_rex_mle_nbhel.sh --all --submit
USAGE
}

submission_dir=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)
version="v3.5"
max_parallel=4
submit=0
all=0
tasks=()
forwarded=()

while (($#)); do
  case "$1" in
    --all) all=1; shift ;;
    --version) version=${2:?missing value for --version}; shift 2 ;;
    --max-parallel) max_parallel=${2:?missing value for --max-parallel}; shift 2 ;;
    --model|--reasoning)
      forwarded+=("$1" "${2:?missing value for $1}")
      shift 2
      ;;
    --submit) submit=1; shift ;;
    --dry-run) submit=0; shift ;;
    -h|--help) usage; exit 0 ;;
    --*) printf 'Unknown option: %s\n\n' "$1" >&2; usage >&2; exit 2 ;;
    *) tasks+=("$1"); shift ;;
  esac
done

if ((all)) && ((${#tasks[@]})); then
  printf '%s\n' 'Use either --all or explicit task IDs, not both.' >&2
  exit 2
fi
if ((all)); then
  tasks=("${ALL_TASKS[@]}")
fi
if ((${#tasks[@]} == 0)); then
  usage >&2
  exit 2
fi
if [[ ! "$max_parallel" =~ ^[1-9][0-9]*$ ]]; then
  printf '%s\n' '--max-parallel must be a positive integer' >&2
  exit 2
fi

run_one() {
  local task_id=$1
  local action=--dry-run
  if ((submit)); then
    action=--submit
  fi
  "$submission_dir/submit.sh" rex-mle "$task_id" \
    --cluster nb-hel \
    --version "$version" \
    "$action" \
    ${forwarded[@]+"${forwarded[@]}"}
  if ((submit)); then
    "$submission_dir/sync_rex_mle_nbhel.sh" "$task_id" \
      --work-version "$version"
    "$submission_dir/validate_rex_mle_completion.sh" "$task_id" \
      --version "$version"
  fi
}

if ((!submit)); then
  for task_id in "${tasks[@]}"; do
    run_one "$task_id"
  done
  exit 0
fi

pids=()
task_for_pid=()
failures=0

reap_batch() {
  local i
  for ((i = 0; i < ${#pids[@]}; i++)); do
    if ! wait "${pids[$i]}"; then
      printf 'Codex session failed for task %s\n' "${task_for_pid[$i]}" >&2
      failures=$((failures + 1))
    fi
  done
  pids=()
  task_for_pid=()
}

for task_id in "${tasks[@]}"; do
  run_one "$task_id" &
  pids+=("$!")
  task_for_pid+=("$task_id")
  if ((${#pids[@]} >= max_parallel)); then
    reap_batch
  fi
done
reap_batch

if ((failures)); then
  printf '%d Codex session(s) failed.\n' "$failures" >&2
  exit 1
fi
