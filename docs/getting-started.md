# Getting started

[Documentation index](README.md) · [CLI reference](cli.md)

## Prerequisites

Use Python 3.11+, [uv](https://docs.astral.sh/uv/), and a running Docker or
Podman engine. ClawBench checks for Docker first, then Podman; set
`CONTAINER_ENGINE=docker` or `CONTAINER_ENGINE=podman` to choose explicitly.
Even with a remote browser, the native runner needs a container for the agent.

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

## Install

Choose one workflow. Commands in the rest of this guide use the installed
package; in a source checkout, prefix them with `uv run`.

### Installed package

```bash
uv tool install clawbench-eval
clawbench
```

`pipx install clawbench-eval` and `python -m pip install clawbench-eval` also
work. Run `clawbench` in the directory where you want your configuration and
results. The TUI guides you through model configuration and task selection.
It requires an interactive terminal.

### Source checkout

```bash
git clone https://github.com/TIGER-AI-Lab/ClawBench.git
cd ClawBench
cp models/models.example.yaml models/models.yaml
# Edit models/models.yaml with your model and judge API settings.
uv run clawbench
```

`./run.sh` also launches the TUI. For development checks and the source map,
see [Contributing](../CONTRIBUTING.md#code-changes) and
[Source layout](../src/README.md). Runtime files are copied into container
images; rebuild after changing them instead of running with `--no-build`.

## Configure models

The TUI's **Configure models** menu edits `models/models.yaml`. To configure
an installed package without a TTY, initialize its templates and copy the
example yourself:

```bash
clawbench-run --help
cp models/models.example.yaml models/models.yaml
# Edit models/models.yaml before running a task.
```

Only copy the example when creating a new configuration; keep an existing
`models/models.yaml`. Each top-level key must be a model ID accepted by your
provider, because the runner sends that key as the model name:

```yaml
your-provider-model-id:
  api_key: "your-api-key"
  base_url: https://your-provider.example/v1
  api_type: openai-completions
```

Replace all placeholders. The [example configuration](../models/models.example.yaml)
and [model schema](../models/model.schema.json) describe supported API types
and optional settings.

The default request judge is `deepseek-v4-pro`. Configure that entry too,
select another configured model with `--judge <model-id>`, or use `--no-judge`
to collect trajectories with interception-only results. Model and judge
configuration are separate; selecting an agent model does not configure the judge.

PurelyMail credentials for disposable run emails are bundled with ClawBench.
Workspace `.env` values can override them. Set both `HF_TOKEN` and `HF_REPO_ID`
to enable automatic output uploads, or pass `--no-upload` to keep runs local.
See the [environment reference](cli.md#environment-variables).

## Run a task

Use `clawbench` for guided selection, or run a single case directly:

```bash
clawbench-run test-cases/v1/886-entertainment-hobbies-experience-topgolf your-provider-model-id
```

Replace the model ID with a configured key. Bundled case paths work in an
installed package too. The default harness is `openclaw`.

The first run builds the browser and harness images; later builds reuse
cached layers. With the local browser, open the printed noVNC URL to watch
the run. Outputs go to
`test-output/<model>/<harness>-<case>-<model>-<timestamp>/`.
For artifacts and provenance, see the [trace cookbook](trace-cookbook.md).

For a human reference run, omit the model:

```bash
clawbench-run test-cases/v1/886-entertainment-hobbies-experience-topgolf --human
```

Open the noVNC URL, complete the task, then close the tab to end the session.

## Run a batch

```bash
clawbench-batch --models your-provider-model-id --cases-suite v2 --all-cases
```

The batch CLI defaults to V2; select the suite explicitly for reproducible
commands. Use `--cases-suite v1` for V1 or `--cases-suite v1-lite`
for the 20-task subset, `--max-concurrent N` for parallelism, and `--dry-run`
to inspect the job matrix before running. The CLI reference lists
[all suite selectors and execution options](cli.md#clawbench-batch).

After a run, inspect the summary or generate a report:

```bash
clawbench-analyze --runs-dir test-output/batch-<timestamp> --out report.md
```

The native request judge evaluates intercepted requests. Tasks with a
placeholder interception rule need separate trajectory evaluation; see the
[walkthrough](walkthrough.md) and [evaluation guide](../eval/README.md).

## Choose a harness

The harness drives the browser; the model supplies its reasoning. Select a
harness with `--harness <name>` on `clawbench-run` or `clawbench-batch`.

| Harness | `--harness` | How it drives the browser | Use it when |
| --- | --- | --- | --- |
| [OpenClaw](https://github.com/openclaw/openclaw) | `openclaw` *(default)* | Native browser tools over CDP | Running the default harness |
| [Hermes Agent](https://github.com/NousResearch/hermes-agent) | `hermes` | Native browser tools over CDP | You want the configuration behind most V2 leaderboard rows |
| [opencode](https://opencode.ai) | `opencode` | Playwright MCP bridge | Comparing coding-agent scaffolds |
| [Claude Code](https://docs.anthropic.com/en/docs/claude-code) | `claude-code` | Playwright MCP bridge | Comparing coding-agent scaffolds |
| Claude Code + [Claude in Chrome](https://code.claude.com/docs/en/chrome) | `claude-code-chrome-extension` | Chrome extension via a local bridge (Microsoft Edge) | Testing the extension stack; any LiteLLM-routed provider works |
| [OpenAI Codex CLI](https://github.com/openai/codex) | `codex` | Playwright MCP bridge | Comparing coding-agent scaffolds |
| [claw-code](https://github.com/ultraworkers/claw-code) | `claw-code` | Playwright MCP bridge | Comparing coding-agent scaffolds |
| [browser-use](https://github.com/browser-use/browser-use) | `browser-use` | Native browser framework, routed via LiteLLM | Comparing a purpose-built web agent |
| [Pi](https://pi.dev/) | `pi` | Pinned [pi-browser-harness](https://pi.dev/packages/pi-browser-harness) tools over CDP | Read-only tool allowlist, no shell |
| [WebBrain](../src/clawbench/runtime/harnesses/webbrain/README.md) | `webbrain` | Browser extension with a CDP driver | Testing WebBrain with a local browser and an OpenAI-compatible completions endpoint |
| — | `random-click` | Random clicks, no model | Establishing a floor baseline |
| — | `null` | Does nothing | Measuring harness/recording overhead |

Full registry: [`src/clawbench/runtime/harnesses/harnesses.yaml`](../src/clawbench/runtime/harnesses/harnesses.yaml).

## Other execution options

- [Browser runtimes](browser-runtimes.md): remote CDP, Kernel, and Browserbase.
- [Harbor](harbor.md): convert tasks and run them with Harbor's agents.
- [EdgeBench / SForge](edgebench.md): export tasks and score results.
- [ProRL](prorl-rl-env.md): submit RL rollouts through ProRL-Agent-Server.
- [FAQ](faq.md): task state, artifacts, scoring, and live-site behavior.
