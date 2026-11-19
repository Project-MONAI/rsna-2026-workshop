# RSNA 2026 Workshop: MIAgent Medical Imaging Agent Lab

Explore how a language model becomes an agent that can research a medical imaging problem, run experiments, and leave results you can inspect.

This hands-on lab combines a locally served Qwen model, the OpenCode harness, MIAgent workflow instructions, medical AI skills, and a Docker-based training environment. Students compare model-only chat with an agent that can read files, use tools, submit GPU jobs, and examine predictions.

**Workshop format:** three browser-based lessons, two medical imaging challenges, and no Jupyter notebooks. The lessons run in the lab's browser workspace. You interact with the agent using natural-language prompts and review its work through documents, tracking tools, and image viewers.

## Who this lab is for

- **Clinicians and imaging researchers** who want to understand what an agent does, inspect its scientific reasoning, and assess its predictions.
- **Data scientists and AI engineers** who want to explore skills, experiment workflows, GPU execution, and reproducible research records.

Basic familiarity with medical imaging and machine learning is useful. The student walkthrough does not require writing a training pipeline from scratch.

## What you will learn

By the end of the lab, you should be able to:

- Distinguish the **model**, **harness**, **agent**, and **user interface**.
- Explain why a model-only conversation cannot inspect current files, query running jobs, or retrieve live information without tools.
- Identify how instructions and skills guide the agent's use of existing medical AI tools.
- Follow a research task through literature evidence, candidate selection, an implementation plan, and experiments.
- Check experiment status and distinguish planned work from completed results.
- Compare saved metrics, training curves, and prediction overlays.
- Explain how the containers separate responsibilities and where they share resources.
- Ask questions and steer the next experiment using the recorded evidence.

## The three lessons

| Lesson | Focus | What the student does |
| --- | --- | --- |
| **01 — Models, harnesses, and agents** | Concepts, interfaces, architecture, skills, and inference | Start the CAS and CHD agents, compare model-only chat with tool use, explore the container setup, and use NV-Segment-CT inference. |
| **02 — MIAgent overview** | Research workflow and durable artifacts | Understand the workflow, human decision gates, research records, and how work continues beyond a single conversation. |
| **03 — MIAgent workflow** | Inspecting actual agent work | Follow CAS research and experiments, review CHD architecture experiments, inspect predictions, and compare runs with MLflow and TensorBoard. |

Lesson sources:

