#!/bin/bash
set -e

# All config comes from env vars set by the test driver (sourced from models.yaml).
# BASE_URL, MODEL_NAME, and API_TYPE are required.
if [ -z "$BASE_URL" ] || [ -z "$MODEL_NAME" ] || [ -z "$API_TYPE" ]; then
  echo "ERROR: BASE_URL, MODEL_NAME, and API_TYPE must be set"
  exit 1
fi

if [ -n "$MAX_TOKENS" ]; then
  echo "WARN: browser-use does not expose a max-tokens knob; MAX_TOKENS='$MAX_TOKENS' will be ignored."
fi

# Generate /tmp/browser-use-env.sh + /tmp/litellm-config.yaml.
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
                print(f"WARN: browser-use does not rotate keys — using first of {len(parsed)}")
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
# Provider-specific prefixes give better tool-call and reasoning
# fidelity than the generic `openai/` prefix.
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
    raise SystemExit(f"ERROR: unsupported api_type for browser-use harness: {api_type}")

proxy_config = {
    "model_list": [{
        "model_name": model_name,
        "litellm_params": litellm_params,
    }],
    # drop_params: silently ignore fields the upstream doesn't accept
    # instead of erroring out (e.g. service_tier for non-OpenAI).
    "litellm_settings": {
        "drop_params": True,
        "success_callback": ["browser_use_usage_logger.proxy_handler_instance"],
    },
}
Path("/tmp/litellm-config.yaml").write_text(
    yaml.dump(proxy_config, default_flow_style=False))
os.chmod("/tmp/litellm-config.yaml", 0o600)

# Sourceable env file for the run script / agent script. BU_MODEL_NAME
# is what browser-use sends to LiteLLM — it must match `model_name` in
# the LiteLLM config so the proxy routes correctly.
env_path = Path("/tmp/browser-use-env.sh")
env_path.write_text(
    f'export BU_MODEL_NAME="{model_name}"\n'
    f'export BU_UPSTREAM_BASE_URL="{base_url}"\n'
    f'export BU_UPSTREAM_MODEL_ID="{resolved_model}"\n'
    f'export BU_BASE_URL="http://localhost:4000"\n'
    f'export BU_API_KEY="sk-proxy-placeholder"\n'
    f'export BU_TEMPERATURE="{os.environ.get("TEMPERATURE", "0.0")}"\n'
    f'export BU_THINKING_LEVEL="{(os.environ.get("THINKING_LEVEL") or "off").lower()}"\n'
)
os.chmod(env_path, 0o600)

print(f"browser-use config: model={model_name}, upstream={litellm_params['model']}")
PYEOF
