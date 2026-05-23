# ClawBench Source Layout

This directory contains the implementation for ClawBench.

## Entry Points

From the project root:

```bash
# Interactive TUI
./run.sh
# or
uv run clawbench

# Single run
uv run clawbench-run test-cases/v1/886-entertainment-hobbies-experience-topgolf qwen3.5-397b-a17b

# Human reference run
uv run clawbench-run test-cases/v1/886-entertainment-hobbies-experience-topgolf --human

# Batch run
uv run clawbench-batch --all-models --case-range 1-50 --max-concurrent 3
```

The console scripts are defined in the root `pyproject.toml`:

| Script            | Module              | Purpose                        |
| ----------------- | ------------------- | ------------------------------ |
| `clawbench`       | `clawbench.tui:main`          | Interactive terminal UI        |
| `clawbench-run`   | `clawbench.runner.run:main`   | Single test-case runner        |
| `clawbench-batch` | `clawbench.runner.batch:main` | Model x test-case batch runner |

## Directory Map

```text
src/
  clawbench/
    tui.py                       # Interactive menu for configuring and launching runs
    runner/
      run.py                     # Single test-case driver
      batch.py                   # Concurrent batch runner
      run_support/
        resume.py                # Runner-private resume PDF renderer
        resume_template.json     # Synthetic resume source template
    utils/
      paths.py                   # Shared PROJECT_ROOT / HARNESS_ROOT discovery
      hf_upload.py               # Optional HuggingFace upload helpers
  extension-server/
    server.py                    # FastAPI server for actions, screenshots, recording, request interception
    pyproject.toml               # Container-only uv project
    uv.lock
    README.md
  chrome-extension/
    manifest.json
    content.js                   # DOM action capture
    background.js                # Screenshot capture + server relay
    stealth.js                   # Browser fingerprint hardening patches
    setup.sh                     # Local extension launch helper
    README.md
  harnesses/
    harnesses.yaml              # Central harness registry: images, Dockerfiles, scripts
    harness.schema.json         # JSON Schema for harnesses.yaml
    base/
      Dockerfile.base            # Shared Chromium, Xvfb, noVNC, server, extension image
      entrypoint.sh              # Shared container startup logic
    openclaw/
    ...                          # other harnesses
```

## Configuration

### Infrastructure (`.env`)

Infrastructure secrets are read from `.env` at the project root:

```dotenv
PURELY_MAIL_API_KEY=pm-live-...
PURELY_MAIL_DOMAIN=clawbench.example.com

# Optional: upload run outputs to a HuggingFace dataset repo
HF_TOKEN=hf_...
HF_REPO_ID=your-org/your-dataset-name
```

Purely mail is used to generate a disposable email for each run, so each agent will get its own working email for things like account creation or verification.


When `HF_TOKEN` and `HF_REPO_ID` are set,
completed runs are uploaded after local collection unless `--no-upload` is
passed.

### Model Configuration (`models/`)

Model configs live in `models/models.yaml` in the mutable workspace. In a
source checkout this is the project root; in an installed PyPI package this is
the directory where you launch the CLI.

```bash
cp models/models.example.yaml models/models.yaml
$EDITOR models/models.yaml
```

Each top-level YAML key is the model name passed to the runner and into the
container as `MODEL_NAME`:

```yaml
qwen3.5-397b-a17b:
  api_key: "sk-or-v1-..."
  base_url: https://openrouter.ai/api/v1
  api_type: openai-completions
  thinking_level: medium
```

Model entries are validated against `models/model.schema.json`.

| Field            | Required | Description                                                                               |
| ---------------- | -------- | ----------------------------------------------------------------------------------------- |
| `base_url`       | yes      | API base URL, for example `https://api.openai.com/v1`                                     |
| `api_type`       | yes      | `openai-completions`, `openai-responses`, `anthropic-messages`, or `google-generative-ai` |
| `api_key`        | no       | Single API key                                                                            |
| `api_keys`       | no       | Multiple API keys; on supported harnesses the traffic is distributed among them           |
| `thinking_level` | no       | `off`, `low`, `medium`, `high`  or `adaptive` (if model & harness support it)             |
| `temperature`    | no       | Sampling temperature                                                                      |
| `max_tokens`     | no       | Maximum output tokens                                                                     |

