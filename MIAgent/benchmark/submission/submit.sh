#!/usr/bin/env bash
set -euo pipefail

usage() {
  cat <<'USAGE'
Render or submit one editable MIAgent benchmark prompt.

Usage:
  benchmark/submission/submit.sh BENCHMARK TASK [options]

Benchmarks:
  camyla       CamylaBench; defaults to 8 GPUs and 8 wall-clock hours
  rex-mle      ReX-MLE; defaults to 8 GPUs and 24 total training GPU-hours

Options:
  --version VERSION       Session and workspace version (default: v3.5)
  --cluster CLUSTER       Compute cluster: dfw or nb-hel (default: dfw)
  --max-gpus N            Maximum concurrent GPUs (default: 8)
  --wall-hours HOURS      CamylaBench wall-clock budget (default: 8)
  --gpu-hours HOURS       ReX-MLE training GPU-hour budget (default: 24)
  --model MODEL           Codex model (default: gpt-5.5)
  --reasoning EFFORT      Codex reasoning effort (default: xhigh)
  --submit                Launch Codex after rendering
  --dry-run               Render and print without launching (default)
  -h, --help              Show this help

Examples:
  benchmark/submission/submit.sh camyla 907 --version v3.5 --dry-run
  benchmark/submission/submit.sh rex-mle puma-track2-task2 --version v3.5 --dry-run
  benchmark/submission/submit.sh rex-mle puma-track2-task2 --version v3.5 --submit
  benchmark/submission/submit.sh rex-mle usenhance --version v3.5 \
    --cluster nb-hel --submit
USAGE
}

if (($# == 1)) && [[ "$1" == "-h" || "$1" == "--help" ]]; then
  usage
  exit 0
fi
if (($# < 2)); then
  usage >&2
  exit 2
fi

benchmark=$1
task_id=$2
shift 2

version="v3.5"
cluster="dfw"
max_gpus="8"
wall_hours="8"
gpu_hours="24"
model="gpt-5.5"
reasoning="xhigh"
submit=0

while (($#)); do
  case "$1" in
    --version) version=${2:?missing value for --version}; shift 2 ;;
    --cluster) cluster=${2:?missing value for --cluster}; shift 2 ;;
    --max-gpus) max_gpus=${2:?missing value for --max-gpus}; shift 2 ;;
    --wall-hours) wall_hours=${2:?missing value for --wall-hours}; shift 2 ;;
    --gpu-hours) gpu_hours=${2:?missing value for --gpu-hours}; shift 2 ;;
    --model) model=${2:?missing value for --model}; shift 2 ;;
    --reasoning) reasoning=${2:?missing value for --reasoning}; shift 2 ;;
    --submit) submit=1; shift ;;
    --dry-run) submit=0; shift ;;
    -h|--help) usage; exit 0 ;;
    *) printf 'Unknown argument: %s\n\n' "$1" >&2; usage >&2; exit 2 ;;
  esac
done

case "$benchmark" in
  camyla|camylabench)
    benchmark="camyla"
    if [[ ! "$task_id" =~ ^[0-9]+$ ]]; then
      printf '%s\n' 'CamylaBench TASK must be numeric' >&2
      exit 2
    fi
    ;;
  rex|rex-mle)
    benchmark="rex-mle"
    task_id=$(printf '%s' "$task_id" | tr '[:upper:]' '[:lower:]')
    case "$task_id" in
      isles22|neurips-cellseg|panther-task1|panther-task2|puma-track1-task1|puma-track2-task1|seg_a|topbrain-track1|topbrain-track2|topcow-track1-task1|topcow-track2-task1|dentex|puma-track1-task2|puma-track2-task2|topcow-track1-task2|topcow-track2-task2|topcow-track1-task3|topcow-track2-task3|ldct-iqa|usenhance) ;;
      *)
        printf 'Unknown ReX-MLE task: %s\n' "$task_id" >&2
        exit 2
        ;;
    esac
    ;;
  *)
    printf '%s\n' 'BENCHMARK must be camyla or rex-mle' >&2
    exit 2
    ;;
esac

if [[ ! "$task_id" =~ ^[A-Za-z0-9._-]+$ ]]; then
  printf '%s\n' 'TASK may contain only letters, digits, dot, underscore, and hyphen' >&2
  exit 2
fi
if [[ ! "$version" =~ ^[A-Za-z0-9._-]+$ ]]; then
  printf '%s\n' '--version may contain only letters, digits, dot, underscore, and hyphen' >&2
  exit 2
fi
case "$cluster" in
  dfw|nb-hel) ;;
  *) printf '%s\n' '--cluster must be dfw or nb-hel' >&2; exit 2 ;;
esac
if [[ ! "$max_gpus" =~ ^[1-8]$ ]]; then
  printf '%s\n' '--max-gpus must be an integer from 1 through 8' >&2
  exit 2
fi
for budget in "$wall_hours" "$gpu_hours"; do
  if [[ ! "$budget" =~ ^[0-9]+([.][0-9]+)?$ ]] ||
     ! awk -v value="$budget" 'BEGIN { exit !(value > 0) }'; then
    printf '%s\n' 'Time and GPU-hour budgets must be positive numbers' >&2
    exit 2
  fi
done
if [[ ! "$model" =~ ^[A-Za-z0-9._-]+$ ]]; then
  printf '%s\n' '--model contains unsupported characters' >&2
  exit 2
