# nb-hel-cs-001 SLURM

Use this skill for nb-hel-cs-001 cluster work.

## Profile

Read the selected profile before submitting:

```text
skills/compute/profiles/<profile>.yaml
skills/compute/clusters/nb_hel.yaml
skills/compute/clusters/resource_profiles.yaml
```

Do not use another person's profile unless the human explicitly asks.

Recommended shell variables after reading the profile:

```bash
NB_HEL_HOST=<profile.clusters.nb_hel.default_host>
NB_HEL_IDENTITY=<profile.clusters.nb_hel.ssh_identity>
NB_HEL_ACCOUNT=<profile.clusters.nb_hel.account>
NB_HEL_DATASET_ROOT=<profile.clusters.nb_hel.paths.dataset_root>
NB_HEL_MIAGENT_ROOT=<profile.clusters.nb_hel.paths.miagent_root>
NB_HEL_SHARED_CAMYLA_ROOT=<profile.clusters.nb_hel.paths.shared_camyla_root>
NB_HEL_SHARED_REX_MLE_ROOT=<profile.clusters.nb_hel.paths.shared_rex_mle_root>
NB_HEL_CONTAINER_IMAGE=<profile.clusters.nb_hel.container.image>
NB_HEL_CONTAINER_MOUNT=<profile.clusters.nb_hel.container.mount>
NB_HEL_CONTAINER_PYTHON=<profile.clusters.nb_hel.container.python>
NB_HEL_HOST_PREFIX=<profile.clusters.nb_hel.container.host_to_container_path.host_prefix>
NB_HEL_CONTAINER_PREFIX=<profile.clusters.nb_hel.container.host_to_container_path.container_prefix>
SSH="ssh -i $NB_HEL_IDENTITY -o IdentitiesOnly=yes $NB_HEL_HOST"
```

Probe before use:

```bash
$SSH "hostname && whoami && squeue --me && sinfo -s"
```

## Scheduling Policy

| Work | Partition | Limit / Wall Time | Use |
|---|---|---|---|
| GPU interactive allocation | `interactive` | At most 2 active allocations; 4 hours each | Testing, validation, debugging, inference, and quick training |
| GPU batch training | `batch` | 4 hours | Long or full training; checkpoint and resume across allocations |
| GPU short batch | `batch_short` | 2 hours | Quick or resumable work when a 4-hour `batch` job remains queued |
| CPU jobs | `cpu_dataprocessing,cpu` | At most 2 concurrent jobs | Downloads, conversion, manifests, preprocessing, and CPU evaluation |

Prefer one 1-node, 8-GPU interactive allocation and append multiple exclusive
job steps to it instead of opening one allocation per probe. Request the GPUs,
CPUs, and memory each step actually needs; SLURM then gives simultaneous steps
different GPUs through `CUDA_VISIBLE_DEVICES`. Never exceed two active
interactive allocations or two concurrent CPU jobs. Interactive resources are
for bounded development work, not unattended full training.

**Hard rule:** every new GPU allocation on `interactive` requests one complete
8-GPU node. A one-GPU debug, inference, or smoke command is a job step inside
that allocation, never a new `interactive` allocation. If no reusable
interactive allocation exists and opening a full node is not justified, submit
the work to `batch` or `batch_short`.

## Storage Policy

For nb-hel-cs-001, read all user-specific paths from the selected profile.

```text
$NB_HEL_DATASET_ROOT       profile-owned root for challenge datasets
$NB_HEL_MIAGENT_ROOT       root for MIAgent challenge work
$NB_HEL_SHARED_CAMYLA_ROOT shared CamylaBench official datasets
$NB_HEL_SHARED_REX_MLE_ROOT shared ReX-MLE official datasets
```

Official shared benchmark data lives under:

```text
/cluster/shared/projects/your_slurm_account/datasets/
  CamylaBench/
  ReX-MLE/
```

MIAgent code, experiment-specific preprocessing, experiment runs, logs,
checkpoints, predictions, and result artifacts live under:

```text
$NB_HEL_MIAGENT_ROOT/<challenge>/
```

Do not copy raw challenge data into `$NB_HEL_MIAGENT_ROOT` unless the human
explicitly asks. Use symlinks, manifests, or read-only references from
`$NB_HEL_MIAGENT_ROOT/<challenge>/data/` to the dataset root when runs need a
stable challenge-local entry point.

## Interactive Debug

Before creating an allocation, list and count this user's existing interactive
allocations. Reuse a running allocation when it has free resources:

```bash
${SSH} "squeue --me -h -p interactive -t PENDING,RUNNING -o '%.18i %.24j %.10T %.10M %.20R'"
INTERACTIVE_COUNT=$(${SSH} "squeue --me -h -p interactive -t PENDING,RUNNING | wc -l")
```

If no reusable allocation exists and fewer than two are active, open one
1-node, 8-GPU, 4-hour allocation and keep that allocation session alive:

```bash
${SSH} -t "salloc -A '$NB_HEL_ACCOUNT' \
  --partition interactive \
  --nodes 1 \
  --gpus-per-node 8 \
  --ntasks 1 \
  --cpus-per-task 32 \
  --mem 512G \
  --time 4:00:00 \
  --job-name mia_interactive"
```

Once the allocation is running, append bounded steps. Each parallel step must
use `--exclusive` and request its own GPU count:

```bash
${SSH} "srun --jobid '$JOB_ID' \
  --exclusive --exact --nodes 1 --ntasks 1 \
  --gpus 1 --cpus-per-task 4 --mem 64G \
  --container-image '$NB_HEL_CONTAINER_IMAGE' \
  --container-mounts='$NB_HEL_CONTAINER_MOUNT' \
  --no-container-mount-home \
  --container-remap-root \
  --export=ALL \
  bash -lc 'cd <remote_experiment_dir> && \"$NB_HEL_CONTAINER_PYTHON\" <probe_or_script>.py'"
```

## Batch Submit

Copy or render a template from `skills/compute/slurm/` into the experiment's
`jobs/` folder, then submit with explicit account, partition, and log paths.
Use `batch` for normal training. If a 4-hour `batch` job remains queued and the
work can finish or save a useful resumable checkpoint within two hours, submit
the quick version explicitly to `batch_short`.

## Monitoring

```bash
$SSH "squeue -j <job_id> -o '%.18i %.24j %.10T %.10M %.20R'"
$SSH "sacct -j <job_id> --format=JobID,JobName,State,Elapsed,ExitCode --parsable2"
$SSH "tail -160 <slurm_log>"
```

Update the experiment `jobs/` evidence and this baseline's dashboard section
from scheduler or log evidence. Scheduler completion alone is not result
provenance. Do not busy-poll a healthy queued/running job.

## Runtime Rules

- Probe CUDA and task dependencies before expensive jobs.
- Reuse an existing 8-GPU interactive allocation for bounded tests.
- Never create a smaller GPU allocation on `interactive`.
- Run smaller interactive work as explicit exclusive steps with `--jobid`,
  `--exact`, and the GPUs, CPUs, and memory required by that step.
- Keep no more than two CPU jobs active concurrently.
- Use 4-hour `batch` jobs for full training and 2-hour `batch_short` only for
  quick or resumable work when the long-partition job remains queued.
- Use experiment-scoped environments rather than mutating shared envs.
- Keep jobs resumable when wall-time limits or preemption apply.
- Put large logs, checkpoints, predictions, and raw outputs on remote storage.
- Put official CamylaBench and ReX-MLE datasets under the shared
  `your_slurm_account/datasets` tree.
- Put experiment-specific preprocessing and derived data under the active
  experiment folder.
