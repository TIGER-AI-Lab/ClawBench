# ClawBench Test Driver

The test driver orchestrates single test-case runs against the ClawBench framework. For each run, it creates a disposable email, launches an isolated container (Docker or Podman) with an AI agent, enforces a time limit, collects results, and cleans up all resources.

## Quick Start

```bash
# 1. Configure .env with PurelyMail credentials (see Configuration below)
# 2. Launch the interactive menu:
./run.sh
# Or equivalently:
uv run --project test-driver test-driver/tui.py
```

The interactive menu lets you configure models, select test cases, and choose a run mode interactively.

For direct CLI usage:

```bash
uv run --project test-driver test-driver/run.py test-cases/886-entertainment-hobbies-experience-topgolf qwen3.5-397b-a17b
```

## Configuration

### Infrastructure (`.env`)

Infrastructure secrets are read from `.env` at the project root (gitignored):

```
PURELY_MAIL_API_KEY=pm-live-...
PURELY_MAIL_DOMAIN=clawbench.example.com

# Optional: auto-upload results to HuggingFace after each run
HF_TOKEN=hf_...
HF_REPO_ID=your-org/your-dataset-name
```

See `.env.example` for the template.

When `HF_TOKEN` and `HF_REPO_ID` are set, each run's output is automatically uploaded to the HuggingFace dataset repo after completion. The local `data/` directory is then replaced with an `uploaded.json` marker containing the repo path and commit URL. Use `--no-upload` to skip this even when credentials are configured.

### Model Configuration (`models/`)

All models are defined in a single `models/models.yaml` file (gitignored — contains API keys).

Add models interactively via the TUI, or manually copy and edit the example:

```bash
# Interactive:
uv run --project test-driver test-driver/tui.py   # select "Configure models"

# Manual:
cp models/models.example.yaml models/models.yaml
# Edit models/models.yaml and fill in your API keys
```

```
models/
  model.schema.json       # JSON schema for a single model entry
  models.example.yaml     # Example config (committed, placeholder keys)
  models.yaml             # Your config (gitignored, real keys)
```

Each top-level key is the model name (passed as `MODEL_NAME` to the container):

```yaml
qwen3.5-397b-a17b:
  api_key: "sk-or-v1-..."
  base_url: https://openrouter.ai/api/v1
  api_type: openai-completions
  thinking_level: medium
```

#### Model entry fields

Validated by `models/model.schema.json`:

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `base_url` | string | yes | API base URL (e.g. `https://api.openai.com/v1`) |
| `api_type` | string | yes | API type (`openai-completions`, `openai-responses`, `anthropic-messages`, `google-generative-ai`) |
| `api_key` | string | no | API key |
| `api_keys` | list | no | Multiple API keys for round-robin rotation (takes precedence over `api_key`) |
| `thinking_level` | string | no | `off`/`minimal`/`low`/`medium`/`high`/`xhigh`/`adaptive` |
| `temperature` | number | no | Sampling temperature (0–2) |
| `max_tokens` | integer | no | Maximum output tokens |

## Interactive TUI

`tui.py` provides an interactive menu for users unfamiliar with the CLI:

```bash
uv run --project test-driver test-driver/tui.py
```

Options:
1. **Single run** — pick one model and one test case
2. **Batch run** — pick models and cases, set concurrency
3. **Human mode** — pick a test case, launch noVNC
4. **Configure models** — add models to `models/models.yaml` interactively

Test cases can be selected by their numeric ID prefix (e.g. `886` for `886-entertainment-hobbies-experience-topgolf`).

## Workflow

1. **Load config** — reads `.env` for PurelyMail credentials, loads model config from `models/models.yaml`
2. **Load test case** — reads `task.json` from the specified test case directory
3. **Build container image** — runs `docker build` (or `podman build`) to build the `clawbench` image; skipped with `--no-build`
4. **Create disposable email** — calls PurelyMail API to create `cb<uuid>@<domain>` with a generated password
5. **Prepare personal info** — copies `shared/alex_green_personal_info.json`, injects the generated email into the contact field, writes `email_credentials.json`, generates `alex_green_resume.pdf` from `resume_template.json` (also with the generated email), and copies any `extra_info` files from the test case. All files are placed in a temporary directory mounted into the container at `/my-info/`
6. **Write eval schema** — writes the eval schema from `task.json` to `eval-schema.json` in the output directory, then mounts it read-only into the container
7. **Build instruction** — assembles the agent prompt from the task instruction, browser-only enforcement, an explicit listing of the core `/my-info/` files (personal info, email credentials, resume), and any extra info files
8. **Start container** — launches the `clawbench` container image with the instruction, eval schema, personal info mount, and model config
9. **Wait** — blocks until the container exits (the container enforces its own time limit via `TIME_LIMIT_S`)
10. **Collect results** — copies `/data` (actions, HTTP requests, screenshots, recording, interception) from the container
11. **Ensure interception** — if the interceptor didn't produce `interception.json`, generates one with the stop reason from the container (`time_limit_exceeded`, `agent_idle`, or `agent_exited`)
12. **Write metadata** — saves `run-meta.json` with model, timestamp, duration, and interception status
13. **Upload** (optional) — if `HF_TOKEN` and `HF_REPO_ID` are configured, uploads the output directory to HuggingFace and replaces the local `data/` with an `uploaded.json` marker
14. **Cleanup** — removes the container, deletes the disposable email, and removes the temporary personal info directory (guaranteed via `try/finally`)