## Single-Run Workflow

`clawbench/runner/run.py` is the authoritative single test-case driver. For each run it:

1. Loads bundled `.env`, workspace `.env` overrides, and `models/models.yaml`.
2. Reads the selected `test-cases/<suite>/<case>/task.json`.
3. Builds `clawbench-base` and the selected harness image.
4. Creates a disposable PurelyMail account.
5. Prepares a temporary `/my-info/` mount with personal info, email credentials, resume PDF, and any task `extra_info` files.
6. Writes the task `eval_schema` to the output directory and mounts it read-only as `/eval-schema.json`.
7. Builds the agent instruction from the task prompt, browser-only rules, `/my-info/` file list, and any extra task context.
8. Starts the container with the chosen harness, model config, eval schema, personal info mount, and noVNC port mapping.
9. Waits for the container to exit by interception, watchdog stop, agent exit, human VNC disconnect, or timeout.
10. Copies `/data` from the container to the output directory.
11. Ensures `data/interception.json` exists, creating a stop-reason record if no request was intercepted.
12. Writes `run-meta.json`.
13. Optionally uploads the run to HuggingFace.
14. Removes the container, deletes the disposable email, and removes the temporary personal info directory.

Check `clawbench/runtime/harnesses/harnesses.yaml` for the supported harnesses
and their Dockerfile, setup script, run script, helper-file, and
agent-message source mappings.

Use `--harness <name>` to select one. The default is `openclaw`.

## Batch Runner

`clawbench/runner/batch.py` runs the model x test-case cross-product concurrently. It
builds the chosen image once, then invokes `clawbench-run` for each job with
`--no-build`.

```bash
# All configured models x cases 1-50, 3 concurrent
uv run clawbench-batch --all-models --case-range 1-50 --max-concurrent 3

# Specific model patterns x specific case globs
uv run clawbench-batch \
  --models "qwen*" "claude*" \
  --cases "test-cases/v1/886-*" "test-cases/v1/872-*" \
  --max-concurrent 2

# Preview the job matrix without running
uv run clawbench-batch --all-models --all-cases --dry-run
```

A stagger delay is applied between job starts since during container startup it is taking significantly more resources than during the run, so starting multiple containers at the same time can lead to random pod crashes. The default stagger delay is 15 seconds, which can be adjusted with `--stagger-delay`.

| Flag                      | Description                                               | Default                                          |
| ------------------------- | --------------------------------------------------------- | ------------------------------------------------ |
| `--models PATTERN...`     | Model name patterns matched against `models/models.yaml`  | required, unless `--all-models`                  |
| `--all-models`            | Use all configured models                                 | false                                            |
| `--cases PATTERN...`      | Glob patterns for case directories                        | required, unless `--all-cases` or `--case-range` |
| `--cases-suite NAME`      | Built-in suite: `v1`, `v2`, or `v1-lite`                  | `v1`                                            |
| `--cases-dir PATH`        | Custom case directory                                     | none                                            |
| `--all-cases`             | Use all task directories in the selected suite/dir        | false                                            |
| `--case-range START-END`  | Filter by numeric case ID prefix                          | none                                             |
| `--max-concurrent N`      | Max parallel jobs; a recommended value is 1/3 - 1/2 n CPU | 2                                                |
| `--output-dir PATH`       | Base output directory                                     | `test-output`                                    |
| `--stagger-delay SECONDS` | Minimum gap between consecutive container starts          | 15                                               |
| `--dry-run`               | Print job matrix without running                          | false                                            |
| `--no-upload`             | Skip HuggingFace upload for all runs                      | false                                            |
| `--harness NAME`          | Harness image to use                                      | `openclaw`                                       |

