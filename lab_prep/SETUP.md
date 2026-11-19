# Public-repository Brev setup

Expected repository layout:

```text
MIAgent/                 # application and Docker Compose
lab_prep/                # downloader, setup script, and tests
data/                    # tracked placeholders only; downloaded files ignored
build_reports/           # local timing reports, ignored
```

The top-level layout is published at https://github.com/Project-MONAI/rsna-2026-workshop. The setup script
does not initialize, rewrite, or push repositories.

## Local setup

`brev_startup.sh` is the Brev VM startup entrypoint. Brev clones the public
repository configured under Source; the entrypoint locates that existing
checkout and invokes its `setup_lab.py` without `--repo-url`. No GitHub token
or second clone is required.
`setup_lab.py` prepares configuration, then runs four independent tasks in
parallel: data download/resampling, lab image builds, chat image pull, and Qwen
download using a small dedicated downloader image. After those tasks succeed,
workspace initialization and Qwen startup run concurrently. Lab services and
the gateway start only after both complete. Startup uses `--no-build` so it
cannot unexpectedly trigger another build.
One-off downloader commands use `compose run --pull never` with already-built
images; `--no-build` is an `up` option and must not be passed to `run`.
Paseo accepts Brev Secure Link hosts under `.brevlab.com` and `.gobrev.dev` without a per-instance
hostname parameter. nginx forwards the public Host and Origin for HTTP and
WebSocket requests, adding the scheme's default port when it is omitted
(443 for HTTPS, 80 for HTTP). Paseo 0.9.2 requires that explicit port in its
automatic connection hint. Explicit ports such as local 8088 are preserved.
Paseo still rejects unrelated domains. Use
`MIAgent_PUBLIC_HOST` only for an additional custom domain outside Brev.
Paseo startup registers the non-Git lab directory `/workspace` as the MIAgent
project using the pinned Paseo registry APIs. It reuses existing active records
and preserves unrelated projects and daemon identity. The initial browser page
opens that workspace automatically; other workspace/session routes are left
alone. OpenCode is configured with local Qwen as its default model. No agent
is created and no prompt is sent automatically.
The seeded Local Qwen Paseo profile enables its `auto_accept` feature. The
shared OpenCode configuration also defaults tool permissions to `allow`, so
ordinary lab work does not require choosing that profile or approving each
tool call. Explicit `.env` read denials remain. Shell and Docker access are
powerful; those read rules are not a sandbox or a guarantee that secrets
cannot be reached through other tools. Use these defaults only in the trusted
student lab. Existing conversations with their own permission overrides may
need a new session to inherit the defaults.
Paseo starts with the left workspace/session sidebar hidden on each page load,
including returning browsers. Students can reopen it while working; other
saved panel preferences and sessions are preserved.
On the first visit to the lab workspace in a browser, Paseo expands `lab/`
and opens `01_overview.html` in Preview mode. Its screenshots are embedded,
so the lesson does not require a separate images folder. A
browser-local marker scoped to the daemon and workspace prevents subsequent
visits from replacing the selected chat. The initial preview is skipped when
the teaching file is absent. Old Markdown lessons remain only in the local,
Git-ignored and Docker-ignored `lab/delete/` archive. A new Agent draft may
require explicitly choosing Local Qwen in the model picker.
The first-run browser bootstrap is tested against pinned Paseo 0.9.2; rerun
`lab_prep/test_paseo_browser.cjs` with Playwright against an isolated preview
when upgrading Paseo. Browser-test dependencies are not needed on student VMs.
It invokes `run_data_prep.py`, which builds `lab_prep/Dockerfile` and runs a
standalone preparation container using `docker run`, never lab Compose.
After the gateway is healthy, setup starts NV-Segment-CT preparation in a
standalone background container, outside Compose. The lab does not wait for
this download. It reuses the existing training image with no GPU, Docker socket,
or dataset mount; only the workspace (read-only) and persistent model cache
(writable) are attached. No running services are restarted and no packages are
installed on the host or in VS Code. CTMR is not downloaded automatically.

