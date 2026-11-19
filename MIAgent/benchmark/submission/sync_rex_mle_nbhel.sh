#!/usr/bin/env bash
set -euo pipefail

usage() {
  cat <<'USAGE'
Pull ReX-MLE challenge artifacts from nb-hel without model checkpoints.

Usage:
  benchmark/submission/sync_rex_mle_nbhel.sh TASK [--work-version VERSION]

Options:
  --work-version VERSION  Challenge-folder version (default: v3.5)
  -h, --help              Show this help
USAGE
}

if (($# < 1)); then
  usage >&2
  exit 2
fi

task_id=$1
shift
work_version=v3.5

while (($#)); do
  case "$1" in
    --work-version) work_version=${2:?missing value for --work-version}; shift 2 ;;
    -h|--help) usage; exit 0 ;;
    *) printf 'Unknown argument: %s\n' "$1" >&2; exit 2 ;;
  esac
done

if [[ ! "$task_id" =~ ^[A-Za-z0-9._-]+$ ]]; then
  printf '%s\n' 'TASK contains unsupported characters' >&2
  exit 2
fi
if [[ ! "$work_version" =~ ^[A-Za-z0-9._-]+$ ]]; then
  printf '%s\n' '--work-version contains unsupported characters' >&2
  exit 2
fi

repo_root=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/../.." && pwd)
folder="ReX-MLE_${work_version}_${task_id}"
remote_root="/cluster/shared/users/your_username/MIAgent/challenge/$folder"
local_root="$repo_root/challenge/$folder"

mkdir -p "$local_root"
rsync -a \
  --exclude='.cache/' \
  --exclude='.venv/' \
  --exclude='__pycache__/' \
  --exclude='checkpoints/' \
  --exclude='model_weights/' \
  --exclude='weights/' \
  --exclude='*.bin' \
  --exclude='*.ckpt' \
  --exclude='*.engine' \
  --exclude='*.h5' \
  --exclude='*.hdf5' \
  --exclude='*.joblib' \
  --exclude='*.onnx' \
  --exclude='*.pkl' \
  --exclude='*.pt' \
  --exclude='*.pth' \
  --exclude='*.safetensors' \
  "cluster-login.example.invalid:$remote_root/" \
  "$local_root/"

printf 'Synced nb-hel artifacts without checkpoints: %s\n' "$local_root"
