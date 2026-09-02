# CLI reference

Every ClawBench command. From a PyPI install run them directly (`clawbench-run …`); from a source checkout prefix with `uv run` (`uv run clawbench-run …`).

| Command | What it does |
| --- | --- |
| `clawbench` | Interactive TUI — guided model and test-case selection. Needs a TTY. |
| `clawbench-run` | One task, one model (or human mode). |
| `clawbench-batch` | A matrix of models × cases. |
| `clawbench-rescore` | Re-judge trajectories you already have, without re-running agents. |
| `clawbench-reproduce` | Download published traces for one leaderboard row and check you reproduce it. |
| `clawbench-harbor-adapt` | Convert V2 into a Harbor dataset — see [`harbor.md`](harbor.md). |
| `clawbench-edgebench-adapt`, `clawbench-edgebench-judge` | EdgeBench/SForge export — see [`edgebench.md`](edgebench.md). |

`./run.sh` from a source checkout is a shortcut for the TUI.

## Task suites

| Suite | Path | Tasks | Selector |
| --- | --- | ---: | --- |
| V1 | [`test-cases/v1/`](../test-cases/v1/) | 152 | *(default)* |
| V2 | [`test-cases/v2/`](../test-cases/v2/) | 129 | `--cases-suite v2` |
| Lite | [`test-cases/v1-lite/`](../test-cases/v1-lite/) | 20 | `--cases-suite v1-lite` |
| Claw-Eval | [`test-cases/claw-eval/`](../test-cases/claw-eval/) | 19 | `--cases-suite claw-eval` |
| Your own | anywhere | — | `--cases-dir <path>` |

All suites validate against [`test-cases/task.schema.json`](../test-cases/task.schema.json).

## `clawbench-run`

```bash
clawbench-run <case-dir> <model>      # agent run
clawbench-run <case-dir> --human      # human reference run
```

| Flag | Default | What it does |
| --- | --- | --- |
| `--human` | off | Expose Chrome via noVNC instead of running an agent |
| `--harness <name>` | `openclaw` | Agent scaffold; see the harness table in the [README](../README.md#quick-start) |
| `--judge <model>` | `deepseek-v4-pro` | Model key in `models/models.yaml` used as the LLM judge |
| `--no-judge` | off | Skip the judge stage — pass = intercepted (stage 1 only) |
| `--output-dir <path>` | `<project>/test-output` | Where run directories are written |
| `--no-build` | off | Skip building the container image (assumes it exists) |
| `--no-upload` | off | Skip HuggingFace upload even if `HF_TOKEN` is configured |
| `--browser-runtime <name>` | `local` | `local`, `kernel`, `browserbase`, `remote-cdp` — see [`browser-runtimes.md`](browser-runtimes.md) |
| `--browser-cdp-url <url>` | — | CDP endpoint for `--browser-runtime remote-cdp` |
| `--browser-runtime-options <json>` | — | Provider-specific options, e.g. `'{"region":"us-west-2"}'` |

Output lands in `./test-output/<model>/<harness>-<case>-<model>-<timestamp>/`.

## `clawbench-batch`

```bash
clawbench-batch --models <model> --cases-suite v2 --all-cases
clawbench-batch --all-models --case-range 1-50 --max-concurrent 3
clawbench-batch --models <model> --cases-dir ./custom-cases --all-cases
```

Selection:

| Flag | What it does |
| --- | --- |
| `--models <pattern> …` | Model name patterns matched against keys in `models/models.yaml` |
| `--all-models` | Every model in `models/models.yaml` |
| `--cases <glob> …` | Glob patterns for case directories |
| `--all-cases` | Every case in the selected suite or `--cases-dir` |
| `--case-range 1-50` | Numeric task-ID range |
| `--cases-suite <name>` / `--cases-dir <path>` | Which corpus to draw from |

Execution:

| Flag | Default | What it does |
| --- | --- | --- |
| `--max-concurrent <n>` | 2 local, 1 Kernel/Browserbase | Parallel jobs |
| `--stagger-delay <s>` | 15 | Minimum seconds between consecutive container starts (rolling start) |
| `--resume <dir>` | — | Reuse a previous batch's output directory and skip finished runs |
| `--dry-run` | off | Print the job matrix without running anything |
| `--output-dir <path>` | `test-output` | Base output directory |

`--harness`, `--judge`, `--no-judge`, `--no-upload`, and the `--browser-*` flags behave as in `clawbench-run`. A `batch-summary.json` is written alongside the per-run directories.

### Exit codes

| Code | Meaning |
| --- | --- |
| 0 | Intercepted, and judged a match (or `--no-judge`) |
| 1 | The run failed: not intercepted, or the judge returned a mismatch |
| 2 | The run itself errored before producing a result |
| 3 | Intercepted, but the judge returned no verdict — a judge outage, not a model failure. `clawbench-batch` counts these as `unjudged`; re-judge them with `clawbench-rescore --only-unjudged` |

## `clawbench-rescore`

Re-judge existing trajectories — no browser, no agent compute.

```bash
clawbench-rescore <run-or-batch-dir> --judge-model deepseek-v4-pro --rubric both
```

| Flag | Default | What it does |
| --- | --- | --- |
| `--judge-model <model>` | `deepseek-v4-pro` | Judge model key in `models/models.yaml` |
| `--rubric <lenient\|strict\|both>` | `lenient` | `lenient` matches the public leaderboard |
| `--workers <n>` | 4 | Parallel judge calls |
| `--force` | off | Re-judge tasks that already have a verdict for this rubric |
| `--limit <n>` | 0 (all) | Judge at most *n* tasks |
| `--only-batch <name>` | — | Restrict to one batch inside a sweep |
| `--only-unjudged` | off | Only re-score runs that intercepted but have no judge verdict — what a judge outage leaves behind |
| `--eval-results-dir <path>` | `./eval_results` | Where per-task CSV + `summary.json` are written |
| `--no-eval-results` | off | Skip writing the `eval_results/` artifact |
| `--models-yaml <path>`, `--sweep-root <path>` | — | Override config / sweep locations |

## `clawbench-reproduce`

Download the published traces for one leaderboard row, re-judge them, and compare.

```bash
clawbench-reproduce --model deepseek-v4-flash --tolerance 2.0
```

| Flag | Default | What it does |
| --- | --- | --- |
| `--model <name>` | required | Published row to reproduce |
| `--judge-model <model>` | `deepseek-v4-pro` | Judge to use |
| `--rubric <lenient\|strict\|both>` | `both` | `both` computes both columns for a full diff |
| `--tolerance <pp>` | 2.0 | Pass if each metric lands within ±tolerance percentage points |
| `--work-dir <path>` | `./reproduce-cache` | Local download directory |
| `--keep-cache` | off | Keep downloaded traces instead of deleting them |

See [Reproduce the leaderboard](../README.md#reproduce-the-leaderboard) for the full workflow and pass criterion.

## Environment variables

| Variable | Used for |
| --- | --- |
| `CONTAINER_ENGINE` | Force `docker` or `podman` |
| `HF_TOKEN` | Optional upload of runs to HuggingFace |
| `BROWSERBASE_API_KEY` | Browserbase runtime (from `.env.local`) |
| `KERNEL_API_KEY` | Kernel runtime (from `.env.local`) |
| `KERNEL_BASE_URL` | Optional Kernel API base URL override |
| `CLAWBENCH_JUDGE_*` | Judge credentials for Harbor's verifier — see [`harbor.md`](harbor.md) |

PurelyMail credentials for disposable run emails come from the committed `.env`.