## Test Case Naming Convention

Test case directories are prefixed by their numeric `task_id` from `task.json`:

```
test-cases/
  001-daily-life-food-uber-eats/
  002-daily-life-food-doordash/
  ...
  886-entertainment-hobbies-experience-topgolf/
```

This enables range-based selection with `--case-range` in the batch runner (e.g., `--case-range 1-50` selects all cases with IDs 1 through 50).

## Batch Runner

`batch.py` runs the model x test-case cross-product concurrently. It builds the container image once upfront, then invokes `run.py` as a subprocess for each job (with `--no-build` to skip redundant rebuilds), with an asyncio semaphore controlling max parallelism.

### Usage

```bash
# All models x cases 1-50, 3 concurrent
uv run --project test-driver test-driver/batch.py --all-models --case-range 1-50 --max-concurrent 3

# Specific models by name pattern x specific cases
uv run --project test-driver test-driver/batch.py \
  --models "qwen*" "claude*" \
  --cases "test-cases/886-*" "test-cases/872-*" \
  --max-concurrent 2

# Preview the job matrix without running
uv run --project test-driver test-driver/batch.py --all-models --all-cases --dry-run
```

### Flags

| Flag | Description | Default |
|------|-------------|---------|
| `--models PATTERN...` | Model name patterns (matched against keys in `models/models.yaml`) | (required, or `--all-models`) |
| `--all-models` | Use all models in `models/models.yaml` | false |
| `--cases PATTERN...` | Glob patterns for case dirs | (required, or `--all-cases` or `--case-range`) |
| `--all-cases` | Use all `test-cases/*/task.json` dirs | false |
| `--case-range START-END` | Filter by numeric ID prefix (e.g. `1-50`) | none |
| `--max-concurrent N` | Max parallel jobs | 2 |
| `--output-dir PATH` | Base output directory | `test-output` |
| `--stagger-delay SECONDS` | Minimum gap between consecutive container starts (rolling start) | 15 |
| `--dry-run` | Print job matrix without running | false |
| `--no-upload` | Skip HuggingFace upload for all runs | false |

`--case-range` can be used standalone (discovers all cases, then filters) or combined with `--cases` (filter the glob results).

### Output

Each batch creates a timestamped subdirectory under the output dir:

```
test-output/batch-20260324-143207/
  batch-logs/
    001-daily-life-food-uber-eats-gpt-5.4-pro-2026-03-05.log
  batch-summary.json
  gpt-5.4-pro-2026-03-05/
    001-daily-life-food-uber-eats-gpt-5.4-pro-2026-03-05-20260324-143210/
```

- `batch-logs/<case>-<model>.log` — captured stdout/stderr from each subprocess
- `batch-summary.json` — aggregate results with per-job status and timing

All log lines include UTC timestamps (e.g. `[14:32:07] [START] ...`).

When HuggingFace credentials are configured, `batch-summary.json` is also uploaded after the batch completes.

### Signal Handling

- First Ctrl+C: stops spawning new jobs (pending jobs are skipped), running jobs continue to completion so their `run.py` subprocesses can clean up containers and emails via `try/finally`
- Second Ctrl+C: force-kills all running subprocesses

## Test Case Format

Each test case is a subdirectory under `test-cases/` at the project root. The directory must contain a `task.json` (validated by `test-cases/task.schema.json`):

```json
{
  "$schema": "../task.schema.json",
  "instruction": "Task prompt for the agent",
  "eval_schema": {
    "url_pattern": "example\\.com/api/submit",
    "method": "POST"
  },
  "time_limit": 5,
  "extra_info": [
    {
      "path": "extra_info/profile.json",
      "description": "Description injected into the agent prompt"
    }
  ]
}
```

### Fields

