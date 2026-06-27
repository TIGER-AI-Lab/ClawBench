#!/bin/bash
set -e

# All config comes from env vars set by the test driver (sourced from models.yaml).
# BASE_URL, MODEL_NAME, and API_TYPE are required.
if [ -z "$BASE_URL" ] || [ -z "$MODEL_NAME" ] || [ -z "$API_TYPE" ]; then
  echo "ERROR: BASE_URL, MODEL_NAME, and API_TYPE must be set"
  exit 1
fi

if [ -n "$TEMPERATURE" ]; then
  echo "WARN: Codex CLI does not expose a temperature flag for 'codex exec'; TEMPERATURE='$TEMPERATURE' will be ignored."
fi
if [ -n "$MAX_TOKENS" ]; then
  echo "WARN: Codex CLI does not expose a max-tokens flag for 'codex exec'; MAX_TOKENS='$MAX_TOKENS' will be ignored."
fi

mkdir -p "$HOME/.codex"

# Generate ~/.codex/config.toml + /tmp/codex-env.sh + /tmp/litellm-config.yaml.
# Everything routes through LiteLLM on localhost:4000
python3 - <<'PYEOF'
import json, os, urllib.request
from pathlib import Path
import yaml

base_url = os.environ["BASE_URL"]
model_name = os.environ["MODEL_NAME"]
api_type = os.environ["API_TYPE"]

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
                print(f"WARN: Codex does not rotate keys — using first of {len(parsed)}")
    except json.JSONDecodeError:
        pass
if not key and single_key:
    key = single_key
if not key:
    raise SystemExit("ERROR: no API key provided (API_KEYS or API_KEY)")

# ── Resolve the upstream model id (OpenRouter only) ──────────────────
# OpenRouter expects the canonical full id (e.g. "qwen/qwen3.5-...").
resolved_model = model_name
is_openrouter = "openrouter.ai" in base_url
if is_openrouter:
    try:
        req = urllib.request.Request(
            f"{base_url}/models",
            headers={"Authorization": f"Bearer {key}"},
        )
        resp = json.loads(urllib.request.urlopen(req, timeout=10).read())
        for m in resp.get("data", []):
            if m["id"].endswith(f"/{model_name}") or m["id"] == model_name:
                resolved_model = m["id"]
                break
    except Exception as e:
        print(f"WARN: could not resolve OpenRouter model ID: {e}")

# ── Pick the LiteLLM provider prefix ────────────────────────────────
# The prefix tells LiteLLM which native API format to translate to.
# We prefer provider-specific prefixes (`openrouter/`, `anthropic/`,
# `gemini/`) over the generic `openai/` since they have better
# tool-call fidelity.
litellm_params = {"api_key": key}
if is_openrouter:
    litellm_params["model"] = f"openrouter/{resolved_model}"
elif api_type == "anthropic-messages":
    litellm_params["model"] = f"anthropic/{model_name}"
    if not base_url.startswith("https://api.anthropic.com"):
        litellm_params["api_base"] = base_url
elif api_type == "google-generative-ai":
    litellm_params["model"] = f"gemini/{model_name}"
    if not base_url.startswith("https://generativelanguage.googleapis.com"):
        litellm_params["api_base"] = base_url
elif api_type in ("openai-completions", "openai-responses"):
    litellm_params["model"] = f"openai/{model_name}"
    litellm_params["api_base"] = base_url
else:
    raise SystemExit(f"ERROR: unsupported api_type for codex harness: {api_type}")

proxy_config = {
    "model_list": [{
        "model_name": model_name,
        "litellm_params": litellm_params,
    }],
    # drop_params: silently ignore OpenAI-only fields (service_tier,
    # reasoning.summary, etc.) that non-OpenAI providers would reject.
    "litellm_settings": {"drop_params": True},
}
Path("/tmp/litellm-config.yaml").write_text(
    yaml.dump(proxy_config, default_flow_style=False))
os.chmod("/tmp/litellm-config.yaml", 0o600)

# ── Reasoning effort ────────────────────────────────────────────────
_EFFORT_MAP = {
    "minimal":  "minimal",
    "low":      "low",
    "medium":   "medium",
    "adaptive": "medium",
    "high":     "high",
    "xhigh":    "high",
}
thinking = (os.environ.get("THINKING_LEVEL") or "").lower()
if thinking and thinking != "off":
    reasoning_effort = _EFFORT_MAP.get(thinking, "medium")
else:
    reasoning_effort = "minimal"

# ── Codex config (~/.codex/config.toml) ─────────────────────────────
def toml_escape(s: str) -> str:
    return s.replace("\\", "\\\\").replace("\"", "\\\"")

browser_cdp_url = toml_escape(os.environ["CLAWBENCH_BROWSER_CDP_URL"])

toml = f'''\
model = "{toml_escape(model_name)}"
model_provider = "clawbench"
model_reasoning_effort = "{reasoning_effort}"
model_reasoning_summary = "auto"
# Emit raw chain-of-thought into the --json event stream as
# `agent_reasoning_raw_content` / `reasoning_content_delta` items.
# Without this Codex only surfaces summaries, which upstream providers
# don't always produce for non-OpenAI models.
show_raw_agent_reasoning = true
hide_agent_reasoning = false
approval_policy = "never"
sandbox_mode = "read-only"

[model_providers.clawbench]
name = "ClawBench provider (via LiteLLM)"
base_url = "http://localhost:4000"
env_key = "CODEX_API_KEY"
wire_api = "responses"

# Codex manages the Playwright MCP itself
[mcp_servers.playwright]
command = "npx"
args = ["@playwright/mcp", "--cdp-endpoint", "{browser_cdp_url}"]
'''
config_path = Path(os.path.expanduser("~/.codex/config.toml"))
config_path.write_text(toml)
os.chmod(config_path, 0o600)

# Sourceable env file for the run script.
env_path = Path("/tmp/codex-env.sh")
env_path.write_text('export CODEX_API_KEY="sk-proxy-placeholder"\n')
os.chmod(env_path, 0o600)

print(f"Codex config: model={model_name}, upstream={litellm_params['model']}, "
      f"wire_api=responses, reasoning_effort={reasoning_effort}")
PYEOF
