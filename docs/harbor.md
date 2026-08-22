# Running ClawBench through Harbor

[Harbor](https://pypi.org/project/harbor/) is an agent-evaluation framework with its own task format, agent registry, and job runner. ClawBench ships an adapter that converts the V2 corpus into Harbor tasks, so you can evaluate any Harbor-supported agent against ClawBench websites with ClawBench's recorder, interceptor, and judge still in the loop.

**Use Harbor when** you already run other benchmarks through it, you want Harbor's agent registry (`-a openclaw`, `-a hermes`, …) instead of ClawBench's own harnesses, or you need Harbor's retry/attempt semantics. **Use `clawbench-batch` instead** when you just want to score a model on ClawBench — it is the shorter path and it is what the leaderboard uses.

- [Prerequisites](#prerequisites)
- [1. Convert V2 into a Harbor dataset](#1-convert-v2-into-a-harbor-dataset)
- [2. Wire up the judge](#2-wire-up-the-judge)
- [3. Run it](#3-run-it)
- [Making it fast](#making-it-fast)
- [What the generated environment contains](#what-the-generated-environment-contains)
- [Troubleshooting](#troubleshooting)

## Prerequisites

- **Docker.** Harbor runs use Harbor's Docker provider, so Docker must be available even if you normally use Podman for native ClawBench runs.
- **ClawBench installed** (`uv tool install clawbench-eval`, or a source checkout with `uv run` prefixes).
- **Judge credentials.** Scoring requires both an intercepted request *and* a judge verdict; without judge credentials every intercepted task scores `0`.
- **PurelyMail credentials** from `.env`, passed through with `--env-file .env`.

## 1. Convert V2 into a Harbor dataset

```bash
# All V2 tasks.
uv run clawbench-harbor-adapt \
  --output-dir ./harbor-datasets/clawbench-v2 \
  --overwrite

# One-task smoke dataset — do this first, it takes minutes instead of hours.
uv run clawbench-harbor-adapt \
  --output-dir ./harbor-datasets/clawbench-v2-smoke \
  --limit 1 \
  --overwrite
```

| Flag | What it does |
| --- | --- |
| `--output-dir <path>` | Where the Harbor task directories are written (required) |
| `--overwrite` | Replace an existing output directory |
| `--limit <n>` | Convert only the first *n* tasks — use for smoke datasets |
| `--task-ids <id> …` | Convert specific tasks by directory name or numeric `task_id` |
| `--cases-dir <path>` | Convert a corpus other than V2 (defaults to `test-cases/v2/`) |
| `--dataset-name`, `--org` | Metadata written into the generated `task.toml` |

## 2. Wire up the judge

Harbor's verifier applies both ClawBench V2 judge rubrics to every intercepted request. `reward` and `reward_lenient` use the public leaderboard's no-explicit-contradiction rubric; `reward_strict` requires the payload to demonstrate complete fulfillment. The two judge calls run concurrently against the same request and use the model configured below. Export the four variables once, then forward them into each run with `--ve`:

```bash
export CLAWBENCH_JUDGE_BASE_URL="https://your-judge-provider.example/v1"
export CLAWBENCH_JUDGE_API_KEY="your-judge-api-key"
export CLAWBENCH_JUDGE_MODEL="deepseek-v4-pro"
export CLAWBENCH_JUDGE_API_TYPE="openai-completions"
```

Use `deepseek-v4-pro` if you want numbers comparable to the published leaderboard.

## 3. Run it

```bash
uvx --from harbor==0.15.0 harbor run \
  -p ./harbor-datasets/clawbench-v2 \
  -a "<agent>" \
  -m "<model>" \
  --env-file .env \
  --ve CLAWBENCH_JUDGE_BASE_URL="$CLAWBENCH_JUDGE_BASE_URL" \
  --ve CLAWBENCH_JUDGE_API_KEY="$CLAWBENCH_JUDGE_API_KEY" \
  --ve CLAWBENCH_JUDGE_MODEL="${CLAWBENCH_JUDGE_MODEL:-deepseek-v4-pro}" \
  --ve CLAWBENCH_JUDGE_API_TYPE="${CLAWBENCH_JUDGE_API_TYPE:-openai-completions}"
```

Drop `uvx --from harbor==0.15.0` if Harbor is already installed.

### OpenClaw through an OpenAI-compatible endpoint

```bash
export OPENAI_BASE_URL="https://openrouter.ai/api/v1"
export OPENAI_API_KEY="$OPENROUTER_API_KEY"

uvx --from harbor==0.15.0 harbor run \
  -p ./harbor-datasets/clawbench-v2 \
  -a openclaw \
  -m openai/deepseek/deepseek-v4-flash \
  --ak thinking=off \
  --env-file .env \
  --ve CLAWBENCH_JUDGE_BASE_URL="$CLAWBENCH_JUDGE_BASE_URL" \
  --ve CLAWBENCH_JUDGE_API_KEY="$CLAWBENCH_JUDGE_API_KEY" \
  --ve CLAWBENCH_JUDGE_MODEL="${CLAWBENCH_JUDGE_MODEL:-deepseek-v4-pro}" \
  --ve CLAWBENCH_JUDGE_API_TYPE="${CLAWBENCH_JUDGE_API_TYPE:-openai-completions}" \
  --jobs-dir ./harbor-jobs/openclaw-deepseek-flash
```

### Hermes through OpenRouter

```bash
export OPENROUTER_API_KEY="your-openrouter-key"

uvx --from harbor==0.15.0 harbor run \
  -p ./harbor-datasets/clawbench-v2 \
  -a hermes \
  -m deepseek/deepseek-v4-flash \
  --env-file .env \
  --ve CLAWBENCH_JUDGE_BASE_URL="$CLAWBENCH_JUDGE_BASE_URL" \
  --ve CLAWBENCH_JUDGE_API_KEY="$CLAWBENCH_JUDGE_API_KEY" \
  --ve CLAWBENCH_JUDGE_MODEL="${CLAWBENCH_JUDGE_MODEL:-deepseek-v4-pro}" \
  --ve CLAWBENCH_JUDGE_API_TYPE="${CLAWBENCH_JUDGE_API_TYPE:-openai-completions}" \
  --jobs-dir ./harbor-jobs/hermes-deepseek-flash
```

## Kernel browser runtime (control arm)

By default each Harbor trial runs Chromium inside its own container. Pass `--browser-runtime kernel` to the adapter to run the same tasks against one Kernel cloud browser per task instead:

```bash
uv run clawbench-harbor-adapt \
  --output-dir ./harbor-datasets/clawbench-v2-kernel \
  --browser-runtime kernel \
  --browser-runtime-options '{"stealth": false}' \
  --task-ids v2-1134-chapter-finder-redcross \
  --overwrite
```

During task setup, the environment creates exactly one Kernel browser and replay, starts the ClawBench runtime server against it, and exposes only the local credential-free CDP bridge (`http://127.0.0.1:7878`) to the agent — the Kernel API key is never visible to the benchmark agent. Session identity and cleanup metadata land in `/my-info/kernel_browser.json`. During verification the provider replay is finalized, `recording.mp4` is downloaded into `/data`, and the browser is deleted (idempotently, including failure paths via a setup trap).

Generated tasks register a pinned Playwright MCP package (`@playwright/mcp@0.0.79`) pointed at the CDP bridge, so Harbor's stock Claude Code and Codex agents drive the Kernel browser with native Playwright MCP tool calls — structurally identical to ClawBench's native Claude/Codex harnesses.

Export `KERNEL_API_KEY` (and optionally `KERNEL_BASE_URL` for non-production gateways) before `harbor run`; no extra flags are needed.

## Making it fast

A full V2 sweep is 129 containerized browser sessions, each capped by the task's `time_limit`. Serial, that is a very long night. What actually moves the needle, in order:

**1. Raise concurrency.** `-n / --n-concurrent` is the single biggest lever:

```bash
uvx --from harbor==0.15.0 harbor run -p ./harbor-datasets/clawbench-v2 \
  -a hermes -m deepseek/deepseek-v4-flash -n 8 --env-file .env --ve ...
```

Each trial is a full Chromium container, so budget roughly **1 CPU core and ~2 GB RAM per concurrent trial** and keep `-n` under your provider's rate limit. On a 16-core box, `-n 8` is a sane starting point; going wider usually trades wall-clock for flaky, timing-sensitive failures on live sites.

**2. Build the image once.** The first trial builds the ClawBench environment image; parallel cold starts all build at once. Warm the cache with the smoke dataset before the real sweep:

```bash
uvx --from harbor==0.15.0 harbor run -p ./harbor-datasets/clawbench-v2-smoke \
  -a hermes -m deepseek/deepseek-v4-flash --env-file .env --ve ...
```

**3. Don't pay for attempts you don't need.** `-k / --n-attempts` multiplies the whole sweep — leave it at 1 unless you are measuring variance. `-r / --max-retries` only re-runs infrastructure errors; keep it low (1–2) so a dead site doesn't burn the budget.

**4. Trim timeouts deliberately.** `--timeout-multiplier` (and the per-phase `--agent-timeout-multiplier`, `--verifier-timeout-multiplier`, `--agent-setup-timeout-multiplier`, `--environment-build-timeout-multiplier`) scale ClawBench's per-task limits. Shrinking them makes a sweep finish sooner but converts slow successes into timeouts — only do it when you are debugging plumbing, never for a leaderboard number.

**5. Shard instead of scaling one box.** For a big sweep, convert subsets with `--task-ids` and run them on separate machines with separate `--jobs-dir` paths, then merge results.

**6. Skip the interactive prompt in CI** with `-y / --yes`, and quiet per-trial output with `-q`.

## What the generated environment contains

Each converted task directory carries its own `environment/` (Chromium, the ClawBench recorder/interceptor, noVNC, runtime helper scripts), a `run/` step with `instruction.md`, the original `task.json`, the `eval-schema.json`, and a verifier under `tests/`. It deliberately contains **no ClawBench-native harness** — Harbor installs and runs whatever agent you pass to `-a` inside the task container.

Scoring uses the same two-stage rule as the native runner: the interceptor must catch a request matching the task schema, then the verifier emits both the public lenient reward and the conservative strict reward. Harbor uses the lenient result as the primary `reward` metric and retains both verdicts and reasons in `clawbench-result.json`.

## Troubleshooting

| Symptom | Cause | Fix |
| --- | --- | --- |
| Every intercepted task scores `0` with `missing judge configuration` | Judge base URL or API key not reaching the verifier | Pass all four `--ve CLAWBENCH_JUDGE_*` values on the `harbor run` command |
| `Cannot connect to the Docker daemon` | Harbor's provider is Docker-only | Start Docker Desktop / `dockerd`; Podman is not a substitute here |
| Sign-in tasks fail immediately | PurelyMail credentials missing | Add `--env-file .env` |
| Many trials die at once under high `-n` | Host CPU/RAM exhaustion, or provider rate limits | Lower `-n`; see [Making it fast](#making-it-fast) |
| Reward differs from the leaderboard | Different judge model or rubric | Use `deepseek-v4-pro`; see [Reproduce the leaderboard](../README.md#reproduce-the-leaderboard) |

Related: [`docs/cli.md`](cli.md) · [`docs/browser-runtimes.md`](browser-runtimes.md) · [`eval/scoring.md`](../eval/scoring.md)
