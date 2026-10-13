# Frequently asked questions

[← ClawBench](../README.md) · [中文](faq.zh-CN.md)

## <img src="../assets/icons/circle-question.svg" width="20" height="20"> FAQ

### What it is

<details>
<summary><b>What is ClawBench?</b></summary>

An open-source benchmark for AI browser agents — the systems (GPT-based, Claude-based, or open) that drive a real web browser to complete a user's task. V1 measures whether the agent actually finishes 152 everyday online tasks across 143 live websites; V2 adds a 129-task corpus in `test-cases/v2/`. It measures completion, not whether the agent produces the right-looking text.

</details>

<details>
<summary><b>What kinds of tasks does it cover?</b></summary>

Fifteen life categories: food delivery, travel booking, job applications, shopping, housing search, email and calendar management, academic research, software development, learning platforms, and more. Every task is something a normal person might do in a normal week, on a real website.

</details>

<details>
<summary><b>Are ~150 tasks enough for evaluation?</b></summary>

Yes for a V1 benchmark signal: the tasks span 143 live websites and 15 life categories, and each full run is expensive because it uses isolated containers, real websites, five-layer recording, and post-session judgment against human references. V2 adds another 129 tasks. For cheaper iteration, start with the 20-task [`test-cases/v1-lite/`](../test-cases/v1-lite) subset.

</details>

<details>
<summary><b>What's the current top score?</b></summary>

