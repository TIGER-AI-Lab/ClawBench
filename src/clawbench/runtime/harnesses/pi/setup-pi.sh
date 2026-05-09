#!/bin/bash
set -e

# All config comes from env vars set by the test driver (sourced from models.yaml).
# BASE_URL, MODEL_NAME, and API_TYPE are required.
if [ -z "$BASE_URL" ] || [ -z "$MODEL_NAME" ] || [ -z "$API_TYPE" ]; then
  echo "ERROR: BASE_URL, MODEL_NAME, and API_TYPE must be set"
  exit 1
fi

if [ -n "$TEMPERATURE" ]; then
  echo "WARN: Pi CLI does not expose a temperature flag; TEMPERATURE='$TEMPERATURE' will be ignored."
fi

mkdir -p "$HOME/.pi/agent"

# Generate ~/.pi/agent/models.json, /tmp/pi-env.sh, and /tmp/litellm-config.yaml.
# Pi always talks OpenAI-compatible chat completions to LiteLLM on localhost:4000.
python3 - <<'PYEOF'
import json
import os
import urllib.request
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
                print(f"WARN: Pi does not rotate keys; using first of {len(parsed)}")
    except json.JSONDecodeError:
        pass
if not key and single_key:
    key = single_key
if not key:
    raise SystemExit("ERROR: no API key provided (API_KEYS or API_KEY)")

# Resolve the upstream model id for OpenRouter; LiteLLM's openrouter provider
# expects the canonical provider/model id.
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
    raise SystemExit(f"ERROR: unsupported api_type for pi harness: {api_type}")

proxy_config = {
    "model_list": [{
        "model_name": model_name,
        "litellm_params": litellm_params,
    }],
    "litellm_settings": {"drop_params": True},
}
proxy_path = Path("/tmp/litellm-config.yaml")
proxy_path.write_text(yaml.dump(proxy_config, default_flow_style=False))
os.chmod(proxy_path, 0o600)

thinking = (os.environ.get("THINKING_LEVEL") or "medium").lower()
thinking_map = {
    "": "off",
    "off": "off",
    "minimal": "minimal",
    "low": "low",
    "medium": "medium",
    "adaptive": "medium",
    "high": "high",
    "xhigh": "xhigh",
}
pi_thinking = thinking_map.get(thinking, "medium")

model_entry = {
    "id": model_name,
    "name": model_name,
    "api": "openai-completions",
    "reasoning": pi_thinking != "off",
    "input": ["text"],
}
max_tokens = os.environ.get("MAX_TOKENS", "")
if max_tokens:
    model_entry["maxTokens"] = int(max_tokens)

models_config = {
    "providers": {
        "clawbench": {
            "baseUrl": "http://localhost:4000",
            "api": "openai-completions",
            # Pi requires an API key for custom models. LiteLLM is local and
            # unauthenticated in this harness, so a placeholder is sufficient.
            "apiKey": "sk-proxy-placeholder",
            "models": [model_entry],
        }
    }
}
models_path = Path.home() / ".pi" / "agent" / "models.json"
models_path.write_text(json.dumps(models_config, indent=2))
os.chmod(models_path, 0o600)

env_path = Path("/tmp/pi-env.sh")
env_path.write_text(
    "\n".join([
        'export PI_PROVIDER="clawbench"',
        f'export PI_MODEL_ID="{model_name}"',
        f'export PI_THINKING="{pi_thinking}"',
        'export PI_CODING_AGENT_DIR="$HOME/.pi/agent"',
    ]) + "\n"
)
os.chmod(env_path, 0o600)

print(
    f"Pi config: model={model_name}, upstream={litellm_params['model']}, "
    f"thinking={pi_thinking}"
)
PYEOF
