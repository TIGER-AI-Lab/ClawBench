# ClawBench

[![License: Apache 2.0](https://img.shields.io/badge/License-Apache_2.0-blue.svg)](LICENSE)
[![Python 3.11+](https://img.shields.io/badge/python-3.11%2B-blue.svg)](https://python.org)
[![Docker](https://img.shields.io/badge/docker-supported-blue.svg)](https://www.docker.com/)

ClawBench is a benchmarking framework for evaluating web agents in real browser environments. It records user/agent interactions, HTTP requests, action screenshots, and full MP4 video recordings of each session.

Each test case runs in an isolated container (Docker or Podman) with a Chrome browser, a custom recording extension, and an AI agent. The framework captures everything the agent does and uses a request interceptor to detect task completion.

## Table of Contents

- [Dependencies](#dependencies)
- [Quick Start](#quick-start)
- [Architecture](#architecture)
- [Data Output](#data-output)
- [Building the Container](#building-the-container)
- [API Endpoints](#api-endpoints)
- [OpenClaw Agent Integration](#openclaw-agent-integration)
- [Synthetic User Profile](#synthetic-user-profile)
- [Tool Restrictions](#tool-restrictions)
- [Request Interceptor](#request-interceptor)
- [Test Driver](#test-driver)
- [Human Mode](#human-mode)
- [License](#license)
- [Acknowledgments](#acknowledgments)

## Dependencies

- [Python](https://www.python.org/) 3.11+
- [uv](https://docs.astral.sh/uv/) (Python package manager — installs all Python deps automatically)
- [Docker](https://www.docker.com/) or [Podman](https://podman.io/) (container runtime)

Python dependencies (`fpdf2`, `huggingface_hub`, `pyyaml`) are managed by `uv` and installed automatically on first run.

## Quick Start

```bash
# 1. Set up PurelyMail credentials:
cp .env.example .env
# Edit .env and fill in PURELY_MAIL_API_KEY and PURELY_MAIL_DOMAIN

# 2. Launch the interactive menu:
./run.sh
```

The menu will guide you through configuring models, selecting test cases, and running benchmarks.

## Architecture

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

## Data Output

All data is stored under `/data` in the container:

```
/data/
  actions.jsonl          # One JSON object per line, every DOM event
  requests.jsonl         # One JSON object per line, every HTTP request
  agent-messages.jsonl   # OpenClaw conversation transcript (thinking, text, tool calls)
  screenshots/           # Timestamped PNGs, one per action
    1710000001234.png
    1710000002345.png
  recording.mp4          # Full session video (H.264, 15fps)
  interception.json      # Details of any blocked requests by the interceptor (if applicable)
```

### Action Format (JSONL)

Each line is a JSON object:

```json
{"type": "click", "timestamp": 1710000001234, "url": "https://example.com/", "target": {"tagName": "A", "id": "", "className": "btn", "textContent": "Submit", "xpath": "/html[1]/body[1]/div[1]/a[1]"}, "x": 255, "y": 245}
{"type": "keydown", "timestamp": 1710000002345, "url": "https://example.com/", "target": {...}, "key": "Enter"}
{"type": "input", "timestamp": 1710000003456, "url": "https://example.com/", "target": {...}, "value": "search query"}
{"type": "pageLoad", "timestamp": 1710000004567, "url": "https://example.com/results", "title": "Results"}
```

Captured event types: `pageLoad`, `click`, `keydown`, `keyup`, `input`, `scroll`, `change`, `submit`.

### Agent Messages Format (JSONL)

`agent-messages.jsonl` contains the full OpenClaw conversation transcript. Each line is a JSON object:

- **`type: "session"`** — session metadata (version, id, timestamp)
- **`type: "message"`** — conversation turn, with `message.role` and `message.content[]`:

| `message.role` | Content types                     | Description                        |
| -------------- | --------------------------------- | ---------------------------------- |
| `user`         | `text`                            | The instruction prompt              |
| `assistant`    | `text`, `thinking`, `toolCall`    | Model response, reasoning, actions |
| `toolResult`   | `text`                            | Tool execution results              |

### HTTP Requests Format (JSONL)

`requests.jsonl` logs every HTTP request made by the browser during the session (excluding internal extension/server traffic). Each line:

```json
{"timestamp": 1710000001.234, "url": "https://example.com/api?q=test", "method": "POST", "headers": {"Content-Type": "application/json"}, "body": {"action": "send"}, "query_params": {"q": "test"}, "resource_type": "XHR"}
```

| Field           | Description                                                        |
| --------------- | ------------------------------------------------------------------ |
| `timestamp`     | Unix epoch (float)                                                 |
| `url`           | Full request URL                                                   |
| `method`        | HTTP method (GET, POST, etc.)                                      |
| `headers`       | Request headers (object)                                           |
| `body`          | Parsed request body (JSON object, form dict, raw string, or null)  |
| `query_params`  | Parsed URL query parameters (object)                               |
| `resource_type` | Resource type: Document, Script, Stylesheet, XHR, Fetch, Image, Font, etc. |

Requests to `localhost:7878` (extension server) and `chrome-extension://` URLs are filtered out.

## Building the Container

### Container engine

The framework supports both Docker and Podman (which works without root privileges). Set the `CONTAINER_ENGINE` environment variable to force one:

```bash
export CONTAINER_ENGINE=podman  # or docker
```

If unset, it auto-detects the one available on the system.

### Build

```bash
# Using docker:
docker build -t clawbench .

# Using podman (rootless, no sudo required):
podman build -t clawbench .
```

### Ports

| Port | Service         | Purpose                                    |
| ---- | --------------- | ------------------------------------------ |
| 7878 | FastAPI server  | Action/screenshot API, session control     |
| 9223 | CDP (via socat) | Playwright/DevTools connection to Chromium |

## API Endpoints

| Method | Path              | Description                                  |
| ------ | ----------------- | -------------------------------------------- |
| GET    | `/api/status`     | Health check                                 |
| POST   | `/api/action`     | Record a browser action (JSON body)          |
| POST   | `/api/screenshot` | Store a screenshot (base64 PNG in JSON)      |
| POST   | `/api/stop`       | Signal session stop, finalize bookkeeping    |
| POST   | `/api/stop-recording` | Stop ffmpeg recording, finalize MP4      |


## OpenClaw Agent Integration

The container uses [OpenClaw](https://github.com/openclaw/openclaw) as the agent driver to perform actions on the in-container Chromium browser via CDP. All agent actions are transparently recorded by the existing extension and server infrastructure.

### Environment Variables

| Variable                          | Example                                                | Description                                          |
| --------------------------------- | ------------------------------------------------------ | ---------------------------------------------------- |
| `MODEL_NAME`                      | `claude-sonnet-4-6`, `gemini-3-flash-preview`          | Model identifier                                     |
| `BASE_URL`                        | `https://api.openai.com/v1`                            | API base URL                                         |
| `API_TYPE`                        | `openai-completions`                                   | API type (`openai-completions`, `anthropic-messages`, etc.) |
| `API_KEY`                         | `sk-ant-...`, `AIza...`                                | API key                                              |
| `INSTRUCTION`                     | `"Go to example.com and…"`                             | Task prompt for the agent                            |
| `TIME_LIMIT_S`                    | `300`                                                  | Watchdog timeout in seconds (default: 600)           |
| `THINKING_LEVEL`                  | `high`, `low`, `off`                                   | Reasoning depth (default: `medium`)                  |
| `TEMPERATURE`                     | `0.5`                                                  | Sampling temperature (optional)                      |
| `MAX_TOKENS`                      | `4096`                                                 | Max output tokens (optional)                         |

### Container Lifecycle with OpenClaw

The entrypoint (`entrypoint.sh`) orchestrates the following sequence:

1. **Xvfb** — virtual display at `:99` (1920x1080)
2. **FastAPI server** — data collection API on port 7878, starts ffmpeg screen recording
3. **Chromium** — with Chrome extension loaded, CDP on port 9222
4. **socat** — forwards port 9223 (external) to 9222 (internal CDP)
5. **setup-openclaw.sh** — generates `~/.openclaw/openclaw.json` and auth credentials from env vars
6. **CDP health check** — polls `http://127.0.0.1:9222/json/version` until Chrome is ready
7. **OpenClaw gateway** — local mode, manages agent execution and browser tool
8. **OpenClaw agent** — runs `openclaw agent --session-id clawbench --message "$INSTRUCTION" --local`
9. **Watchdog** — monitors `/data/actions.jsonl`; stops when the eval interceptor matches (via `/data/.stop-requested`), after 900s of no new actions, or when `TIME_LIMIT_S` is reached
10. **Cleanup** — kills OpenClaw processes, calls `POST /api/stop` for bookkeeping, waits 15s grace period for recording to capture end result, calls `POST /api/stop-recording` to finalize MP4, exits

### OpenClaw Configuration

`setup-openclaw.sh` generates two files at runtime:

- **`~/.openclaw/openclaw.json`** — gateway config (local mode), model provider settings, and browser profile pointing to `http://127.0.0.1:9222` (the in-container Chrome CDP endpoint)
- **`~/.openclaw/agents/main/agent/auth-profiles.json`** — API key credentials for the configured provider

The provider's `baseUrl` and `api` type are passed directly from the model config in `models.yaml` via `BASE_URL` and `API_TYPE` environment variables.

### OpenClaw Browser Patch

OpenClaw's built-in browser tool uses [chrome-devtools-mcp](https://github.com/anthropics/anthropic-quickstarts/tree/main/chrome-devtools-mcp) to control the browser. However, as of `v2026.3.13`, the `existing-session` driver hardcodes `--autoConnect` when launching chrome-devtools-mcp, which only discovers Chrome via the `DevToolsActivePort` file in the default user data directory. It ignores the `cdpUrl` set in the browser profile config and never passes `--browserUrl` to chrome-devtools-mcp. This means the browser tool cannot connect to our Chromium instance running on port 9222. See [openclaw/openclaw#47879](https://github.com/openclaw/openclaw/issues/47879).

**Workaround applied in the Dockerfile:**

- OpenClaw is pinned to `v2026.3.13`
- A `sed` patch replaces `"--autoConnect"` with `"--browserUrl","http://127.0.0.1:9222"` across all bundled dist files
- Chromium is launched with `--remote-allow-origins=*` (required for chrome-devtools-mcp's internal WebSocket connections on Chrome 132+)

Once [#47879](https://github.com/openclaw/openclaw/issues/47879) is resolved upstream, the version pin and patch can be removed.

## Synthetic User Profile

Each container has a `/my-info/` directory (read-only) containing a dummy user's identity and credentials:

```
/my-info/
  alex_green_personal_info.json   # Full profile (contact, address, education, work, etc.)
  email_credentials.json          # Auto-generated email + password + login URL
  alex_green_resume.pdf           # Resume PDF with dynamic email in header
```

The `email` field in both the personal info JSON and the resume PDF is updated each run to match the disposable email created for that session. The agent is instructed to read these files when it needs personal details for form filling, registration, etc.

Source templates live in `shared/` (personal info) and `test-driver/resume_template.json` (resume). The PDF is generated at runtime by `test-driver/generate_resume_pdf.py`.

## Tool Restrictions

The `exec` tool is set to `allowlist` security mode in the generated OpenClaw config. Only safe, read-only commands are permitted (`ls`, `cat`, `find`, `file`, `grep`, `sort`, `head`, `tail`, `jq`, `cut`, `uniq`, `tr`, `wc`). Commands that could bypass the browser (e.g., `curl`, `python`, `node`, `wget`, `smtplib`) are blocked. The agent uses `cat` to read files in `/my-info/` (the core files are listed in the instruction prompt, but `ls` is still available for extra info discovery).

The agent instruction prompt also explicitly requires browser-only task completion.

## Request Interceptor

The interceptor blocks critical, irreversible HTTP requests (checkout, form submission, review posting, etc.) to prevent the agent from causing real-world side effects during evaluation. It does **not** validate task completion — evaluation is handled separately by evaluators post-session.

### How It Works

1. Mount a JSON config at `/eval-schema.json` in the container
2. The server connects to Chrome via CDP (`Fetch` domain) and intercepts all requests
3. When a request matches the `url_pattern` (regex), `method`, and optional `body`/`params` filters, the request is blocked
4. The blocked request's details are saved to `interception.json`, the agent is killed, and the recording stops

### Schema Format

The eval schema has two required fields (`url_pattern`, `method`) and two optional fields (`body`, `params`) for disambiguation.

```json
{
  "url_pattern": "inbox\\.purelymail\\.com",
  "method": "POST",
  "body": { "_action": "send" }
}
```

The optional `body` and `params` are flat key-value maps — each key must match exactly in the request data. Use them when the same URL + method serves multiple actions (e.g., login vs send on the same endpoint, or different GraphQL operations).

For tasks behind payment walls or other natural blockers (agent has no valid credit card), use the placeholder pattern that never matches:

```json
{
  "url_pattern": "__PLACEHOLDER_WILL_NOT_MATCH__",
  "method": "POST"
}
```

### When to Block

The interceptor is only needed for actions that would have **irreversible real-world consequences** without a payment wall:

| Block   | Examples                                                                                                                          |
| ------- | --------------------------------------------------------------------------------------------------------------------------------- |
| **Yes** | Public reviews, listings, job applications, contact forms, email sends, appointment bookings, website creation                    |
| **No**  | Purchases, subscriptions, donations (payment wall), cart additions (reversible), searches (reversible), account creation (benign) |


### Interception Output

`/data/interception.json`:

```json
{
  "intercepted": true,
  "request": {
    "url": "https://inbox.purelymail.com/action",
    "method": "POST",
    "params": {},
    "body": {"_action": "send", "_to": "user@example.com"}
  }
}
```

## Test Driver

The test driver (`test-driver/run.py`) automates running test cases end-to-end: creates a disposable email via PurelyMail, launches a container, enforces a time limit, collects results, and cleans up. Test cases are defined in `test-cases/` with a `task.json` validated by `test-cases/task.schema.json`.

```bash
# Interactive menu (configure models, select cases, choose run mode):
./run.sh

# Or run directly:
uv run --project test-driver test-driver/run.py test-cases/886-entertainment-hobbies-experience-topgolf qwen3.5-397b-a17b

# Human mode (no agent — you control the browser via noVNC):
uv run --project test-driver test-driver/run.py test-cases/886-entertainment-hobbies-experience-topgolf --human

# Batch: all models x cases 1-50, 3 concurrent
uv run test-driver/batch.py --all-models --case-range 1-50 --max-concurrent 3

```

See [test-driver/README.md](test-driver/README.md) for full documentation.

## Human Mode

Human mode lets you perform test cases manually in the browser instead of using an AI agent. This is useful for collecting human baselines, debugging test cases, or verifying that a task is completable.

The container runs the same infrastructure (Xvfb, Chromium, extension, FastAPI server, ffmpeg recording) but instead of launching an OpenClaw agent, it exposes the browser via [noVNC](https://novnc.com/) — a browser-based VNC client.

### Usage

```bash
# Via interactive menu (select "Human mode"):
./run.sh

# Or directly:
uv run --project test-driver test-driver/run.py test-cases/886-entertainment-hobbies-experience-topgolf --human
```

After the container starts, open the noVNC URL printed in the terminal:

```
noVNC ready: http://localhost:6080/vnc.html
```

You'll see the Chromium browser in your web browser. Complete the task manually — all your actions, screenshots, and HTTP requests are recorded just like in agent mode.

### How it ends

The session stops when any of these happen:

- **Eval interceptor matches** — the target HTTP request was detected (task completed)
- **VNC disconnect** — you close the noVNC tab (15s grace period for reconnection)
- **Time limit** — the configured time limit expires

After the session ends, results are collected in the same format as agent runs (actions, screenshots, recording, interception).

## License

This project is licensed under the Apache License 2.0 — see the [LICENSE](LICENSE) file for details.

## Acknowledgments

ClawBench uses the following open-source projects:

- [noVNC](https://github.com/novnc/noVNC) (MPL 2.0) — browser-based VNC client for human mode
- [websockify](https://github.com/novnc/websockify) (LGPL 3.0) — WebSocket-to-TCP proxy for VNC
- [OpenClaw](https://github.com/openclaw/openclaw) — AI agent driver for browser automation