The [live leaderboard](https://huggingface.co/spaces/TIGER-Lab/ClawBench) reports scores by corpus, harness, and scoring rubric. The 33.3% result belongs to the historical V1 paper evaluation; it is not a current overall maximum. Compare results using the same corpus revision, metric, and denominator.

</details>

<details>
<summary><b>How does ClawBench relate to HarnessBench?</b></summary>

ClawBench evaluates model/harness configurations on everyday web tasks. HarnessBench focuses on comparing harnesses with a fixed base model. When comparing scores, report the model, harness, corpus revision, judge, and scoring rubric.

</details>

### Running it

<details>
<summary><b>What data does each run produce?</b></summary>

Each session records five layers of synchronized data under `/data/`:

| Layer              | File                   | Description                                                     |
| ------------------ | ---------------------- | --------------------------------------------------------------- |
| Session replay     | `recording.mp4` or `run-meta.json` recording URL | Local/Kernel H.264 video or Browserbase Session Inspector replay |
| Action screenshots | `screenshots/*.png`    | Throttled timestamped PNGs captured after browser actions       |
| Browser actions    | `actions.jsonl`        | Every DOM event (click, keydown, input, pageLoad, scroll, etc.) |
| HTTP traffic       | `requests.jsonl`       | Every HTTP request with headers, body, and query params         |
| Agent messages     | `agent-messages.jsonl` | Full agent conversation transcript (thinking, text, tool calls) |

For the Pi harness, `agent-messages.jsonl` is filtered Pi JSON mode output, including `message_start`/`message_end` events, `tool_execution_*` events, tool-call content blocks, and `thinking` blocks when the selected model emits reasoning. Streaming `message_update` fragments, including `*_delta` rows, are omitted because complete assistant messages are already preserved in `message_end` events.

Harness diagnostic logs such as Pi's `agent.log` and `proxy.log` are not copied into the final `data/` directory. The interceptor result is saved to `interception.json`.

</details>

<details>
<summary><b>What is the synthetic user profile?</b></summary>

Each container gets a `/my-info/` directory with a dummy user identity (Alex Green): personal info JSON, email credentials, and a resume PDF. The email is a fresh disposable PurelyMail address generated per run. The agent reads these files when it needs to fill forms, register accounts, etc.

Source templates: `src/clawbench/runtime/shared/alex_green_personal_info.json` (profile) and `src/clawbench/runner/run_support/resume_template.json` (resume).

</details>

<details>
<summary><b>How do account login, registration, and initial task state work?</b></summary>

Each run receives that synthetic profile plus a fresh disposable address. If a task requires sign-up, the agent normally starts from scratch and registers during the run. If a task needs starting files or workspace context, those live under the task's `extra_info/` directory and are mounted for the agent at runtime.

</details>

<details>
<summary><b>What tools can the agent use?</b></summary>

All supported harnesses run inside the same container recording and interception environment. CLI/MCP harnesses expose the browser tool plus a restricted set of read-only shell commands (`ls`, `cat`, `find`, `grep`, `head`, `tail`, `jq`, `wc`, etc.); commands that could bypass the browser (`curl`, `python`, `node`, `wget`) are blocked. Hermes and Pi use native browser/file tools attached to the same ClawBench Chrome CDP endpoint. The Pi harness intentionally allowlists only read-only file tools and browser interaction tools; `bash`, `write`, `edit`, `browser_http_get`, and `browser_run_script` are not enabled. The agent instruction also explicitly requires browser-only task completion.

</details>

<details>
<summary><b>Can I use Podman instead of Docker?</b></summary>

Yes. Set `export CONTAINER_ENGINE=podman`. The framework auto-detects whichever is available. Podman works without root privileges. (Harbor runs are the exception — they use Harbor's Docker provider.)

</details>

<details>
<summary><b>Is ClawBench tightly coupled to OpenClaw? Can it evaluate CLI agents?</b></summary>

No, and yes. OpenClaw is the default harness, but harnesses are interchangeable — see the table in [Quick start](getting-started.md) and the registry at `src/clawbench/runtime/harnesses/harnesses.yaml`. CLI and coding-agent harnesses drive the same instrumented Chromium session using native tools or MCPs.

</details>

### Scoring and safety

<details>
<summary><b>How is a task judged successful?</b></summary>

Each task runs in an isolated browser container with a five-layer recording. For the original V1 results, an evaluator compares the agent trajectory against human reference runs and assigns PASS/FAIL with evidence from the recording. For V2 and newer leaderboard rows, scoring is two-stage: first, the request interceptor checks whether the final blocked HTTP request matches the task's URL/method schema; second, an LLM judge checks whether the captured request payload fulfills the natural-language instruction.

</details>

<details>
<summary><b>How does the request interceptor work — and is this safe to run against live websites?</b></summary>

The interceptor blocks critical, irreversible HTTP requests (checkout, form submit, email send) to prevent real-world side effects. It connects to Chrome via CDP's `Fetch` domain and matches requests against the eval schema (`url_pattern` regex + `method` + optional `body`/`params`). When triggered, it saves the blocked request to `interception.json`, kills the agent, and stops recording. Tasks that need to *simulate* an irreversible action (e.g. "add to cart and checkout") terminate at the last reversible step; you can relax the interceptor per-task if your research requires it.

The interceptor does **not** validate task completion — that is handled separately post-session. For tasks behind payment walls (the agent has no valid credit card), the eval schema uses a placeholder pattern that never matches, so the session runs until timeout.

</details>

<details>
<summary><b>Which harness are the published model results based on?</b></summary>

The repo default is `openclaw`, but leaderboard rows include their harness explicitly. V1 results used OpenClaw; newer runs may use Hermes or other supported harnesses. Use the `harness` column when comparing models, because model and harness changes are separate experimental axes.

</details>

<details>
<summary><b>What happens when live websites change?</b></summary>

Live-site change is part of the benchmark's target: ClawBench measures whether agents can handle production websites rather than frozen snapshots. That also means some runs can be affected by layout changes, availability, anti-bot systems, or alternate flows. Reproducibility comes from publishing task definitions, eval schemas, run metadata, and five-layer traces; repeated runs over time are still useful for measuring site drift.

</details>

<details>
<summary><b>Do CAPTCHA or bot checks dominate failures?</b></summary>

If an agent encounters a CAPTCHA, it must attempt it. We have seen cases where frontier models are able to solve some CAPTCHAs. CAPTCHA failures can reflect model behavior, browser-control stack limits, or site defenses. The trace datasets make these failures inspectable.

</details>

### Contributing and coverage

<details>
<summary><b>How do I add a new test case?</b></summary>

See [CONTRIBUTING.md](../CONTRIBUTING.md). In short: create a directory under the target corpus (`test-cases/v1/` or `test-cases/v2/`) with a `task.json` conforming to `test-cases/task.schema.json`, define the eval schema, test with human mode, and submit a PR. Harness definitions live in `src/clawbench/runtime/harnesses/harnesses.yaml`.

</details>

<details>
<summary><b>How do I reproduce a published score?</b></summary>

See [Reproduce the leaderboard](reproduce.md) for the two verification paths and the pass criterion.

</details>

<details>
<summary><b>Will newer models be added?</b></summary>

Yes. New model runs can be submitted or requested through the contribution flow and issues. Public rows are added as complete or clearly marked partial runs, depending on what has finished.

</details>