fi
if [[ ! "$reasoning" =~ ^[A-Za-z0-9._-]+$ ]]; then
  printf '%s\n' '--reasoning contains unsupported characters' >&2
  exit 2
fi

submission_dir=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)
repo_root=$(cd -- "$submission_dir/../.." && pwd)

case "$benchmark" in
  camyla)
    if [[ "$cluster" == "nb-hel" ]]; then
      template_path="$submission_dir/templates/camylabench-nbhel.prompt.md"
      run_name="camyla_task_${version}_${task_id}_nbhel"
    else
      template_path="$submission_dir/templates/camylabench.prompt.md"
      run_name="camyla_task_${version}_${task_id}"
    fi
    work_dir="/cluster/shared/users/your_username/MIAgent/challenge/CamylaBench_${version}_${task_id}"
    dataset_root="/cluster/shared/projects/your_slurm_account/datasets/CamylaBench"
    root_path="not-applicable"
    train_path="not-applicable"
    test_path="not-applicable"
    private_path="not-applicable"
    ;;
  rex-mle)
    if [[ "$cluster" == "nb-hel" ]]; then
      template_path="$submission_dir/templates/rex-mle-nbhel.prompt.md"
      run_name="rex_task_${version}_${task_id}_nbhel"
    else
      template_path="$submission_dir/templates/rex-mle.prompt.md"
      run_name="rex_task_${version}_${task_id}"
    fi
    work_dir="/cluster/shared/users/your_username/MIAgent/challenge/ReX-MLE_${version}_${task_id}"
    dataset_root="not-applicable"
    root_path="/cluster/shared/projects/your_slurm_account/datasets/ReX-MLE/data"
    train_path="$root_path/$task_id/prepared/public/train/"
    test_path="$root_path/$task_id/prepared/public/test/"
    private_path="$root_path/$task_id/prepared/private"
    ;;
esac

prompt=$(<"$template_path")
prompt=${prompt//\{\{TASK_ID\}\}/$task_id}
prompt=${prompt//\{\{VERSION\}\}/$version}
prompt=${prompt//\{\{RUN_NAME\}\}/$run_name}
prompt=${prompt//\{\{WORK_DIR\}\}/$work_dir}
prompt=${prompt//\{\{DATASET_ROOT\}\}/$dataset_root}
prompt=${prompt//\{\{ROOT_PATH\}\}/$root_path}
prompt=${prompt//\{\{TRAIN_PATH\}\}/$train_path}
prompt=${prompt//\{\{TEST_PATH\}\}/$test_path}
prompt=${prompt//\{\{PRIVATE_PATH\}\}/$private_path}
prompt=${prompt//\{\{MAX_GPUS\}\}/$max_gpus}
prompt=${prompt//\{\{WALL_HOURS\}\}/$wall_hours}
prompt=${prompt//\{\{GPU_HOURS\}\}/$gpu_hours}

if printf '%s\n' "$prompt" | grep -Eq '\{\{[A-Z0-9_]+\}\}'; then
  printf '%s\n' 'Rendered prompt contains an unresolved placeholder' >&2
  exit 2
fi

run_dir="$submission_dir/.runs/$run_name"
prompt_path="$run_dir/prompt.md"
events_path="$run_dir/events.jsonl"
final_path="$run_dir/final.txt"
metadata_path="$run_dir/metadata.txt"
mkdir -p "$run_dir"

if ((submit)) && [[ -s "$events_path" || -s "$final_path" ]]; then
  printf 'Refusing to overwrite an existing submitted run: %s\n' "$run_dir" >&2
  printf '%s\n' 'Choose a new --version.' >&2
  exit 2
fi

printf '%s\n' "$prompt" >"$prompt_path"
template_sha=$(shasum -a 256 "$template_path" | awk '{print $1}')
prompt_sha=$(shasum -a 256 "$prompt_path" | awk '{print $1}')
git_revision=$(git -C "$repo_root" rev-parse HEAD 2>/dev/null || printf 'not-a-git-checkout')
{
  printf 'benchmark=%s\n' "$benchmark"
  printf 'task=%s\n' "$task_id"
  printf 'version=%s\n' "$version"
  printf 'cluster=%s\n' "$cluster"
  printf 'model=%s\n' "$model"
  printf 'reasoning=%s\n' "$reasoning"
  printf 'git_revision=%s\n' "$git_revision"
  printf 'template_sha256=%s\n' "$template_sha"
  printf 'prompt_sha256=%s\n' "$prompt_sha"
} >"$metadata_path"

printf 'Session: %s\nPrompt: %s\nMetadata: %s\n' \
  "$run_name" "$prompt_path" "$metadata_path"

if ((!submit)); then
  printf '\n%s\n' "$prompt"
  exit 0
fi

if ! command -v codex >/dev/null 2>&1; then
  printf '%s\n' 'codex is not installed or not on PATH' >&2
  exit 127
fi

codex_cmd=(
  codex
  -a never
  -s danger-full-access
  --search
  exec
  -m "$model"
  -c "model_reasoning_effort=\"$reasoning\""
  -C "$repo_root"
  --json
  -o "$final_path"
  -
)

printf '%s\n' "$prompt" | "${codex_cmd[@]}" | tee "$events_path"
