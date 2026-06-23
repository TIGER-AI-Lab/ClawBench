#!/bin/bash
set -e

# All config comes from env vars set by the test driver (sourced from models.yaml).
# BASE_URL, API_TYPE, and MODEL_NAME are required.
if [ -z "$BASE_URL" ] || [ -z "$API_TYPE" ] || [ -z "$MODEL_NAME" ]; then
  echo "ERROR: BASE_URL, API_TYPE, and MODEL_NAME must be set"
  exit 1
fi

# Map ClawBench api_type → opencode provider id + npm package.
case "$API_TYPE" in
  anthropic-messages)
    PROVIDER_ID="anthropic"
    PROVIDER_NPM="@ai-sdk/anthropic"
    ;;
  openai-responses)
    PROVIDER_ID="openai"
    PROVIDER_NPM="@ai-sdk/openai"
    ;;
  openai-completions)
    PROVIDER_ID="openai-compat"
    PROVIDER_NPM="@ai-sdk/openai-compatible"
    ;;
  google-generative-ai)
    PROVIDER_ID="google"
    PROVIDER_NPM="@ai-sdk/google"
    ;;
  *)
    echo "ERROR: unsupported API_TYPE '$API_TYPE'"
    exit 1
    ;;
esac

mkdir -p ~/.config/opencode

# Build opencode.json
export OPENCODE_PROVIDER_ID="$PROVIDER_ID"
export OPENCODE_PROVIDER_NPM="$PROVIDER_NPM"
python3 - <<'PYEOF'
import json, os
from pathlib import Path

provider_id = os.environ["OPENCODE_PROVIDER_ID"]
provider_npm = os.environ["OPENCODE_PROVIDER_NPM"]
model_name = os.environ["MODEL_NAME"]
base_url = os.environ["BASE_URL"]

# Pick a single API key (first from API_KEYS list, else API_KEY).
keys_json = os.environ.get("API_KEYS", "")
single_key = os.environ.get("API_KEY", "")
key = ""
if keys_json:
    try:
        parsed = json.loads(keys_json)
        if parsed:
            key = parsed[0]
            if len(parsed) > 1:
                print(f"WARN: opencode does not rotate keys — using first of {len(parsed)}")
    except json.JSONDecodeError:
        pass
if not key and single_key:
    key = single_key
if not key:
    raise SystemExit("ERROR: no API key provided (API_KEYS or API_KEY)")

model_options = {}
temperature = os.environ.get("TEMPERATURE", "")
if temperature:
    model_options["temperature"] = float(temperature)

model_limit = {}
max_tokens = os.environ.get("MAX_TOKENS", "")
if max_tokens:
    model_limit["output"] = int(max_tokens)

# Reasoning surfacing. Three things must line up for opencode to emit
# `reasoning` events in --format json:
#   1. `reasoning: true` on the model (capability flag).
#   2. `interleaved.field` so opencode round-trips reasoning back to the
#      provider on later turns. OpenRouter uses `reasoning_content`.
#   3. `options.reasoning.effort` so OpenRouter actually generates and
#      streams reasoning back for reasoning-capable models (Qwen3, etc.).
# The `--thinking` flag on `opencode run` (set by run-opencode.sh) is the
# fourth gate; without it opencode captures reasoning but suppresses it
# from the JSONL stream.
thinking_level = os.environ.get("THINKING_LEVEL", "").lower()
_EFFORT_MAP = {
    "minimal": "low", "low": "low",
    "medium": "medium", "adaptive": "medium",
    "high": "high", "xhigh": "high",
}
reasoning_enabled = thinking_level not in ("", "off")
if reasoning_enabled:
    effort = _EFFORT_MAP.get(thinking_level, "medium")
    model_options["reasoning"] = {"effort": effort}

model_entry = {}
if reasoning_enabled:
    model_entry["reasoning"] = True
    model_entry["interleaved"] = {"field": "reasoning_content"}
if model_options:
    model_entry["options"] = model_options
if model_limit:
    model_entry["limit"] = model_limit

config = {
    "$schema": "https://opencode.ai/config.json",
    "provider": {
        provider_id: {
            "npm": provider_npm,
            "options": {
                "baseURL": base_url,
                "apiKey": key,
            },
            "models": {
                model_name: model_entry,
            },
        },
    },
    # Mirror openclaw's allowlist posture: deny everything the agent
    # could use to escape the sandbox; allow only safe read-only bins.
    # opencode permission semantics: last-matching rule wins.
    "permission": {
        "bash": {
            "*": "deny",
            "ls *": "allow", "ls": "allow",
            "cat *": "allow",
            "find *": "allow",
            "file *": "allow",
            "jq *": "allow",
            "cut *": "allow",
            "uniq *": "allow",
            "head *": "allow",
            "tail *": "allow",
            "tr *": "allow",
            "wc *": "allow",
            "grep *": "allow",
            "sort *": "allow",
        },
        "edit": "deny",
        "write": "deny",
        "webfetch": "deny",
    },
    # Browser control via Microsoft's Playwright MCP, attached to the
    # same Chromium that the extension-server / interceptor are watching.
    "mcp": {
        "playwright": {
            "type": "local",
            "command": [
                "npx", "@playwright/mcp",
                "--cdp-endpoint", os.environ["CLAWBENCH_BROWSER_CDP_URL"],
            ],
            "enabled": True,
        },
    },
}

cfg_path = Path.home() / ".config" / "opencode" / "opencode.json"
cfg_path.write_text(json.dumps(config, indent=2))
os.chmod(cfg_path, 0o600)
print(f"opencode config: provider={provider_id}, model={model_name}, base_url={base_url}")
PYEOF