| Field | Type | Description |
|-------|------|-------------|
| `instruction` | string | Task prompt sent to the agent |
| `eval_schema` | object | Interceptor config: `url_pattern` (regex) + `method` (HTTP method) — blocks matching requests |
| `time_limit` | number | Maximum time in minutes before the in-container watchdog stops the agent |
| `extra_info` | array | Additional context injected into the agent prompt |

### eval_schema

The `eval_schema` tells the request interceptor which HTTP requests to block:

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `url_pattern` | string | yes | Regex pattern matched against the request URL via `re.search()` |
| `method` | string | yes | HTTP method to match (`GET`, `POST`, `PUT`, `PATCH`, `DELETE`) |
| `body` | object | no | Key-value pairs that must match exactly in the request body |
| `params` | object | no | Key-value pairs that must match exactly in the URL query parameters |

When URL pattern, method, and any body/params filters all match, the interceptor blocks the request, records the details in `interception.json`, and stops the session. The optional `body`/`params` filters are for disambiguation when the same endpoint serves multiple actions (e.g., `{"_action": "send"}` to distinguish from login on the same URL).

For tasks behind payment walls or other natural blockers (e.g., the agent has no valid credit card), use the placeholder pattern `__PLACEHOLDER_WILL_NOT_MATCH__` — the interceptor will never fire and the session runs until timeout.

### Extra Info

Each entry in `extra_info` has:
- `path` (required) — relative path to a file in the test case directory; the file is copied into `/my-info/` inside the container
- `description` (required) — text shown in the prompt as `<filename>: <description>` so the agent knows what the file is for

## Output

Results are saved to `test-output/<model>/<case>-<model>-<YYYYMMDD-HHMMSS>/` at the project root:

```
test-output/qwen3.5-397b-a17b/886-entertainment-hobbies-experience-topgolf-qwen3.5-397b-a17b-20260406-215109/
  eval-schema.json          # Schema used for this run
  run-meta.json             # Run metadata (model, duration, intercepted)
  data/
    actions.jsonl           # Browser action log
    requests.jsonl          # HTTP request log (all browser requests)
    agent-messages.jsonl    # Agent conversation transcript
    screenshots/            # Timestamped PNGs
    recording.mp4           # Full session video
    interception.json       # Interception result
```

### interception.json

When the interceptor blocks a matching request:
```json
{
  "intercepted": true,
  "request": {
    "url": "https://inbox.purelymail.com/action",
    "method": "POST",
    "params": {},
    "body": { "_action": "send", "_to": "recipient@example.com" }
  }
}
```

When the agent doesn't trigger the interceptor (generated by the driver):
```json
{
  "intercepted": false,
  "stop_reason": "agent_idle",
  "stop_description": "Session stopped: agent went idle (300s no actions) before triggering the interceptor.",
  "request": null
}
```

### run-meta.json

```json
{
  "test_case": "886-entertainment-hobbies-experience-topgolf",
  "model": "qwen3.5-397b-a17b",
  "thinking_level": "medium",
  "temperature": null,
  "max_tokens": null,
  "email_used": "cb92784dc43fb0@clawbench.example.com",
  "timestamp": "20260320-040604",
  "time_limit_minutes": 5,
  "duration_seconds": 187,
  "intercepted": true
}
```

## Personal Info

Each run prepares a `/my-info/` directory mounted into the container with:

| File | Source | Dynamic fields |
|------|--------|----------------|
| `alex_green_personal_info.json` | `shared/alex_green_personal_info.json` | `contact.email` → generated email |
| `email_credentials.json` | Generated | `email`, `password`, `login_url`, `provider` |
| `alex_green_resume.pdf` | `test-driver/resume_template.json` | `header.email` → generated email |

The agent instruction tells the model to read `/my-info/` for any information it needs. The `online_accounts` section is stripped from the personal info to prevent agents from using pre-existing account credentials.

### Resume PDF

The resume is generated from `resume_template.json` using `generate_resume_pdf.py` (requires `fpdf2`). To preview:

```bash
cd test-driver && uv run generate_resume_pdf.py [output.pdf]
```

## Disposable Email

The driver creates a disposable email for each run via the [PurelyMail API](https://news.purelymail.com/api/index.html#/User):

- **Username format:** `cb<12-hex-chars>` (e.g., `cb92784dc43fb0`)
- **Domain:** configured via `PURELY_MAIL_DOMAIN` in `.env`
- **Password:** `secrets.token_urlsafe(16)` (22 characters)
- **Cleanup:** deleted after the run, even if the test fails

The email and password are placed in `/my-info/email_credentials.json` inside the container, and the email is also injected into the personal info JSON and resume PDF. The agent instruction directs the model to read `/my-info/` for credentials.