1. [Models, harnesses, and agents](MIAgent/lab/01_overview.html)
2. [MIAgent workflow overview](MIAgent/docs/miagent_v3_overview.html)
3. [Inspect the agent's work](MIAgent/lab/03_MIAgent_workflow.html)

Open these lessons in the deployed lab's Preview/viewer for the interactive experience. GitHub file links provide access to the HTML source. The second lesson uses the overview maintained under `docs/`.

The first lesson starts the longer experiments early. Continue with the concepts and walkthrough while the agents work; you do not need to wait for training to finish before reading the remaining sections.

## Two challenges, two ways to delegate

| Challenge | Task | How the prompt guides the agent | Stopping instruction |
| --- | --- | --- | --- |
| **ImageCAS** | Coronary artery segmentation on cardiac CT | Give the agent the dataset and goal. Follow its task analysis, literature survey, critique, method selection, and experiment refinement. | Validation Dice 0.90 or 90 minutes. |
| **ImageCHD** | Cardiac structure segmentation on CT | Supply an explicit architecture sequence: MONAI SegResNet, UNet, and NV-Segment fine-tuning. Skip the literature survey and critique. | Validation Dice 0.90 or 55 minutes; at most 10 epochs per experiment, validating at epochs 5 and 10. |

Use the exact launch prompts in lesson 01. These targets are task instructions, not claims that a run will achieve them. The agents share GPU capacity, so opening two conversations does not guarantee simultaneous training.

For CAS, focus on **how the research changes the plan**. Read `literature.md`, check the cited evidence and available implementations, inspect critique limitations, and trace the selected direction into the experiments. Published paper scores and the lab's validation scores may use different data and evaluation settings.

## What runs where

```text
Student browser
    |
    v
Brev Secure Link -> nginx gateway
    |
    +-- Open WebUI --------------------------> local Qwen / vLLM
    |   Model-only chat
    |
    +-- Paseo / VS Code -> OpenCode agent ---> local Qwen / vLLM
    |                         |
    |                         +-- workspace, skills, and research records
    |                         +-- admitted jobs -> training container
    |
    +-- MIAgent Viewer ----------------------> documents and predictions
    +-- MLflow / TensorBoard ----------------> tracking container
```

| Service | Responsibility |
| --- | --- |
| `gateway` | nginx entry point. The default published host port is **8088**, accessed through the configured Brev Secure Link. |
| `chat` | Open WebUI configured for model-only conversation, with search, code execution, and external tools disabled. |
| `paseo` | Browser workspace for interacting with OpenCode agents and viewing lab files. |
| `miagent` | CPU control environment containing VS Code, OpenCode, workflow instructions, tools, viewers, and job submission. |
| `llm` | Local Qwen inference served by vLLM through an internal OpenAI-compatible API. |
| `training` | GPU scientific environment with PyTorch, MONAI, and the training/evaluation dependencies. |
| `tracking` | MLflow and TensorBoard for experiment tracking. |
| `lab-init` | One-time initialization of the persistent lab workspace and runtime volumes. |

The full service definitions are in [docker-compose.yml](MIAgent/docker-compose.yml).

### What is isolated, and what is shared?

- **Service environments:** containers separate processes and installed dependencies. The agent's control environment and the GPU training environment have different jobs.
- **Dataset access:** selected services mount the host dataset directory at `/data` as read-only. Experiments write outputs into the workspace rather than modifying those input files.
- **Persistent state:** selected services share `/workspace`, `/runtime`, and `/cache` through Docker volumes. The model server has a separate Hugging Face cache volume. Tracking mounts `/workspace` read-only.
- **GPU capacity:** model inference and scientific training use the same host GPU resources. Separate containers do not reserve independent GPUs or eliminate memory contention.
- **Networking:** services communicate over the Compose network through internal endpoints. The gateway provides the normal browser entry point.

**This is operational separation, not a security sandbox against an untrusted agent.** The `miagent` and `paseo` services mount the host Docker socket, which gives the agent powerful access to the host's Docker environment. The LLM service also uses host IPC. Read-only dataset mounts and separate containers must be interpreted in that context. Brev and the VM's network configuration provide the intended access control for this trusted student lab.

## Skills: reuse tools instead of rebuilding them

MIAgent includes workflow guidance and medical imaging skills that tell the agent when to use a tool, what inputs it needs, how to invoke it, and what outputs to inspect.

Examples include DICOM utilities, MONAI workflows, pretrained segmentation, and segmentation fine-tuning. Browse the [local skills](MIAgent/skills/) and the upstream [NVIDIA Medtech Medical AI Skills catalog](https://github.com/NVIDIA-Medtech/medical-AI-skills).

Skills guide the LLM without updating its weights. A training tool called by the agent can separately update an imaging model. An upstream skill being listed does not mean all its dependencies and weights are ready in this lab; check the preparation status documented in the setup guide.

## Follow the evidence

Each challenge has a durable research folder. Use these records to understand the work beyond the chat transcript:

| Record | Question it answers |
| --- | --- |
| `challenge.md` | What are the task, data, split, metric, and rules? |
| `literature.md` and `critics/` | What research supports the approach, and which assumptions remain weak? |
| `candidates.md` | Which alternatives were considered and why was a direction selected? |
| `trajectory.md` | Which consequential agent decisions or human instructions changed the direction? |
| `dashboard.md` and `state.md` | What is running, what is the current focus, and what evidence is needed next? |
| `baselines/<baseline>/baseline.md` | What is the implementation plan for the selected direction? |
| `baselines/<baseline>/runs/<experiment>/experiment.md` | What was the pre-run intent, what happened, and what decision followed? |
| `result_viewers/result_viewer.html` inside a run | What do the saved predictions look like on individual cases? |

Compare prediction, ground truth, and difference overlays across cases. A single case's Dice score is not the aggregate validation result. Use MLflow and TensorBoard alongside the saved experiment records to connect curves and checkpoints to the reported outcome.

## Start the lab

### Students

1. Open the workshop's Brev Launchable and deploy the assigned environment.
2. Wait for setup to finish, then open the configured Secure Link.
3. Open Paseo and start **lesson 01**. The prepared lab normally opens its first lesson in Preview on the first visit.
4. Start the CAS and CHD agents using the supplied prompts, then continue through the lessons while experiments run.
5. Use the MIAgent Viewer, MLflow, TensorBoard, and prediction viewers to review the work.

### Instructors and operators

Start with [lab preparation and Brev setup](lab_prep/SETUP.md). It documents the current VM bootstrap, repository authentication, dataset preparation, model downloads, service startup, and access configuration. Configure the public repository as the Brev Source. Brev clones it onto the VM; upload or paste `lab_prep/brev_startup.sh` as the VM setup script to prepare that existing checkout. No GitHub token or second clone is required.

The machine needs Docker with Compose, NVIDIA GPU support, and sufficient GPU memory and disk for local LLM serving, imaging jobs, model weights, and datasets. Use the setup guide for the supported configuration; this README does not define a tested minimum GPU size.

Startup produces a local timing report at `build_reports/startup_timing.json`. Pretrained NV-Segment-CT preparation continues separately in the background; its readiness and timing are recorded separately from the initial lab startup.

## Repository map

```text
MIAgent/        Application, Compose stack, agent instructions, skills, and lessons
lab_prep/       Host orchestration, dataset preparation, and setup documentation
data/           Dataset mount root; downloaded data is excluded from Git
```

- [Application and research workflow documentation](MIAgent/README.md)
- [Student lesson sources](MIAgent/lab/)
- [Lab setup guide](lab_prep/SETUP.md)
- [Dataset preparation details](lab_prep/README.md)
- [Reusable challenge template](MIAgent/challenge/challenge_template/)

This is a research and education lab. Its demonstrations and saved predictions do not establish clinical validity.

## Attribution

This workshop packages the [MIAgent research workflow](https://github.com/heyufan1995/MIAgent) with browser lessons and a local Docker lab. Third-party tools, models, datasets, and bundled assets retain their respective licenses and usage terms. External-cluster configuration is provided as an example and must be filled in and verified for your own environment.