The pinned CT checkpoint is 871,970,895 bytes (about 832 MiB), plus small Python
and configuration files. A valid existing checkpoint is reused; only one weight
format is downloaded. SHA-256, required files, JSON metadata, and offline code
imports are checked before marking inference ready. Weights are stored in
`/cache/bundles/nv-segment-ct`, not Git or Docker build layers. Fresh workspace
initialization reconnects the cache even when no bundle exists in the source.

Check readiness inside the lab with
`python3 tools/prepare_lab_models.py --status`. The command is read-only and
needs no imaging packages. It reports `not_started`, `preparing`, `ready`, or
`failed`. The report at `/cache/model-preparation/nv-segment-ct.json` records
the pinned revision, elapsed preparation time, and failures. Student inference
stops with a clear message until ready; agents must not attempt installations.

To retry after a network failure, run
`python3 lab_prep/prepare_nvsegment.py --background` on the host. Omit
`--background` to follow the logs and wait for completion. The container is
named after the training container with `-nvsegment-prepare` appended; its
logs remain available after completion. A running preparation is not duplicated.

Each setup stage prints UTC timestamps, elapsed time since setup began, and
its duration on completion or failure. The final total is wall-clock time,
not the sum of overlapping stages. A machine-readable report is saved at
`build_reports/startup_timing.json` (ignored by Git), including stage durations,
start offsets, and failure status. Parallel subprocess output may interleave;
the labelled START/COMPLETE/FAILED lines identify task boundaries. On failure,
pending tasks are cancelled and running preparation tasks are joined before
exiting; service startup does not proceed. Background inference preparation
is the exception: download completion is timed separately and its failure does
not stop the available lab. The measured total starts in
`setup_lab.py`, including repository clone when requested, but excludes the
Brev-managed repository clone and the entrypoint before Python setup begins.
`build_lab.py` is an optional operator-only uncached-build timing tool, not
part of agent workflows or required by the normal setup script. It writes
reports to the top-level `build_reports/` directory.

Run the harmless plan first:

```bash
python3 lab_prep/setup_lab.py --plan
```

With existing ImageCAS_lab and ImageCHD_lab data, run:

```bash
python3 lab_prep/setup_lab.py --public-host YOUR_BREV_SECURE_LINK_HOSTNAME
```

For a fresh VM, explicitly select a resampled dataset variant:

```bash
python3 lab_prep/setup_lab.py --prepare-data --spacing-mm 2 \
  --unknown-labels background --public-host YOUR_BREV_SECURE_LINK_HOSTNAME
```

There is no additional nginx username/password prompt. Open WebUI also runs
with its own authentication disabled. Access control must be provided by Brev
and the VM's network restrictions: do not expose gateway port 8088 directly
to untrusted users. Setup no longer generates or copies an `htpasswd` file,
and removes obsolete gateway username/password entries from `.env`. Other
existing `.env` settings are preserved, apart from updated host paths, local
IDs, and an explicitly requested public hostname. No GitHub token is written to
`.env`, a remote URL, or Docker configuration. A temporary Git askpass helper
reads the token from the clone process environment and is deleted afterward.
Administrators can still inspect process environments; prefer short-lived tokens.

The script checks Docker (falling back to noninteractive sudo), the Compose
plugin, and the NVIDIA driver. Host Python is used only for standard-library
orchestration. No host virtual environments, pip installs, or apt installs are
performed. Scientific Python dependencies are packaged in the standalone
data-preparation image. It does not install system drivers or Docker.
Use a Brev GPU VM with Docker GPU support and enough disk for images, Qwen,
and datasets. No hardware suitability benchmark is performed automatically.

Preflight and configuration precede the parallel preparation tasks described
above. Service startup waits for their completion; the pretrained CT
segmentation bundle downloads separately after the lab is available.
Dependencies stop subsequent stages on failure. Setup refuses to operate on
an active Compose lab and never runs `down`, volume deletion, or reset commands.
Already-downloaded Qwen weights remain in the persistent cache. Completed lab
initialization is reused; use the separate reset tool only when intentionally
resetting student work. A failed partial data download/preparation is not
automatically overwritten; inspect or choose a clean output directory first.

