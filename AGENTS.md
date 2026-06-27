# ClawBench -- Agent Context

This file is for coding agents (Claude Code, Cursor, Copilot, etc.) to understand and operate on the ClawBench project. If you are a human, see the [README](README.md).

## What This Is

ClawBench is a benchmarking framework for evaluating AI web agents on real-world online tasks. V1 lives in `test-cases/v1/` with 153 tasks spanning 144 live websites and 15 life categories; V2 lives in `test-cases/v2/` with 130 tasks; Lite lives in `test-cases/v1-lite/` with 20 link-backed V1 tasks. Each task runs in an isolated Docker container with  a browser, a recording Chrome extension, and an AI agent harness (`openclaw`, `opencode`, `claude-code`, `claude-code-chrome-extension`, `codex`, `browser-use`, `claw-code`, `hermes`, or `pi`, selectable via `--harness`). The framework captures five layers of data: session replay (MP4), action screenshots, HTTP traffic, browser actions, and agent messages.

## Project Structure

```
ClawBench/
  run.sh                          # Entry point -- launches interactive TUI
  pyproject.toml                  # Root uv package metadata and CLI scripts
  .env                            # Shared PurelyMail credentials packaged with the CLI
  src/
    clawbench/                    # Main Python package
      tui.py                      # Interactive TUI (called by run.sh)
      runner/
        run.py                    # Single test-case runner
        batch.py                  # Batch runner (model x case cross-product)
        run_support/              # Runner-private helpers for single runs
      utils/
        hf_upload.py              # Optional HuggingFace upload helpers
      runtime/
        shared/
          alex_green_personal_info.json
        runtime-server/           # Container-only uv project for server deps
        chrome-extension/         # Recording extension
        harnesses/                # Dockerfiles + setup/run scripts
  models/
    models.yaml                   # Model API configs (gitignored -- copy from example)
    models.example.yaml           # Template with placeholder keys
    model.schema.json             # JSON schema for model entries
  test-cases/
    task.schema.json              # JSON schema for task.json
    v1/                           # V1: 153 task directories
    v2/                           # V2: 130 task directories
    v1-lite/                      # Lite: 20 V1 task directories with linked task files
  eval/
    README.md                     # Evaluation guide + Claude Code prompt template
    agentic_eval.md               # Evaluator rubric for judging agent success
```

## Setup

**Prerequisites:** Python 3.11+, [uv](https://docs.astral.sh/uv/), Docker or Podman.

```bash
# 1. PurelyMail credentials are provided in the committed .env

# 2. Configure at least one model
cp models/models.example.yaml models/models.yaml
# Edit models.yaml: add API key and base URL for your model(s)

# 3. Launch
./run.sh
```

## Common Commands

```bash
# Interactive TUI (recommended):
./run.sh

# Single run:
uv run clawbench-run test-cases/v1/<case-dir> <model-name> --harness openclaw

# Single run with Claude Code harness:
uv run clawbench-run test-cases/v1/<case-dir> <model-name> --harness claude-code

# Batch run V1 (model x case cross-product):
uv run clawbench-batch \
  --models <model-name> --all-cases --max-concurrent 3 --harness openclaw

# Batch run V2:
uv run clawbench-batch \
  --models <model-name> --cases-suite v2 --all-cases --max-concurrent 3 --harness hermes

# Batch run using an explicit case directory:
uv run clawbench-batch \
  --models <model-name> --cases-dir custom-cases --all-cases --harness hermes

# Human mode (manual browser control via noVNC; no harness needed):
uv run clawbench-run test-cases/v1/<case-dir> --human
```

## Model Configuration

Each model entry in `models/models.yaml` requires:
- `base_url` -- API endpoint (e.g. `https://openrouter.ai/api/v1`)
- `api_type` -- one of: `openai-completions`, `openai-responses`, `anthropic-messages`, `google-generative-ai`
- `api_key` -- API key (or `api_keys` for round-robin)

Optional: `thinking_level`, `temperature`, `max_tokens`. See `models/model.schema.json` for the full schema.

## Test Case Format

Each `test-cases/v1/<id>-<metaclass>-<class>-<platform>/task.json` or `test-cases/v2/v2-<id>-<metaclass>-<class>-<platform>/task.json` contains:
- `instruction` -- task prompt for the agent
- `eval_schema` -- request interceptor config (`url_pattern` regex + `method`)
- `time_limit` -- max minutes before watchdog stops the agent
- `extra_info` -- optional additional files to mount into the container

See `test-cases/task.schema.json` for the full schema used by both corpora.

## Output Structure

Each run produces:
```
test-output/<model>/<harness>-<case>-<model>-<timestamp>/
  run-meta.json             # Run metadata (harness, model, duration, intercepted)
  eval-schema.json          # Schema used for this run
  data/
    actions.jsonl           # Browser action log
    requests.jsonl          # HTTP request log
    agent-messages.jsonl    # Agent conversation transcript (shape varies by harness:
                            #   openclaw → session-schema events; opencode → AI-SDK
                            #   `step_start`/`tool_use`/`text`/`reasoning`/`step_finish` events;
                            #   claude-code → stream-json events with `system`/`assistant`/`user`/`result` types;
                            #   codex → full session rollout: timestamped `session_meta`/
                            #   `turn_context`/`event_msg`/`response_item` entries with reasoning,
                            #   function_call, and function_call_output items interleaved;
                            #   browser-use → one `AgentHistory` item per step with `model_output.action`,
                            #   `result`, `state`, `metadata` fields;
                            #   hermes → live `session_meta`/`thinking`/`reasoning`/
                            #   `tool_use`/`tool_result` capture, falling back to
                            #   Hermes session export when it contains messages;
                            #   pi → filtered Pi JSON mode events with
                            #   `message_start`/`message_end`,
                            #   `tool_execution_*`, tool-call content, and
                            #   thinking blocks; streaming `message_update`
                            #   fragments are omitted)
    screenshots/            # Timestamped PNGs
    recording.mp4           # Full session video
    interception.json       # Interception result
```

## Key Documentation

- [README.md#-cli](README.md#-cli) -- CLI usage, batch runner flags, output format
- [src/clawbench/runtime/runtime-server/README.md](src/clawbench/runtime/runtime-server/README.md) -- FastAPI server, endpoints, screen recording
- [CONTRIBUTING.md](CONTRIBUTING.md) -- how to add new test cases
- [eval/README.md](eval/README.md) -- evaluation guide and Claude Code prompt template
- [eval/agentic_eval.md](eval/agentic_eval.md) -- evaluator rubric for PASS/FAIL judgment
