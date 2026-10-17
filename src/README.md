# ClawBench Source Layout

Start here when changing the framework. For running benchmarks, see the
[setup guide](../docs/getting-started.md) and [CLI reference](../docs/cli.md).
[CONTRIBUTING.md](../CONTRIBUTING.md#code-changes) covers development setup and checks.

## Directory Map

```text
src/clawbench/
  tui.py                         # Interactive configuration and launch menus
  runner/
    run.py                       # Single-run lifecycle
    batch.py                     # Model × task scheduling, resume, batch summaries
    judge.py                     # Request and answer judging
    run_support/
      config.py                  # Model config, environment, task-path resolution
      api_preflight.py           # Model API checks before a run
      harness_registry.py        # Load and validate the harness registry
      docker.py                  # Container build, execution, collection, cleanup
      browser_runtime/           # Local, remote CDP, Kernel, Browserbase providers
      email.py                   # Disposable email lifecycle
      task.py                    # Task validation, prompt and /my-info/ preparation
      resume.py                  # Render the synthetic resume template
      results.py                 # Artifact metrics and outcome classification
      metadata.py                # run-meta.json construction and redaction
      usage.py                   # Token usage and cost summaries
  eval/                          # Rescoring, analysis, reproduction, dataset adapters
  prorl/                         # ProRL submission client, payloads, mock, image assets
  utils/
    paths.py                     # Workspace, bundled asset, and runtime paths
    timeouts.py                  # Shared timeout calculations
    hf_upload.py                 # Optional output uploads
  runtime/
    runtime-server/              # CDP capture/interception; separate container uv project
    chrome-extension/            # Browser stealth patches
    harnesses/                   # Registry, base image, per-harness images and scripts
    harbor/                      # Harbor environment, preparation, verifier, cleanup
    shared/                      # Synthetic personal-info source
```

The root [pyproject.toml](../pyproject.toml) defines the host Python package.
The runtime server has its own [dependency project](clawbench/runtime/runtime-server/pyproject.toml).
Container builds use `src/clawbench/runtime/` as their build context.

## Entry Points

Console scripts are declared in [pyproject.toml](../pyproject.toml).
Use `uv run <command> --help` from a checkout for current arguments.

| Command | Implementation |
| --- | --- |
| `clawbench` (also `./run.sh`) | [tui.py](clawbench/tui.py) |
| `clawbench-run` | [runner/run.py](clawbench/runner/run.py) |
| `clawbench-batch` | [runner/batch.py](clawbench/runner/batch.py) |
| `clawbench-rescore`, `clawbench-analyze`, `clawbench-reproduce` | [eval/rescore.py](clawbench/eval/rescore.py), [analyze.py](clawbench/eval/analyze.py), [reproduce.py](clawbench/eval/reproduce.py) |
| `clawbench-harbor-adapt` | [eval/harbor_adapter.py](clawbench/eval/harbor_adapter.py) |
| `clawbench-edgebench-adapt`, `clawbench-edgebench-judge` | [eval/edgebench_adapter.py](clawbench/eval/edgebench_adapter.py), [edgebench_judge.py](clawbench/eval/edgebench_judge.py) |
| `clawbench-prorl-submit`, `clawbench-prorl-mock` | [prorl/submit.py](clawbench/prorl/submit.py), [mock_gateway.py](clawbench/prorl/mock_gateway.py) |

## Single-Run Workflow

[run.py](clawbench/runner/run.py) owns the native run lifecycle:

1. Resolve the task, model, judge, environment, and browser runtime; validate inputs.
2. Build images when needed, create a disposable email, and prepare `/my-info/`
   from the synthetic profile, resume template, and task attachments.
3. Start the browser session and harness container. The runtime server captures
   browser evidence and blocks requests matching the task's interception schema.
4. Wait for completion or timeout, collect container artifacts, and finalize
   provider recordings and browser cleanup.
5. Judge intercepted requests when enabled, write `judge.json` and
   `run-meta.json`, and optionally upload the output.
6. Clean up the container, email, temporary files, and browser session on exit.

[batch.py](clawbench/runner/batch.py) builds images once and launches single-run
subprocesses with `--no-build`, applying concurrency, startup staggering, and
timeouts. The TUI assembles commands for these runners.

The [runtime server](clawbench/runtime/runtime-server/README.md) owns CDP capture,
interception, the remote CDP bridge, and local screen recording. A managed browser
still uses the ClawBench harness container; provider lifecycle code lives in
[`run_support/browser_runtime/`](clawbench/runner/run_support/browser_runtime/).

## Configuration and Paths

Use [utils/paths.py](clawbench/utils/paths.py) to distinguish three locations:

| Root | Purpose |
| --- | --- |
| `WORKSPACE_ROOT` | Mutable model config, environment overrides, and default single-run outputs. `CLAWBENCH_WORKSPACE` overrides discovery; otherwise the nearest ancestor containing `.env` or `models/models.yaml` wins, with checkout/current-directory fallbacks. Batch output defaults to `test-output` under the invocation directory. |
| `ASSET_ROOT` | Task suites and config templates: the source checkout, or `_bundled/` in an installed package. |
| `RUNTIME_ROOT` | Packaged container assets under `clawbench/runtime/`, independent of the workspace. |

[config.py](clawbench/runner/run_support/config.py) loads environment settings in
increasing precedence: bundled `.env`, workspace `.env`, workspace `.env.local`,
then process environment variables. Editable model definitions live in the
workspace's `models/models.yaml`.

The [harness registry](clawbench/runtime/harnesses/harnesses.yaml) maps each
harness to its image, build/setup/run files, usage emitter, and transcript
sources. Update this registry when adding a harness; its
[loader](clawbench/runner/run_support/harness_registry.py) validates referenced
files and mappings.

## Related Guides

| Working on | Read |
| --- | --- |
| Task definitions and attachments | [Contributing](../CONTRIBUTING.md#adding-a-new-test-case), [task schema](../test-cases/task.schema.json) |
| Runtime capture and browser providers | [Runtime server](clawbench/runtime/runtime-server/README.md), [browser runtimes](../docs/browser-runtimes.md) |
| Output artifacts and evaluation | [Evaluation guide](../eval/README.md), [trace cookbook](../docs/trace-cookbook.md) |
| Dataset and RL integrations | [Harbor](../docs/harbor.md), [EdgeBench](../docs/edgebench.md), [ProRL](../docs/prorl-rl-env.md) |

Host-side tests live in [`tests/`](../tests/). Validation and build workflows live
in [`.github/workflows/`](../.github/workflows/); use the
[contributor checks](../CONTRIBUTING.md#code-changes) before opening a PR.
