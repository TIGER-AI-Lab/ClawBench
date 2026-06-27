#!/bin/bash
set -e

# All config comes from env vars set by the test driver (sourced from models.yaml).
# BASE_URL and MODEL_NAME are required.
if [ -z "$BASE_URL" ] || [ -z "$MODEL_NAME" ]; then
  echo "ERROR: BASE_URL and MODEL_NAME must be set"
  exit 1
fi

if [ -n "$TEMPERATURE" ]; then
  echo "WARN: Claude Code CLI does not expose a --temperature flag; TEMPERATURE='$TEMPERATURE' will be ignored."
fi
if [ -n "$MAX_TOKENS" ]; then
  echo "WARN: Claude Code CLI does not expose a --max-tokens flag; MAX_TOKENS='$MAX_TOKENS' will be ignored."
fi

# Generate /tmp/claude-code-env.sh + /tmp/litellm-config.yaml + /tmp/claude-mcp.json.
# Everything routes through LiteLLM on localhost:4000
python3 - <<'PYEOF'
import json, os, urllib.request
from pathlib import Path
import yaml

base_url = os.environ["BASE_URL"]
model_name = os.environ["MODEL_NAME"]
api_type = os.environ.get("API_TYPE", "anthropic-messages")

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
                print(f"WARN: Claude Code does not rotate keys — using first of {len(parsed)}")
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
# tool-call and reasoning fidelity.
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
    raise SystemExit(f"ERROR: unsupported api_type for claude-code harness: {api_type}")

proxy_config = {
    "model_list": [{
        "model_name": model_name,
        "litellm_params": litellm_params,
    }],
    # drop_params: silently drop Anthropic-specific params that can't
    # be translated (e.g. thinking budget) instead of erroring.
    "litellm_settings": {"drop_params": True},
}
proxy_path = Path("/tmp/litellm-config.yaml")
proxy_path.write_text(yaml.dump(proxy_config, default_flow_style=False))
os.chmod(proxy_path, 0o600)

anthropic_base_url = "http://localhost:4000"
anthropic_api_key = "sk-proxy-placeholder"
print(f"API proxy enabled: {api_type} → litellm ({litellm_params['model']})")

# Write a sourceable env file for the run script.
env_path = Path("/tmp/claude-code-env.sh")
env_lines = [
    f'export ANTHROPIC_API_KEY="{anthropic_api_key}"',
    f'export ANTHROPIC_BASE_URL="{anthropic_base_url}"',
]
env_path.write_text("\n".join(env_lines) + "\n")
os.chmod(env_path, 0o600)

# Write MCP config file for --mcp-config flag.
mcp_config = {
    "mcpServers": {
        "playwright": {
            "command": "npx",
            "args": [
                "@playwright/mcp",
                "--cdp-endpoint",
                os.environ["CLAWBENCH_BROWSER_CDP_URL"],
            ],
        },
    },
}
mcp_path = Path("/tmp/claude-mcp.json")
mcp_path.write_text(json.dumps(mcp_config, indent=2))
os.chmod(mcp_path, 0o644)

print(f"Claude Code config: model={model_name}, base_url={anthropic_base_url}")
PYEOF
