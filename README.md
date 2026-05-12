<div align="center">

<a href="https://github.com/reacher-z/ClawBench">
  <picture>
    <source media="(prefers-color-scheme: dark)" srcset="static/hero-dark.svg">
    <img alt="ClawBench" src="static/hero-light.svg" width="820">
  </picture>
</a>

[![Star this repo](https://img.shields.io/badge/%E2%98%85%20Star%20this%20repo-181717?style=flat-square&logo=github&logoColor=white)](https://github.com/reacher-z/ClawBench)
[![arXiv](https://img.shields.io/badge/arXiv-2604.08523-B31B1B?style=flat-square&logo=arxiv&logoColor=white)](https://arxiv.org/abs/2604.08523)
[![HF Daily Paper](https://img.shields.io/badge/Daily_Paper-FFD21E?style=flat-square&logo=huggingface&logoColor=000)](https://huggingface.co/papers/2604.08523)
[![HF Dataset](https://img.shields.io/badge/Dataset-FFD21E?style=flat-square&logo=huggingface&logoColor=000)](https://huggingface.co/datasets/NAIL-Group/ClawBench)
[![HF Trace Dataset](https://img.shields.io/badge/Trace_Dataset-FFD21E?style=flat-square&logo=huggingface&logoColor=000)](https://huggingface.co/datasets/NAIL-Group/ClawBenchV1Trace)
[![Project Page](https://img.shields.io/badge/claw--bench.com-4F46E5?style=flat-square&logo=googlechrome&logoColor=white)](https://claw-bench.com)
[![GitHub stars](https://img.shields.io/github/stars/reacher-z/ClawBench?style=flat-square&logo=github&color=181717&cacheSeconds=300)](https://github.com/reacher-z/ClawBench)
[![Discord](https://img.shields.io/badge/Discord-Join-5865F2?style=flat-square&logo=discord&logoColor=white)](https://discord.gg/clawbench)
[![Codespaces](https://img.shields.io/badge/Codespaces-Open-181717?style=flat-square&logo=github&logoColor=white)](https://codespaces.new/reacher-z/ClawBench?quickstart=1)

[![PyPI downloads](https://img.shields.io/pypi/dm/clawbench-eval?style=flat-square&logo=pypi&color=3775A9&logoColor=white&label=PyPI%20downloads)](https://pypi.org/project/clawbench-eval/)
[![PyPI version](https://img.shields.io/pypi/v/clawbench-eval?style=flat-square&logo=pypi&color=3775A9&logoColor=white)](https://pypi.org/project/clawbench-eval/)
[![Last commit](https://img.shields.io/github/last-commit/reacher-z/ClawBench?style=flat-square&logo=github&logoColor=white)](https://github.com/reacher-z/ClawBench/commits/main)
[![Contributors](https://img.shields.io/github/contributors/reacher-z/ClawBench?style=flat-square&logo=github&logoColor=white)](https://github.com/reacher-z/ClawBench/graphs/contributors)
[![Commit activity](https://img.shields.io/github/commit-activity/m/reacher-z/ClawBench?style=flat-square&logo=github&logoColor=white)](https://github.com/reacher-z/ClawBench/graphs/commit-activity)
[![License](https://img.shields.io/github/license/reacher-z/ClawBench?style=flat-square&color=A42E2B)](https://github.com/reacher-z/ClawBench/blob/main/LICENSE)

<p align="center"><sub><i>Featured in</i></sub></p>
<p align="center">
  <a href="https://github.com/walkinglabs/awesome-harness-engineering"><img alt="awesome-harness-engineering" src="https://img.shields.io/badge/Featured-awesome--harness--engineering-7C3AED?style=flat-square&logo=awesomelists&logoColor=white"></a>
  <a href="https://github.com/Jenqyang/Awesome-AI-Agents"><img alt="Awesome-AI-Agents" src="https://img.shields.io/badge/Featured-Awesome--AI--Agents-7C3AED?style=flat-square&logo=awesomelists&logoColor=white"></a>
  <a href="https://github.com/ranpox/awesome-computer-use"><img alt="awesome-computer-use" src="https://img.shields.io/badge/Featured-awesome--computer--use-7C3AED?style=flat-square&logo=awesomelists&logoColor=white"></a>
  <a href="https://github.com/ZJU-REAL/Awesome-GUI-Agents"><img alt="Awesome-GUI-Agents" src="https://img.shields.io/badge/Featured-Awesome--GUI--Agents-7C3AED?style=flat-square&logo=awesomelists&logoColor=white"></a>
  <a href="https://github.com/zhangxjohn/LLM-Agent-Benchmark-List"><img alt="LLM-Agent-Benchmark-List" src="https://img.shields.io/badge/Featured-LLM--Agent--Benchmark--List-7C3AED?style=flat-square&logo=awesomelists&logoColor=white"></a>
</p>

<p align="center">
  <a href="https://huggingface.co/papers/2604.08523"><img src="https://img.shields.io/badge/%233_Paper_of_the_Day-FFD21E?style=for-the-badge&logo=huggingface&logoColor=000" alt="#3 Paper of the Day"></a>
</p>

<p align="center">
  <a href="https://deepwiki.com/reacher-z/ClawBench"><img alt="Ask DeepWiki" src="https://deepwiki.com/badge.svg" /></a>
</p>

</div>

<div align="center">

<p align="center">
  <b>New:</b> Check out our sister project <a href="https://github.com/reacher-z/HarnessBench"><b>HarnessBench</b></a> &mdash;
  fixes the base model, varies the harness. Same scoring pipeline, orthogonal axis.
</p>

<a href="#-human-quick-start"><img src="https://img.shields.io/badge/Run%20in%20one%20line%20of%20code-4F46E5?style=for-the-badge&labelColor=4F46E5&logoColor=white&logo=data:image/svg%2Bxml;base64,PHN2ZyB4bWxucz0iaHR0cDovL3d3dy53My5vcmcvMjAwMC9zdmciIHZpZXdCb3g9IjAgMCA1NzYgNTEyIj48cGF0aCBmaWxsPSIjZmZmZmZmIiBkPSJNMjYzLjQtMjdMMjc4LjIgOS44IDMxNSAyNC42YzMgMS4yIDUgNC4yIDUgNy40cy0yIDYuMi01IDcuNEwyNzguMiA1NC4yIDI2My40IDkxYy0xLjIgMy00LjIgNS03LjQgNXMtNi4yLTItNy40LTVMMjMzLjggNTQuMiAxOTcgMzkuNGMtMy0xLjItNS00LjItNS03LjRzMi02LjIgNS03LjRMMjMzLjggOS44IDI0OC42LTI3YzEuMi0zIDQuMi01IDcuNC01czYuMiAyIDcuNCA1ek0xMTAuNyA0MS43bDIxLjUgNTAuMSA1MC4xIDIxLjVjNS45IDIuNSA5LjcgOC4zIDkuNyAxNC43cy0zLjggMTIuMi05LjcgMTQuN2wtNTAuMSAyMS41LTIxLjUgNTAuMWMtMi41IDUuOS04LjMgOS43LTE0LjcgOS43cy0xMi4yLTMuOC0xNC43LTkuN0w1OS44IDE2NC4yIDkuNyAxNDIuN0MzLjggMTQwLjIgMCAxMzQuNCAwIDEyOHMzLjgtMTIuMiA5LjctMTQuN0w1OS44IDkxLjggODEuMyA0MS43QzgzLjggMzUuOCA4OS42IDMyIDk2IDMyczEyLjIgMy44IDE0LjcgOS43ek00NjQgMzA0YzYuNCAwIDEyLjIgMy44IDE0LjcgOS43bDIxLjUgNTAuMSA1MC4xIDIxLjVjNS45IDIuNSA5LjcgOC4zIDkuNyAxNC43cy0zLjggMTIuMi05LjcgMTQuN2wtNTAuMSAyMS41LTIxLjUgNTAuMWMtMi41IDUuOS04LjMgOS43LTE0LjcgOS43cy0xMi4yLTMuOC0xNC43LTkuN2wtMjEuNS01MC4xLTUwLjEtMjEuNWMtNS45LTIuNS05LjctOC4zLTkuNy0xNC43czMuOC0xMi4yIDkuNy0xNC43bDUwLjEtMjEuNSAyMS41LTUwLjFjMi41LTUuOSA4LjMtOS43IDE0LjctOS43ek00NjAgMGMxMSAwIDIxLjYgNC40IDI5LjUgMTIuMmw0Mi4zIDQyLjNDNTM5LjYgNjIuNCA1NDQgNzMgNTQ0IDg0cy00LjQgMjEuNi0xMi4yIDI5LjVsLTg4LjIgODguMi0xMDEuMy0xMDEuMyA4OC4yLTg4LjJDNDM4LjQgNC40IDQ0OSAwIDQ2MCAwek00NC4yIDM5OC41TDMwOC40IDEzNC4zIDQwOS43IDIzNS42IDE0NS41IDQ5OS44QzEzNy42IDUwNy42IDEyNyA1MTIgMTE2IDUxMnMtMjEuNi00LjQtMjkuNS0xMi4yTDQ0LjIgNDU3LjVDMzYuNCA0NDkuNiAzMiA0MzkgMzIgNDI4czQuNC0yMS42IDEyLjItMjkuNXoiLz48L3N2Zz4=" alt="Run in one line of code"></a>

```bash
git clone https://github.com/reacher-z/ClawBench.git && cd ClawBench && ./run.sh
```

<sub><i>Clone → configure → run. &nbsp; Root uv package. &nbsp; Docker-isolated harnesses.</i></sub>

### Can AI Agents Complete Everyday Online Tasks?

**ClawBench is an open-source benchmark that evaluates AI browser agents on everyday online tasks — booking travel, ordering food, applying for jobs, managing email — across live websites. V1 lives in `test-cases/v1/` with 153 tasks across 144 websites; V2 lives in `test-cases/v2/` with 130 tasks. It measures end-to-end task success with a 5-layer recording pipeline and an agentic evaluator that compares each run against human references. Top score to date: 33.3%.**

<img src="static/clawbench_logo.png" alt="ClawBench logo" width="320">

We asked frontier AI agents to do what people do every day --<br/>
order food, book travel, apply for jobs, write reviews, manage projects.<br/>
**Even the best agent only completes about 1 in 3.**

<sub><i>Built by NAIL Group &nbsp;·&nbsp; Sister project: <a href="https://github.com/reacher-z/HarnessBench">HarnessBench</a> &nbsp;·&nbsp; Runs on any Chrome.</i></sub>

---

**V1: 153** everyday tasks &nbsp;&middot;&nbsp; **V2: 130** tasks &nbsp;&middot;&nbsp; **144** live websites &nbsp;&middot;&nbsp; **15** life categories

<a href="README.zh-CN.md"><img src="static/icons/language.svg" width="16" height="16"> 中文</a>

</div>

## <img src="static/icons/circle-question.svg" width="20" height="20"> What are you looking for?

<table>
<tr>
<td width="25%" align="center" valign="top">

🏆 **See scores**<br/>
[Live leaderboard](https://huggingface.co/spaces/NAIL-Group/clawbench-leaderboard)<br/>
<sub>Pick a corpus (v1 / v2)</sub>

</td>
<td width="25%" align="center" valign="top">

🚀 **Run it on your model**<br/>
[Quick start ↓](#-human-quick-start)<br/>
<sub><code>pip install clawbench-eval</code></sub>

</td>
<td width="25%" align="center" valign="top">

📊 **Browse 283 tasks**<br/>
[Task explorer](https://claw-bench.com/v2)<br/>
<sub>Search · filter · category</sub>

</td>
<td width="25%" align="center" valign="top">

📄 **Read the paper**<br/>
[arXiv:2604.08523](https://arxiv.org/abs/2604.08523)<br/>
<sub>Methodology · evaluator · results</sub>

</td>
</tr>
<tr>
<td align="center" valign="top">

🎬 **Re-grade old runs**<br/>
[V1 raw traces](https://huggingface.co/datasets/NAIL-Group/ClawBenchV1Trace)<br/>
<sub>5 layers per (task × model)</sub>

</td>
<td align="center" valign="top">

📦 **Download the data**<br/>
[`hf download NAIL-Group/ClawBench`](https://huggingface.co/datasets/NAIL-Group/ClawBench)<br/>
<sub>Tasks · rubrics · metadata</sub>

</td>
<td align="center" valign="top">

🌱 **Add a task / model**<br/>
[How to contribute](#contributing)<br/>
<sub>YAML spec + rubric</sub>

</td>
<td align="center" valign="top">

❓ **Have a question**<br/>
[FAQ](#frequently-asked-questions) · [Discord](https://discord.gg/clawbench)<br/>
<sub>Or open an issue</sub>

</td>
</tr>
</table>

## <img src="static/icons/bullhorn.svg" width="20" height="20"> News

- **[2026.05.12]** <img src="static/icons/hugging-face.svg" width="14" height="14"> &nbsp;Canonical leaderboard moved to **[`TIGER-Lab/ClawBench`](https://huggingface.co/spaces/TIGER-Lab/ClawBench)** — Gradio 3-tab Space (Leaderboard / About / Submit) modeled after [`TIGER-Lab/MMLU-Pro`](https://huggingface.co/spaces/TIGER-Lab/MMLU-Pro). All HF assets bundled in the **[ClawBench collection](https://huggingface.co/collections/TIGER-Lab/clawbench-6a0247d04680f475038797d4)** — paper + V1/V2 dataset + V1Trace + V2Trace + Space. Ranking corrected: partial-batch results no longer outrank complete ones with lower reward. ([`NAIL-Group/clawbench-leaderboard`](https://huggingface.co/spaces/NAIL-Group/clawbench-leaderboard) remains live as the historical mirror.)
- **[2026.05.11]** <img src="static/icons/chart-bar.svg" width="14" height="14"> &nbsp;V2 leaderboard ships — first 6 models scored end-to-end with two-stage rubric (interception + LLM judge). Top so far: `glm-5.1 / hermes` at **18.5% reward / 48.5% intercepted**. See [`claw-bench.com/leaderboard`](https://claw-bench.com/leaderboard), scoring details in [`eval/scoring.md`](eval/scoring.md), live data on the [HF Space](https://huggingface.co/spaces/TIGER-Lab/ClawBench).
- **[2026.05.11]** <img src="static/icons/layer-group.svg" width="14" height="14"> &nbsp;Companion trace dataset **[ClawBenchV2Trace](https://huggingface.co/datasets/NAIL-Group/ClawBenchV2Trace)** going live — same 5-layer trace bundle per run as V1Trace, rolling as new V2 evaluations land.
- **[2026.05.09]** <img src="static/icons/globe.svg" width="14" height="14"> Added support for the **pi** harness — Pi coding agent + `pi-browser-harness`.
- **[2026.05.09]** <img src="static/icons/layer-group.svg" width="14" height="14"> &nbsp;Released **[ClawBenchV1Trace](https://huggingface.co/datasets/NAIL-Group/ClawBenchV1Trace)** — the full execution trace for every V1 model run: session recording (`recording.mp4`), HTTP traffic (`requests.jsonl`), browser actions (`actions.jsonl`), agent reasoning (`agent-messages.jsonl`), and the intercepted final request (`interception.json`). Anyone can reproduce, re-grade, or post-hoc analyze our results. Pairs with the existing [task-definition dataset](https://huggingface.co/datasets/NAIL-Group/ClawBench).
- **[2026.05.09]** <img src="static/icons/robot.svg" width="14" height="14"> &nbsp;Added an **inline LLM judge** as the second scoring stage. Pass = (1) the agent's final HTTP request is intercepted and matches the task's URL/method schema, AND (2) an LLM judge confirms the request body actually fulfills the natural-language instruction. Default judge: `deepseek-v4-pro`. Disable with `--no-judge`. This means **runs now produce a final pass/fail score automatically** — no separate trajectory inspection step.
- **[2026.05.09]** <img src="static/icons/rocket.svg" width="14" height="14"> &nbsp;We have updated our release pipeline and published the package to PyPI under [**clawbench-eval**](https://pypi.org/project/clawbench-eval/) for easier usage.
- **[2026.05.04]** <img src="static/icons/screwdriver-wrench.svg" width="14" height="14"> &nbsp;Refactored the codebase to improve project structure, streamline the CI/CD pipeline, make it easier to extend ClawBench to additional test suites, and deliver more stable builds across **V1**, **V1-Lite**, and **V2**. The FAQ section was also updated based on user feedback.
- **[2026.05.01]** <img src="static/icons/rocket.svg" width="14" height="14"> &nbsp;Added the full **V2** 130-task corpus and one-command Hermes launch:
  `uv run clawbench-batch --models deepseek/deepseek-v4-flash --cases-suite v2 --all-cases --harness hermes --max-concurrent 3 --no-upload`
- **[2026.04.25]**<img src="static/icons/globe.svg" width="14" height="14"> Added support for the **hermes** harness.
- **[2026.04.22]**<img src="static/icons/rocket.svg" width="14" height="14"> Added support for the **claude-code-chrome-extension** harness — Claude Code CLI + [Claude in Chrome](https://code.claude.com/docs/en/chrome) extension.
- **[2026.04.20]**<img src="static/icons/screwdriver-wrench.svg" width="14" height="14"> Added support for the **claw-code** harness.
- **[2026.04.18]** <img src="static/icons/globe.svg" width="14" height="14"> &nbsp;Added support for the **browser-use** harness.
- **[2026.04.17]** <img src="static/icons/rocket.svg" width="14" height="14"> &nbsp;Added support for the **Codex** harness.
- **[2026.04.16]** <img src="static/icons/bolt.svg" width="14" height="14"> &nbsp;Added support for the **Claude Code** harness.
- **[2026.04.16]** Featured in **5 curated awesome-lists**: [awesome-harness-engineering](https://github.com/walkinglabs/awesome-harness-engineering), [Awesome-AI-Agents](https://github.com/Jenqyang/Awesome-AI-Agents), [awesome-computer-use](https://github.com/ranpox/awesome-computer-use), [Awesome-GUI-Agents](https://github.com/ZJU-REAL/Awesome-GUI-Agents), and [LLM-Agent-Benchmark-List](https://github.com/zhangxjohn/LLM-Agent-Benchmark-List).
- **[2026.04.15]** Sister project [**HarnessBench**](https://github.com/reacher-z/HarnessBench) launched — fixes the base model, varies the harness. Also on [PyPI](https://pypi.org/project/harness-bench/).
- **[2026.04.14]** <img src="static/icons/screwdriver-wrench.svg" width="14" height="14"> &nbsp;Added support for the **OpenCode** harness.
- **[2026.04.14]** Project featured on [**DeepWiki**](https://deepwiki.com/reacher-z/ClawBench) — ask questions about ClawBench in natural language.
- **[2026.04.11]** Honored to be [**#3 HuggingFace Paper of the Day**](https://huggingface.co/papers/2604.08523)!
- **[2026.04.11]** Paper released on [arXiv (2604.08523)](https://arxiv.org/abs/2604.08523). Dataset published on [HuggingFace](https://huggingface.co/datasets/NAIL-Group/ClawBench).

<br/>

<p align="center">
<img src="static/icons/globe.svg" width="24" height="24">&nbsp;<b>Live Websites</b>
&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;
<img src="static/icons/cube.svg" width="24" height="24">&nbsp;<b>Isolated Containers</b>
&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;
<img src="static/icons/shield-halved.svg" width="24" height="24">&nbsp;<b>Request Interceptor</b>
&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;
<img src="static/icons/layer-group.svg" width="24" height="24">&nbsp;<b>Five-Layer Recording</b>
</p>

<br/>

## <img src="static/icons/layer-group.svg" width="20" height="20"> Datasets

ClawBench ships **three** Hugging Face datasets — task definitions plus full execution traces for V1 and V2. All open, downloadable in one command. The benchmark itself is also mirrored on **TIGER-Lab** for visibility.

| Dataset                                                                                        | What's in it                                                                                                                                                                                       | Get it                                                        |
| ---------------------------------------------------------------------------------------------- | -------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- | ------------------------------------------------------------- |
| **[NAIL-Group/ClawBench](https://huggingface.co/datasets/NAIL-Group/ClawBench)** _(also mirrored at [TIGER-Lab/ClawBench](https://huggingface.co/datasets/TIGER-Lab/ClawBench))_ | Task definitions, rubrics, and metadata for V1 (153 tasks) and V2 (130 tasks) — what to attempt and how it's judged.                                                                               | `hf download --repo-type dataset NAIL-Group/ClawBench`        |
| **[NAIL-Group/ClawBenchV1Trace](https://huggingface.co/datasets/NAIL-Group/ClawBenchV1Trace)** | One directory per V1 model run, each with `recording.mp4`, `requests.jsonl`, `actions.jsonl`, `agent-messages.jsonl`, `interception.json`, and `run-meta.json` — everything we used to score the run. | `hf download --repo-type dataset NAIL-Group/ClawBenchV1Trace` |
| **[NAIL-Group/ClawBenchV2Trace](https://huggingface.co/datasets/NAIL-Group/ClawBenchV2Trace)** | Same 5-layer bundle for **V2** model runs. Rolling — new models added as they're evaluated.                                                                                                        | `hf download --repo-type dataset NAIL-Group/ClawBenchV2Trace` |

> The trace datasets are large; use `hf download --include "<pattern>"` to pull a single model or a single task.

> **🏆 Live leaderboard:** [`claw-bench.com/leaderboard`](https://claw-bench.com/leaderboard) (V2 default, two-stage scoring — interception + LLM judge). Full scoring formula in [`eval/scoring.md`](eval/scoring.md). Add your run: PR to [`leaderboard/results.csv`](https://huggingface.co/datasets/NAIL-Group/ClawBench/blob/main/leaderboard/results.csv).

## How It Works

```
   You pick a task            ClawBench spins up           Agent drives the         Interceptor captures
   from V1 or V2              an isolated Docker           browser: navigates,      every action across
   everyday scenarios         container + Chromium         fills forms, clicks      all 5 layers of data

   ┌──────────────┐           ┌──────────────┐           ┌──────────────┐           ┌──────────────┐
   │  "Book a pet │    ──►    │   Container  │    ──►    │   AI Agent   │    ──►    │   5 layers   │
   │   sitter on  │           │  + Chromium  │           │  browses the │           │  intercepted │
   │   Rover"     │           │  + Agent     │           │   live site  │           │  & recorded  │
   └──────────────┘           └──────────────┘           └──────────────┘           └──────────────┘
```

<br/>

# <img src="static/icons/robot.svg" width="28" height="28"> LLM Quick Start

Point your coding agent (Claude Code, Cursor, Copilot, etc.) at [`AGENTS.md`](AGENTS.md) and prompt away.

<br/>

# <img src="static/icons/person.svg" width="28" height="28"> Human Quick Start

Install ClawBench from PyPI for normal use:

```bash
uv tool install clawbench-eval
```

You can also use `pipx install clawbench-eval` or `python -m pip install clawbench-eval`.
The installed commands are still `clawbench`, `clawbench-run`, and
`clawbench-batch`.

For those want more granular control and contribution, clone the repo and run the root `uv` package entrypoint:

```bash
git clone https://github.com/reacher-z/ClawBench.git && cd ClawBench && ./run.sh
```

**Prerequisites:** [Python 3.11+](https://python.org), [uv](https://docs.astral.sh/uv/), and a container engine — [Docker](https://www.docker.com/) **or** [Podman](https://podman.io/). ClawBench auto-detects whichever is installed; force one with `export CONTAINER_ENGINE=docker` or `export CONTAINER_ENGINE=podman`.

<details>
<summary><b>Install Docker or Podman</b> (macOS / Linux / Windows)</summary>

#### macOS

```bash
# Option A — Docker Desktop (easiest, includes GUI)
brew install --cask docker
open -a Docker                 # launch and wait for the whale icon to settle

# Option B — Podman (rootless, no daemon, CLI only)
brew install podman
podman machine init            # one-time: downloads the Linux VM image
podman machine start           # must be running before any podman command
```

> **macOS Podman needs a VM.** `brew install podman` alone is not enough — Podman on macOS runs containers inside a small Linux VM, so you must `podman machine init && podman machine start` once after install or `podman info` will fail with `Cannot connect to Podman`.

#### Linux (Ubuntu / Debian)

```bash
# Option A — Podman (rootless by default, recommended)
sudo apt update && sudo apt install -y podman

# Option B — Docker
sudo apt install -y docker.io
sudo usermod -aG docker $USER  # log out / back in so your shell picks up the group
```

> **Rootful Docker ownership note:** with classic `sudo`-docker, files extracted from containers land owned by `root` on the host. ClawBench's driver detects this after each run and chowns `test-output/` back to your user automatically — but if you run other container tooling alongside, rootless Podman (or rootless Docker) avoids the issue entirely.

#### Windows

```powershell
# Option A — Docker Desktop (WSL2 backend)
winget install Docker.DockerDesktop
# then launch Docker Desktop from the Start menu and wait for it to be ready

# Option B — Podman
winget install RedHat.Podman
podman machine init
podman machine start
```

> Run the `uv run …` commands below from **PowerShell**, **WSL2**, or **Git Bash**. Like macOS, Windows Podman requires `podman machine init && podman machine start` before its first use.

</details>

**1. Configure models** — one-time setup.

If you installed from PyPI, run `clawbench` from the directory where you want
results and editable config to live. On first launch it creates local templates
under `models/`; use the TUI to add a model or edit the file directly:

```bash
clawbench
$EDITOR models/models.yaml
```

If you are working from a source checkout:

```bash
cp models/models.example.yaml models/models.yaml
$EDITOR models/models.yaml
```

PurelyMail credentials for disposable run emails are provided in the committed `.env`.
You only need to edit `.env` if you want to use your own PurelyMail account or enable optional HuggingFace upload.

> [!NOTE]
> **First run builds a container image** (Chromium + ffmpeg + noVNC + the selected agent harness dependencies). You'll see a live progress spinner with the current build step. Subsequent runs reuse the cached layers and finish in seconds.

**2. Run your first task** (pick one):

> [!TIP]
> **Recommended &rarr; Interactive TUI** &nbsp; guided model + test case selection
> ```bash
> clawbench         # PyPI install
> uv run clawbench  # source checkout
> ```
> If installed from PyPI, run `clawbench` directly. Needs an interactive terminal.
> For pipes / CI / non-TTY, use `clawbench-run` or `clawbench-batch` directly;
> from a source checkout, prefix commands with `uv run`.

**(b) Run one specific task against a specific model:**
```bash
uv run clawbench-run test-cases/v1/001-daily-life-food-uber-eats claude-sonnet-4-6
```
Once the container starts, the script prints a **noVNC URL** (e.g. `http://localhost:6080/vnc.html`) — open it in your browser to watch the agent operate in real-time. If port 6080 is already in use, an alternative port is chosen automatically.

Results land in `./test-output/<model>/<harness>-<case>-<model>-<timestamp>/` with the full five-layer recording. The default harness is `openclaw`; pass `--harness opencode` to use [opencode](https://opencode.ai), `--harness claude-code` to use [Claude Code](https://docs.anthropic.com/en/docs/claude-code), `--harness claude-code-chrome-extension` to use Claude Code + the [Claude in Chrome](https://code.claude.com/docs/en/chrome) extension (Microsoft Edge + local bridge, bypass stack so any LiteLLM-routed provider works), `--harness codex` to use [OpenAI Codex CLI](https://github.com/openai/codex), `--harness claw-code` to use [claw-code](https://github.com/ultraworkers/claw-code), `--harness browser-use` to use [browser-use](https://github.com/browser-use/browser-use) (Python framework, routed via LiteLLM), `--harness hermes` to use [Hermes Agent](https://github.com/NousResearch/hermes-agent) with native browser tools attached to ClawBench Chrome via CDP, or `--harness pi` to use [Pi](https://pi.dev/) with pinned [pi-browser-harness](https://pi.dev/packages/pi-browser-harness) browser tools attached to the same ClawBench Chrome CDP endpoint.

**(c) Drive the browser yourself via noVNC** — produces a human reference run:
```bash
uv run clawbench-run test-cases/v1/001-daily-life-food-uber-eats --human
```
Open the noVNC URL the script prints, complete the task by hand, then close the tab. Port is auto-assigned if 6080 is busy.

**(d) Pair with an external browser agent** — run in Human mode, open the noVNC URL, and let an external browser agent control that browser session while ClawBench records and intercepts it.

<details>
<summary><b>Develop from source</b> &nbsp;— clone + ``./run.sh`` for contributors</summary>

Prefer the repo checkout if you want to modify the driver, the bundled V1/V2 test cases, or the container build itself.

```bash
git clone https://github.com/reacher-z/ClawBench.git && cd ClawBench
cp models/models.example.yaml models/models.yaml   # edit: add your model API keys
# .env is already provided for PurelyMail; edit only for your own creds or HF upload
./run.sh                                           # interactive TUI
uv run clawbench-run \
  test-cases/v1/001-daily-life-food-uber-eats claude-sonnet-4-6   # single run
uv run clawbench-run \
  test-cases/v1/001-daily-life-food-uber-eats --human             # human mode
```

This path gives you live-reload on ``src/``, ``src/clawbench/runtime/chrome-extension/``, and all suites under ``test-cases/`` — useful when iterating on the harness itself.

</details>

<br/>

# <img src="static/icons/chart-bar.svg" width="28" height="28"> ClawBench-Lite

**New here? Run this first.** [`test-cases/v1-lite/`](test-cases/v1-lite/) is a **20-task curated subset** of the V1 153-task corpus, selected for household-name sites, real-world relevance, difficulty, and category diversity. It matches the 20-tasks-per-source convention of [browser-use/benchmark](https://github.com/browser-use/benchmark) and gives you a credible signal at a fraction of the full-benchmark cost.

Tier distribution: **flagship 9 / core 8 / wildcard 3** — spanning daily life (OpenTable, DoorDash, Instacart, TaskRabbit), entertainment (Eventbrite, Goodreads, Fandango), creation (Asana, Mailchimp, Squarespace), travel (Airbnb), education (LeetCode), dev-tech (GitHub), academia (Overleaf), personal management (1Password), and more. All Lite tasks are judged by [`eval/agentic_eval.md`](eval/agentic_eval.md) regardless of `url_pattern` shape.

The Lite suite is a first-class task directory: run it with `--cases-suite v1-lite`, or inspect the link-backed task files in [`test-cases/v1-lite/`](test-cases/v1-lite/).

<br/>

# <img src="static/icons/play.svg" width="28" height="28"> Demos

Each ClawBench run produces a full MP4 session recording. See the [project page](https://claw-bench.com) for V1 task recordings.

<br/>

# <img src="static/icons/circle-question.svg" width="28" height="28"> Example Walkthrough

Curious what one task actually looks like, start to finish? Here's task **001** end to end.

**The task** — from [`test-cases/v1/001-daily-life-food-uber-eats/task.json`](test-cases/v1/001-daily-life-food-uber-eats/task.json):

```json
{
  "instruction": "On Uber Eats, order delivery: one Pad Thai, deliver to home address, note \"no peanuts\"",
  "time_limit": 30,
  "eval_schema": {
    "url_pattern": "__PLACEHOLDER_WILL_NOT_MATCH__",
    "method": "POST"
  }
}
```

The agent gets this `instruction` verbatim, plus read-only access to `/my-info/alex_green_personal_info.json` (the dummy user's name, home address, phone, date of birth) and a disposable email account for any sign-in prompt. It has **30 minutes** to reach a `POST` request — any longer and the container is killed.

**What the agent does** (the happy path):

1. Navigates to `ubereats.com`
2. Reads the dummy user's home address from `/my-info/alex_green_personal_info.json` and enters it in the delivery-address box
3. Searches for **"Pad Thai"** in the food search
4. Picks a restaurant that has Pad Thai available for delivery to that address
5. Opens the item detail page, finds the customization or special-instructions field, enters **"no peanuts"**
6. Adds one to cart, opens the cart, and handles any sign-in prompt using the disposable email credentials
7. Reaches checkout, taps **Place Order**

**What the interceptor catches** — that final *Place Order* tap fires a `POST` request. ClawBench's request interceptor sits in front of the browser and **captures the outbound request before it reaches Uber Eats's servers**, so the dummy user is never actually charged. At the exact moment of interception, all five recording layers (MP4 video, PNG screenshots, HTTP traffic, browser actions, agent messages) are frozen into `/data/`.

**How the judge decides PASS / FAIL** — task 001's `url_pattern` is the intentional sentinel `__PLACEHOLDER_WILL_NOT_MATCH__`, which means **no request path can mechanically match**. The verdict comes from the agentic judge in [`eval/agentic_eval.md`](eval/agentic_eval.md), which replays the five-layer recording against a human reference run and checks four things:

- Did the agent actually reach the final checkout step?
- Is the cart exactly **one** Pad Thai (not two, not a combo)?
- Is the delivery address the user's home address from `alex_green_personal_info.json`?
- Does the order carry the **"no peanuts"** note in the instructions field?

All four must hold for a **PASS**. Miss any one and it's a **FAIL** with evidence from the recording pinned to the failing criterion. This per-task rubric is what makes ClawBench judge-sensitive rather than URL-regex-sensitive — see [`eval/README.md`](eval/README.md) for the full rubric format and [`eval/agentic_eval.md`](eval/agentic_eval.md) for the judge prompt.

<br/>

# <img src="static/icons/chart-bar.svg" width="28" height="28"> Results

<div align="center">

**Success rate (%) of 6 frontier AI agents on ClawBench V1**

</div>

| Rank  | Model                 | Overall  |  Daily   | Finance  |   Work   |   Dev    | Academic |  Travel  |  Social  |   Pets   |
| :---: | --------------------- | :------: | :------: | :------: | :------: | :------: | :------: | :------: | :------: | :------: |
|   1   | **Claude Sonnet 4.6** | **33.3** |   44.2   | **50.0** |   19.0   |   11.1   | **50.0** |   23.1   | **38.9** | **18.2** |
|   2   | GLM-5                 |   24.2   | **30.8** |   16.7   | **38.1** |   16.7   |   28.6   |   0.0    |   16.7   | **18.2** |
|   3   | Gemini 3 Flash        |   19.0   |   15.4   |   33.3   |   23.8   | **22.2** |   28.6   | **30.8** |   11.1   |   0.0    |
|   4   | Claude Haiku 4.5      |   18.3   |   15.4   |   22.2   |   19.0   | **27.8** |   21.4   |   7.7    |   16.7   | **18.2** |
|   5   | GPT-5.4               |   6.5    |   9.6    |   0.0    |   0.0    |   11.1   |   7.1    |   7.7    |   0.0    |   9.1    |
|   6   | Gemini 3.1 Flash Lite |   3.3    |   1.9    |   0.0    |   0.0    |   5.6    |   14.3   |   0.0    |   0.0    |   9.1    |

<details>
<summary><b>Task Categories (V1: 15 categories, 153 tasks)</b></summary>

| Category                  | Tasks | Example Platforms                                             |
| ------------------------- | :---: | ------------------------------------------------------------- |
| Daily Life                |  21   | Uber Eats, DoorDash, Instacart, Zillow, Craigslist            |
| Entertainment & Hobbies   |  15   | Ticketmaster, AMC Theatres, Topgolf, Crunchyroll              |
| Creation & Initialization |  13   | Squarespace, Wix, Webflow, Ghost, Substack                    |
| Rating & Voting           |  10   | Trustpilot, G2, Goodreads, RateMyProfessors                   |
| Travel                    |   9   | Booking.com, Expedia, Airbnb, TripAdvisor                     |
| Education & Learning      |   9   | Coursera, Udemy, Khan Academy, Duolingo                       |
| Office & Secretary        |   9   | Google Calendar, Slack, Notion, Trello                        |
| Beauty & Personal Care    |   9   | Sephora, Ulta, Glossier                                       |
| Job Search & HR           |   8   | LinkedIn, Greenhouse, Lever, Workday                          |
| Pet & Animal Care         |   8   | Chewy, Petco, Rover                                           |
| Personal Management       |   6   | Mint, YNAB, Todoist                                           |
| Shopping & Commerce       |   6   | Amazon, eBay, Etsy, Target                                    |
| Nonprofit & Charity       |   6   | GoFundMe, DonorsChoose                                        |
| Academia & Research       |   5   | Google Scholar, Semantic Scholar, OpenReview                  |
| Finance & Investment      |   4   | Robinhood, Fidelity, Coinbase                                 |
| Others                    |  15   | Automation, Dev & Tech, Government, Home Services, Automotive |

</details>

<br/>

## How ClawBench compares

| Benchmark                                                   | Domain               | Environment              | Task count | ClawBench difference                                  |
| ----------------------------------------------------------- | -------------------- | ------------------------ | ---------- | ----------------------------------------------------- |
| [WebArena](https://webarena.dev)                            | Synthetic web apps   | Self-hosted replicas     | 812        | Live consumer sites, not admin UIs on hosted replicas |
| [GAIA](https://huggingface.co/datasets/gaia-benchmark/GAIA) | General assistants   | Closed-book text + tools | 466        | Browser-centric; end-to-end task execution            |
| [SWE-bench](https://www.swebench.com)                       | Software engineering | GitHub repos             | 2,294      | Non-code; everyday consumer workflows                 |
| [BrowserGym](https://github.com/ServiceNow/BrowserGym)      | Web agents           | Headless sandbox         | —          | Cloud-parity; records real user journeys              |
| [Mind2Web](https://github.com/OSU-NLP-Group/Mind2Web)       | Web navigation       | Static traces            | 2,350      | Dynamic live websites, not replayed traces            |

ClawBench's niche: **live consumer websites, everyday tasks, end-to-end recording**. If you want a controlled sandbox or replayed traces, the projects above are excellent. If you want to know whether your agent can actually order food or book a flight *today*, this is the benchmark for that.

<br/>

## Architecture

<details>
<summary>Container internals</summary>

```
┌─────────────────────────────────────────────────┐
│  Container (Docker / Podman)                    │
│                                                 │
│  ┌───────────┐   DOM events  ┌──────────────┐   │
│  │ content.js├──────────────►│ background.js│   │
│  │ (per tab) │               │  (service    │   │
│  └───────────┘               │   worker)    │   │
│                              └──┬──────┬────┘   │
│                                 │      │        │
│                         actions │      │ screenshots
│                                 │      │        │
│  ┌──────────┐            ┌──────▼──────▼────┐   │
│  │  Xvfb    │◄──ffmpeg──►│  FastAPI Server  │   │
│  │ :99      │  x11grab   │  :7878           │   │
│  └──────────┘            └──────────────────┘   │
│                                  │              │
│  ┌──────────┐            ┌───────▼─────────┐    │
│  │ Chromium │            │     /data       │    │
│  │ :9222 CDP│            │  actions.jsonl  │    │
│  └──────────┘            │  requests.jsonl │    │
│                          │  screenshots/   │    │
│                          │  recording.mp4  │    │
│                          └─────────────────┘    │
└─────────────────────────────────────────────────┘
```

</details>

<br/>

# <img src="static/icons/terminal.svg" width="28" height="28"> CLI

```bash
# Interactive TUI (recommended):
./run.sh

# Single run:
uv run clawbench-run test-cases/v1/001-daily-life-food-uber-eats claude-sonnet-4-6

# Human mode (you control the browser via noVNC):
uv run clawbench-run test-cases/v1/001-daily-life-food-uber-eats --human

# Batch (all models x cases 1-50, 3 concurrent):
uv run clawbench-batch --all-models --case-range 1-50 --max-concurrent 3

# Batch all V1 tasks from test-cases/v1/:
uv run clawbench-batch --models claude-sonnet-4-6 --all-cases --max-concurrent 3

# Batch all V2 tasks from test-cases/v2/:
uv run clawbench-batch --models claude-sonnet-4-6 --cases-suite v2 --all-cases --max-concurrent 3

# Batch a custom case directory:
uv run clawbench-batch --models claude-sonnet-4-6 --cases-dir custom-cases --all-cases
```

V1 tasks are in [`test-cases/v1/`](test-cases/v1/) (153 tasks). V2 tasks are in `test-cases/v2/` (130 tasks), and Lite is in `test-cases/v1-lite/` (20 tasks). All suites use [`test-cases/task.schema.json`](test-cases/task.schema.json). For test case authoring details, see [CONTRIBUTING.md](CONTRIBUTING.md). For output structure and evaluation guidance, see [eval/README.md](eval/README.md).

<br/>

# <img src="static/icons/chart-bar.svg" width="28" height="28"> Evaluation

Evaluation is a **post-session** step -- first run agents to collect trajectories, then evaluate them against human reference runs.

```
 1. Run agents (root uv package)   2. Evaluate (eval/)
 ─────────────────────────         ────────────────────────────────
 ./run.sh / clawbench-batch ──►    Claude Code subagents compare
 produces test-output/             agent vs human trajectories
   with 5-layer recordings         under eval/agentic_eval.md rubric
```

The evaluator compares each agent trajectory against a human reference trajectory across all five recording layers (video, screenshots, HTTP traffic, browser actions, agent messages), then outputs PASS/FAIL with evidence-backed justification.

See [eval/README.md](eval/README.md) for the full evaluation guide and Claude Code prompt template.

<br/>

# <img src="static/icons/circle-question.svg" width="28" height="28"> FAQ

<details>
<summary><b>What data does each run produce?</b></summary>

Each session records five layers of synchronized data under `/data/`:

| Layer              | File                   | Description                                                     |
| ------------------ | ---------------------- | --------------------------------------------------------------- |
| Session replay     | `recording.mp4`        | Full session video (H.264, 15fps)                               |
| Action screenshots | `screenshots/*.png`    | Timestamped PNG per browser action                              |
| Browser actions    | `actions.jsonl`        | Every DOM event (click, keydown, input, pageLoad, scroll, etc.) |
| HTTP traffic       | `requests.jsonl`       | Every HTTP request with headers, body, and query params         |
| Agent messages     | `agent-messages.jsonl` | Full agent conversation transcript (thinking, text, tool calls) |

For the Pi harness, `agent-messages.jsonl` is filtered Pi JSON mode output, including `message_start`/`message_end` events, `tool_execution_*` events, tool-call content blocks, and `thinking` blocks when the selected model emits reasoning. Streaming `message_update` fragments, including `*_delta` rows, are omitted because complete assistant messages are already preserved in `message_end` events.

Harness diagnostic logs such as Pi's `agent.log` and `proxy.log` are not copied into the final `data/` directory.

The interceptor result is saved to `interception.json`.

</details>

<details>
<summary><b>How does the request interceptor work?</b></summary>

The interceptor blocks critical, irreversible HTTP requests (checkout, form submit, email send) to prevent real-world side effects. It connects to Chrome via CDP's `Fetch` domain and matches requests against the eval schema (`url_pattern` regex + `method` + optional `body`/`params`). When triggered, it saves the blocked request to `interception.json`, kills the agent, and stops recording.

The interceptor does **not** validate task completion -- evaluation is handled separately by evaluators post-session.

For tasks behind payment walls (agent has no valid credit card), the eval schema uses a placeholder pattern that never matches, so the session runs until timeout.

</details>

<details>
<summary><b>What is the synthetic user profile?</b></summary>

Each container gets a `/my-info/` directory with a dummy user identity (Alex Green): personal info JSON, email credentials, and a resume PDF. The email is a fresh disposable PurelyMail address generated per run. The agent reads these files when it needs to fill forms, register accounts, etc.

Source templates: `src/clawbench/runtime/shared/alex_green_personal_info.json` (profile) and `src/clawbench/utils/resume_template.json` (resume).

</details>

<details>
<summary><b>Can I use Podman instead of Docker?</b></summary>

Yes. Set `export CONTAINER_ENGINE=podman`. The framework auto-detects whichever is available. Podman works without root privileges.

</details>

<details>
<summary><b>What tools can the agent use?</b></summary>

All supported harnesses run inside the same container recording and interception environment. CLI/MCP harnesses expose the browser tool plus a restricted set of read-only shell commands (`ls`, `cat`, `find`, `grep`, `head`, `tail`, `jq`, `wc`, etc.); commands that could bypass the browser (`curl`, `python`, `node`, `wget`) are blocked. Hermes and Pi use native browser/file tools attached to the same ClawBench Chrome CDP endpoint. The Pi harness intentionally allowlists only read-only file tools and browser interaction tools; `bash`, `write`, `edit`, `browser_http_get`, and `browser_run_script` are not enabled. The agent instruction also explicitly requires browser-only task completion.

</details>

<details>
<summary><b>How do I add a new test case?</b></summary>

See [CONTRIBUTING.md](CONTRIBUTING.md). In short: create a directory under the target corpus (`test-cases/v1/` for V1 or `test-cases/v2/` for V2) with a `task.json` conforming to `test-cases/task.schema.json`, define the eval schema, test with human mode, and submit a PR.

</details>

<br/>

## Contributing

We welcome contributions -- especially new test cases. If you've ever ordered groceries, booked an appointment, or filed a form online, you already know how to write one. Most PRs are a single JSON file and land in under a day.

**Quick wins:**

- [Add a new test case](CONTRIBUTING.md#adding-a-new-test-case) (~30 min, no container expertise needed)
- [Add a new category](CONTRIBUTING.md#what-were-looking-for) of 10+ tasks &rarr; co-author invitation on the next paper revision
- [Submit a new model](CONTRIBUTING.md#what-were-looking-for) to the public leaderboard
- Browse [good first issues](https://github.com/reacher-z/ClawBench/labels/good%20first%20issue)

See [CONTRIBUTING.md](CONTRIBUTING.md) for the full guide and contributor recognition policy.

## Community

Come hang out with researchers, builders, and contributors working on real-world browser agents.

<table>
<tr>
<td align="center" width="33%">
<a href="https://discord.gg/clawbench">
<img src="https://img.shields.io/badge/Discord-Join-5865F2?style=for-the-badge&logo=discord&logoColor=white" alt="Discord">
</a>
<br/>
<sub><b>English community</b><br/>Agent builders, researchers, contributors</sub>
</td>
<td align="center" width="33%">
<a href="static/community/wechat_grp_422.jpg">
<img src="https://img.shields.io/badge/%E5%BE%AE%E4%BF%A1%E7%BE%A4-%E5%8A%A0%E5%85%A5-07C160?style=for-the-badge&logo=wechat&logoColor=white" alt="微信群">
</a>
<br/>
<sub><b>中文社区</b><br/>研究者、开发者、贡献者交流</sub>
</td>
<td align="center" width="33%">
<a href="https://github.com/reacher-z/ClawBench/discussions">
<img src="https://img.shields.io/badge/GitHub-Discussions-181717?style=for-the-badge&logo=github&logoColor=white" alt="GitHub Discussions">
</a>
<br/>
<sub><b>Async Q&A</b><br/>Searchable, long-form, permanent</sub>
</td>
</tr>
</table>

Use the Discord and GitHub Discussions links for ongoing community support. For 微信群, use the QR link above.

## Frequently Asked Questions

**What is ClawBench?**
ClawBench is an open-source benchmark for AI browser agents — the systems (GPT-based, Claude-based, or open) that drive a real web browser to complete a user's task. V1 measures whether the agent actually finishes 153 everyday online tasks across 144 live websites; V2 adds a 130-task corpus in `test-cases/v2/`. It measures completion, not whether the agent produces the right-looking text.

**What kinds of tasks does ClawBench cover?**
Fifteen life categories: food delivery, travel booking, job applications, shopping, housing search, email and calendar management, academic research, software development, learning platforms, and more. Every task is something a normal person might do in a normal week, on a real website.

**Are 153 tasks enough for evaluation?**
Yes for a V1 benchmark signal: the 153 tasks span 144 live websites and 15 life categories, and each full run is expensive because it uses isolated containers, real websites, five-layer recording, and post-session judgment against human references. V2 adds another 130 tasks in `test-cases/v2/`. For cheaper iteration, start with the 20-task [`test-cases/v1-lite/`](test-cases/v1-lite/) subset.

**How is a task judged successful?**
Each task runs in an isolated browser container with a five-layer recording: video, screenshots, network requests, browser actions, and agent messages. The evaluator compares the agent trajectory against a human reference run and assigns PASS or FAIL with evidence from the recording.

**Do CAPTCHA or bot checks dominate failures?**
If an agent encounters a CAPTCHA, it must attempt it. We have seen cases where frontier models are able to solve some CAPTCHAS. CAPTCHA failures can reflect model behavior, browser-control stack limits, or site defenses.

**What's the current top score?**
33.3% — roughly one task in three — from the strongest frontier model we evaluated. The majority of tasks still defeat every model we've tested; the headroom is real, and the benchmark is not saturated.

**Which harness are the published model results based on?**
The repo default is `openclaw`, and all published results are based on this harness. Though we do support other harnesses listed in `src/clawbench/runtime/harnesses/` which can be selected with `--harness`.

**Is ClawBench tightly coupled to OpenClaw?**
No. OpenClaw is the default harness, but ClawBench supports interchangeable harnesses listed in `src/clawbench/runtime/harnesses/`.

**Can ClawBench evaluate CLI agents?**
Yes. ClawBench is a browser-task benchmark, but CLI and coding-agent harnesses can drive the same instrumented Chromium session using native tools or MCPs.

**How do I reproduce a published score?**
From a source checkout, configure `models/models.yaml`, then run `uv run clawbench`. The TUI builds the container image and runs local tasks against your model of choice. For batch runs, use `--all-cases` for the default V1 suite, `--cases-suite v2 --all-cases` for V2, or `--cases-suite v1-lite --all-cases` for Lite.

**Will newer models be added?**
Yes. New model runs can be submitted or requested through the contribution and issues. We'll also update new model scores when we get a chance to run them.

**Is ClawBench safe to run against live websites?**
The runner uses a hardened container with a request interceptor that blocks purchases, account creation, outbound email sends, and similar irreversible actions by default. Tasks that need to *simulate* those actions (e.g., "add to cart and checkout") terminate at the last reversible step. You can relax the interceptor per-task if your research requires it.

**Can I contribute new tasks or harnesses?**
Yes. V1 tasks live in `test-cases/v1/`; V2 tasks live in `test-cases/v2/`; Lite tasks live in `test-cases/v1-lite/`. See `CONTRIBUTING.md` for the task schema and validation flow.

**How does ClawBench relate to HarnessBench?**
Same scoring pipeline, orthogonal axis. ClawBench fixes the harness and varies the model; HarnessBench fixes the model and varies the harness. They share the V1 153-task corpus, the five-layer recording, and the agentic evaluator — so numbers are directly comparable.

## Citation

If you use ClawBench in your research, please cite:

```bibtex
@misc{zhang2026clawbench,
  title         = {ClawBench: Can AI Agents Complete Everyday Online Tasks?},
  author        = {Yuxuan Zhang and Yubo Wang and Yipeng Zhu and Penghui Du and Junwen Miao and Xuan Lu and Wendong Xu and Yunzhuo Hao and Songcheng Cai and Xiaochen Wang and Huaisong Zhang and Xian Wu and Yi Lu and Minyi Lei and Kai Zou and Huifeng Yin and Ping Nie and Liang Chen and Dongfu Jiang and Wenhu Chen and Kelsey R. Allen},
  year          = {2026},
  eprint        = {2604.08523},
  archivePrefix = {arXiv},
  primaryClass  = {cs.AI},
  url           = {https://arxiv.org/abs/2604.08523}
}
```

## Core Contributors

<table>
<tr>
<td align="center">
<a href="https://github.com/reacher-z">
<img src="https://github.com/reacher-z.png" width="80" height="80" style="border-radius:50%"><br/>
<sub><b>Yuxuan Zhang</b></sub>
</a>
</td>
<td align="center">
<a href="https://github.com/Wyyyb">
<img src="https://github.com/Wyyyb.png" width="80" height="80" style="border-radius:50%"><br/>
<sub><b>Yubo Wang</b></sub>
</a>
</td>
<td align="center">
<a href="https://github.com/Perry2004">
<img src="https://github.com/Perry2004.png" width="80" height="80" style="border-radius:50%"><br/>
<sub><b>Perry Zhu</b></sub>
</a>
</td>
<td align="center">
<a href="https://github.com/eternaldolphin">
<img src="https://github.com/eternaldolphin.png" width="80" height="80" style="border-radius:50%"><br/>
<sub><b>Penghui Du</b></sub>
</a>
</td>
<td align="center">
<a href="https://github.com/MEKSAAA">
<img src="https://github.com/MEKSAAA.png" width="80" height="80" style="border-radius:50%"><br/>
<sub><b>Junwen Miao</b></sub>
</a>
</td>
</tr>
</table>

## Advisors

<table>
<tr>
<td align="center">
<a href="https://github.com/k-r-allen">
<img src="https://github.com/k-r-allen.png" width="80" height="80" style="border-radius:50%"><br/>
<sub><b>Kelsey R. Allen</b></sub>
</a>
</td>
<td align="center">
<a href="https://github.com/wenhuchen">
<img src="https://github.com/wenhuchen.png" width="80" height="80" style="border-radius:50%"><br/>
<sub><b>Wenhu Chen</b></sub>
</a>
</td>
<td align="center">
<a href="https://github.com/jdf-prog">
<img src="https://github.com/jdf-prog.png" width="80" height="80" style="border-radius:50%"><br/>
<sub><b>Dongfu Jiang</b></sub>
</a>
</td>
<td align="center">
<a href="https://github.com/chenllliang">
<img src="https://github.com/chenllliang.png" width="80" height="80" style="border-radius:50%"><br/>
<sub><b>Liang Chen</b></sub>
</a>
</td>
</tr>
</table>

## Support ClawBench

If ClawBench is useful for your research or product work,
the single most helpful thing you can do is **[star the repo](https://github.com/reacher-z/ClawBench)** —
it surfaces the benchmark to other AI-agent researchers and helps us justify
continued dataset curation.

<p align="center">
<a href="https://github.com/reacher-z/ClawBench">
<img src="https://img.shields.io/badge/%E2%98%85%20Star%20this%20repo-181717?style=for-the-badge&logo=github&logoColor=white" alt="Star this repo">
</a>
</p>

Open to contributions — new test cases, bug fixes, or evaluation submissions for a model we haven't scored yet. See [`CONTRIBUTING.md`](CONTRIBUTING.md).

<p align="center">
<a href="https://github.com/reacher-z/ClawBench/graphs/contributors">
<img src="https://contrib.rocks/image?repo=reacher-z/ClawBench" alt="Contributors">
</a>
</p>

## Star History

<a href="https://star-history.com/#reacher-z/ClawBench&Date">
  <picture>
    <source media="(prefers-color-scheme: dark)" srcset="https://api.star-history.com/svg?repos=reacher-z/ClawBench&type=Date&theme=dark" />
    <source media="(prefers-color-scheme: light)" srcset="https://api.star-history.com/svg?repos=reacher-z/ClawBench&type=Date" />
    <img alt="ClawBench Star History" src="https://api.star-history.com/svg?repos=reacher-z/ClawBench&type=Date" width="600" />
  </picture>
</a>

## License & Acknowledgments

Apache 2.0 -- see [LICENSE](LICENSE).

Built with [OpenClaw](https://github.com/openclaw/openclaw), [opencode](https://opencode.ai), [Claude Code](https://docs.anthropic.com/en/docs/claude-code), the [Claude in Chrome](https://code.claude.com/docs/en/chrome) extension, [OpenAI Codex CLI](https://github.com/openai/codex), [browser-use](https://github.com/browser-use/browser-use), [claw-code](https://github.com/ultraworkers/claw-code), [Hermes Agent](https://github.com/NousResearch/hermes-agent), and [Pi](https://pi.dev/) with [pi-browser-harness](https://pi.dev/packages/pi-browser-harness) (selectable harnesses), [Microsoft Playwright MCP](https://github.com/microsoft/playwright-mcp) (browser control bridge for the opencode, claude-code, codex, and claw-code harnesses), [LiteLLM](https://github.com/BerriAI/litellm) (API translation proxy for the claude-code, claude-code-chrome-extension, codex, browser-use, claw-code, and pi harnesses), [noVNC](https://github.com/novnc/noVNC) (MPL 2.0), and [websockify](https://github.com/novnc/websockify) (LGPL 3.0).