Signal handling:

- First Ctrl+C stops new jobs from starting; running jobs continue so their
  subprocesses can clean up containers and disposable emails.
- Second Ctrl+C force-kills running subprocesses.

## Test Case Format

Each test case is a directory under `test-cases/<suite>/` with a `task.json`
validated by `test-cases/task.schema.json`.

```json
{
  "$schema": "../../task.schema.json",
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

| Field         | Description                                                          |
| ------------- | -------------------------------------------------------------------- |
| `instruction` | Task prompt sent to the agent                                        |
| `eval_schema` | Request interceptor config                                           |
| `time_limit`  | Maximum run time in minutes                                          |
| `extra_info`  | Additional files copied into `/my-info/` and described in the prompt |

`eval_schema` supports:

| Field         | Required | Description                                           |
| ------------- | -------- | ----------------------------------------------------- |
| `url_pattern` | yes      | Regex matched against request URLs with `re.search()` |
| `method`      | yes      | HTTP method to match                                  |
| `body`        | no       | Exact key-value filters for parsed request bodies     |
| `params`      | no       | Exact key-value filters for URL query parameters      |

When URL, method, and any body/params filters all match, the interceptor blocks
the request, records it in `data/interception.json`, and asks the container to
stop. For tasks where no irreversible request needs to be intercepted, use
`__PLACEHOLDER_WILL_NOT_MATCH__`; the session will run until another stop
condition occurs.

## Output

Single-run outputs are written under:

```text
test-output/<model>/<harness>-<case>-<model>-<YYYYMMDD-HHMMSS>/
  run-meta.json
  eval-schema.json
  data/
    actions.jsonl
    requests.jsonl
    agent-messages.jsonl
    screenshots/
    recording.mp4
    interception.json
```

Batch outputs are written under:

```text
test-output/batch-<YYYYMMDD-HHMMSS>/
  batch-logs/
    <case>-<model>.log
  batch-summary.json
  <model>/
    <harness>-<case>-<model>-<YYYYMMDD-HHMMSS>/
```

`agent-messages.jsonl` is harness-specific at this stage.

If the interceptor matched a request, `interception.json` contains
`"intercepted": true` and the blocked request. Otherwise the driver writes
`"intercepted": false`, a `stop_reason`, and a human-readable
`stop_description`.

## Personal Info

Each run mounts `/my-info/` into the container:

| File                            | Source                                 | Dynamic fields                                  |
| ------------------------------- | -------------------------------------- | ----------------------------------------------- |
| `alex_green_personal_info.json` | `src/clawbench/runtime/shared/alex_green_personal_info.json` | `contact.email` becomes the generated email     |
| `email_credentials.json`        | Generated by `clawbench/runner/run.py` | disposable email, password, login URL, provider |
| `alex_green_resume.pdf`         | `src/clawbench/runner/run_support/resume_template.json` | resume header email becomes the generated email |
| extra info files                | `test-cases/<suite>/<case>/extra_info/...` | copied by basename into `/my-info/`             |

The `online_accounts` section is removed from the personal info JSON before it
is mounted, so agents use only the disposable account and task-provided files.

## Disposable Email

The single-run driver creates a disposable email for each run through the
PurelyMail API:

- Username format: `cb<12-hex-chars>`
- Domain: `PURELY_MAIL_DOMAIN` from `.env`
- Password: generated with `secrets.token_urlsafe(16)`
- Cleanup: deleted in the `finally` block even when a run fails

The generated email is written to `/my-info/email_credentials.json`, injected
into the personal info JSON, and injected into the generated resume PDF.

We're providing purely-mail API key and domain in `.env` for ease of setup, the cost is on us, though please use them responsibly. If you want to use your own purely-mail account, sign up at https://purelymail.com/, follow their instructions to setup the domain and create an API key, and set `PURELY_MAIL_API_KEY` and `PURELY_MAIL_DOMAIN` in your `.env`.