Data policy matters: 2 mm resampling changes the original lab, particularly
small coronary structures. The default `background` policy maps undocumented
ImageCHD IDs 12 and 13 to zero before resampling, leaving foreground classes
1-7. Original voxel counts and the conversion policy remain recorded in reports.
An explicit `preserve` override retains those IDs and requires a training policy.

## Brev Launchable with the public repository

1. Select **VM Mode** on a GPU VM with Docker GPU support.
2. Under **Source**, select **I have code files in a git repository** and enter
   `https://github.com/Project-MONAI/rsna-2026-workshop`.
3. Upload or paste the contents of [`brev_startup.sh`](brev_startup.sh) into
   the VM setup-script field. Adding a repository alone does not select a
   setup command. Brev runs the configured script during deployment.
4. Create a Brev **Secure Link for port 8088**. Leave the application behind
   Brev access control; do not open the gateway directly to anonymous traffic.
5. Test a fresh deployment before enabling **Publish to community**.

The startup script uses Brev's checkout rather than cloning again. It checks
its working directory, `~/rsna-2026-workshop`,
`/home/ubuntu/rsna-2026-workshop`, and common `~/workspace` locations. If the
provider uses another path, set `MIAgent_LAB_ROOT` explicitly. A missing
checkout fails with an explanation and is never replaced. Verify the source
checkout path and its availability when the VM script runs on the first
fresh deployment; that integration still requires a real Brev VM test.

Optional launch parameters:

| Parameter | Value |
| --- | --- |
| `MIAgent_LAB_ROOT` | Existing checkout root, for example `/home/ubuntu/rsna-2026-workshop`; normally auto-detected. |
| `MIAgent_PREPARE_DATA` | `true` by default; `false` only when both prepared datasets already exist. |
| `MIAgent_DATA_SPACING_MM` | `2` by default, the resampled workshop variant. |
| `MIAgent_UNKNOWN_LABELS` | `background` by default; alternatives are `error` and `preserve`. |

The source clone is handled by Brev. The repository's internal `--repo-url`
helper remains available for legacy private-repository operations but is not
used by this public Launchable entrypoint.

For a custom browser domain outside `.brevlab.com` and `.gobrev.dev`, use
`setup_lab.py --public-host YOUR_HOSTNAME` during initial operator setup. For
an existing lab, update `MIAgent_PUBLIC_HOST` in the application `.env` and
recreate only Paseo as described above. Do not rerun full preparation while
experiments are running.

## Optional solution archive

The outside `MIAgent_solution/` directory is ignored by Git and is not
downloaded or started by the normal Launchable setup. To include historical
solutions, transfer that directory separately and enable the Compose
`solutions` profile. The landing-page archive links require those optional
services; the consolidated Lab Data and Results link uses the student viewer.
Deleting a host-side generated challenge copy does not delete results in the
live workspace volume or the outside archive. Fresh lab images include only
the challenge template, not completed challenge runs.

Archive services mount the outside directory read-only. Student services do
not mount it directly, but their Docker socket access means this is not a
security boundary. Do not rely on this arrangement to conceal answer keys.

After publishing changes, test on a fresh Launchable VM: verify gateway
access through Brev, Paseo's automatic MIAgent workspace and Local Qwen selection, an actual
chat response, the student results viewer, and the startup timing report.
The pasted `brev_startup.sh` only needs updating when that entrypoint changes.
Application setup code is read from the checkout supplied by Brev.

Official references:
- https://docs.nvidia.com/brev/concepts/launchables
- https://docs.nvidia.com/brev/guides/secrets

## Verification

```bash
python3 -m unittest discover -s lab_prep -p test_setup_lab.py -v
```

The setup tests are offline and do not start containers or download models/data.
Run the public startup entrypoint tests without downloading data or starting containers:

```bash
python3 -m unittest discover -s lab_prep -p test_brev_startup.py -v
```

Run the standalone runner tests on the host using only the standard library:

```bash
python3 -m unittest discover -s lab_prep -p test_run_data_prep.py -v
```

Run the scientific data-preparation tests inside the preparation image; see
README.md. The lab's Docker Compose file does not include the data-preparation
container. Qwen download and pretrained segmentation-bundle preparation also
run in containers; NV-Segment-CT preparation is detached from lab startup.
