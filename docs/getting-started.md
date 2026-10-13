# Getting started

[← ClawBench](../README.md) · [中文](getting-started.zh-CN.md)

## <img src="../assets/icons/rocket.svg" width="24" height="24"> Quick start

### Install

```bash
uv tool install clawbench-eval
```

`pipx install clawbench-eval` and `python -m pip install clawbench-eval` work too. This installs the interactive `clawbench` launcher and the runner, scoring, and analysis commands; see the [CLI reference](cli.md).

Contributors can use the [source checkout instructions](getting-started.md#develop-from-source) below. **Driving a coding agent?** Point it at [`AGENTS.md`](../AGENTS.md).

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

### 1. Configure models

One-time setup. If you installed from PyPI, run `clawbench` from the directory where you want results and editable config to live — on first launch it creates local templates under `models/`:

```bash
clawbench
$EDITOR models/models.yaml
```

From a source checkout:

```bash
cp models/models.example.yaml models/models.yaml
$EDITOR models/models.yaml
```

Scoring needs a judge. Add an API key for `deepseek-v4-pro` — the judge used for every published leaderboard row — before running any judged batch:

```yaml
deepseek-v4-pro:
  api_key: "sk-..."
  base_url: <api_base_url>
  api_type: openai-completions
```

PurelyMail credentials for disposable run emails are provided in the committed `.env`. You only need to edit `.env` to use your own PurelyMail account or to enable optional HuggingFace upload.

> [!NOTE]
> **First run builds a container image** (Chromium + ffmpeg + noVNC + the selected agent harness dependencies). You'll see a live progress spinner with the current build step. Subsequent runs reuse the cached layers and finish in seconds.

### 2. Run your first task

> [!TIP]
> **Recommended → interactive TUI**, with guided model + test case selection:
> ```bash
> clawbench         # PyPI install
> uv run clawbench  # source checkout
> ```
> Needs an interactive terminal. For pipes / CI / non-TTY, use `clawbench-run` or `clawbench-batch` directly.

**One task against one model:**

```bash
clawbench-run test-cases/v2/v2-1033-education-learning-registration-khanacademy your-model
```

Replace `your-model` with a key from `models/models.yaml`. This V2 task navigates to a Khan Academy lesson and has an active `GET` interception schema. From a source checkout, prefix the command with `uv run`.

Once the container starts, the script prints a **noVNC URL** (e.g. `http://localhost:6080/vnc.html`) — open it to watch the agent operate in real time. If port 6080 is taken, an alternative is chosen automatically. Results land in `./test-output/<model>/<harness>-<case>-<model>-<timestamp>/` with the full five-layer recording.

**A whole corpus:**

```bash
clawbench-batch --models your-model --cases-suite v2 --all-cases
```

`your-model` is a key you configured in step 1; `--cases-suite v2` runs the full V2 corpus (swap in `v1-lite` for the 20-task subset). Add `--max-concurrent N` to run tasks in parallel (default 2 locally, 1 with Kernel or Browserbase) and `--harness <name>` to pick an agent. Each task is intercepted and scored by the `deepseek-v4-pro` judge from step 1 — pass `--no-judge` to skip scoring. A `batch-summary.json` plus per-run recordings land under `./test-output/`.

Analyze a completed batch's Stage-1/Stage-2 rates, failure taxonomy, per-category results, and self-report gap:

```bash
clawbench-analyze --runs-dir test-output/batch-<timestamp> --out report.md
```

**By hand, to produce a human reference run:**

```bash
uv run clawbench-run test-cases/v1/001-daily-life-food-uber-eats --human
```

Open the noVNC URL, complete the task yourself, then close the tab. You can also leave the session open and let an **external browser agent** drive it while ClawBench records and intercepts.

### 3. Pick a harness

The harness is the agent scaffold that drives the browser; the model is a separate axis. Default is `openclaw`. Select one with `--harness <name>` on `clawbench-run` or `clawbench-batch`.

| Harness | `--harness` | How it drives the browser | Use it when |
| --- | --- | --- | --- |
| [OpenClaw](https://github.com/openclaw/openclaw) | `openclaw` *(default)* | Playwright MCP bridge | You want the reference configuration used by V1 results |
| [Hermes Agent](https://github.com/NousResearch/hermes-agent) | `hermes` | Native browser tools over CDP | You want the configuration behind most V2 leaderboard rows |
| [opencode](https://opencode.ai) | `opencode` | Playwright MCP bridge | Comparing coding-agent scaffolds |
| [Claude Code](https://docs.anthropic.com/en/docs/claude-code) | `claude-code` | Playwright MCP bridge | Comparing coding-agent scaffolds |
| Claude Code + [Claude in Chrome](https://code.claude.com/docs/en/chrome) | `claude-code-chrome-extension` | Chrome extension via a local bridge (Microsoft Edge) | Testing the extension stack; any LiteLLM-routed provider works |
| [OpenAI Codex CLI](https://github.com/openai/codex) | `codex` | Playwright MCP bridge | Comparing coding-agent scaffolds |
| [claw-code](https://github.com/ultraworkers/claw-code) | `claw-code` | Playwright MCP bridge | Comparing coding-agent scaffolds |
| [browser-use](https://github.com/browser-use/browser-use) | `browser-use` | Native browser framework, routed via LiteLLM | Comparing a purpose-built web agent |
| [Pi](https://pi.dev/) | `pi` | Pinned [pi-browser-harness](https://pi.dev/packages/pi-browser-harness) tools over CDP | Read-only tool allowlist, no shell |
| — | `random-click` | Random clicks, no model | Establishing a floor baseline |
| — | `null` | Does nothing | Measuring harness/recording overhead |

Full registry: [`src/clawbench/runtime/harnesses/harnesses.yaml`](../src/clawbench/runtime/harnesses/harnesses.yaml).

### 4. Other browser runtimes and frameworks

| I want to… | Where |
| --- | --- |
| Use a managed remote browser instead of a local container | [`docs/browser-runtimes.md`](browser-runtimes.md) — Kernel and Browserbase setup, options, and recordings |
| Run V2 through the Harbor framework (and run it fast) | [`docs/harbor.md`](harbor.md) — conversion, judge wiring, concurrency, troubleshooting |
| See every CLI command and flag | [`docs/cli.md`](cli.md) |

<details id="develop-from-source">
<summary><b>Develop from source</b> &nbsp;— clone + <code>./run.sh</code> for contributors</summary>

Prefer the repo checkout if you want to modify the driver, the bundled V1/V2 test cases, or the container build itself.

```bash
git clone https://github.com/TIGER-AI-Lab/ClawBench.git && cd ClawBench
cp models/models.example.yaml models/models.yaml   # edit: add your model API keys
# .env is already provided for PurelyMail; edit only for your own creds or HF upload
./run.sh                                           # interactive TUI
uv run clawbench-run \
  test-cases/v1/001-daily-life-food-uber-eats claude-sonnet-4-6   # single run
uv run clawbench-run \
  test-cases/v1/001-daily-life-food-uber-eats --human             # human mode
```

This path gives you live-reload on `src/`, `src/clawbench/runtime/chrome-extension/`, and all suites under `test-cases/` — useful when iterating on the harness itself.

</details>
