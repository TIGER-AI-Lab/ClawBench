#!/bin/bash
set -e

# All config comes from env vars set by the test driver (sourced from models.yaml).
# BASE_URL, MODEL_NAME, and API_TYPE are required.
if [ -z "$BASE_URL" ] || [ -z "$MODEL_NAME" ] || [ -z "$API_TYPE" ]; then
  echo "ERROR: BASE_URL, MODEL_NAME, and API_TYPE must be set"
  exit 1
fi

if [ -n "$TEMPERATURE" ]; then
  echo "WARN: Hermes CLI does not currently expose a temperature flag for 'hermes chat'; TEMPERATURE='$TEMPERATURE' will be ignored."
fi
if [ -n "$MAX_TOKENS" ]; then
  echo "WARN: Hermes CLI does not currently expose a max-tokens flag for 'hermes chat'; MAX_TOKENS='$MAX_TOKENS' will be ignored."
fi

mkdir -p "$HOME/.hermes"

# Generate ~/.hermes/config.yaml, ~/.hermes/.env, and /tmp/hermes-env.sh.
python3 - <<'PYEOF'
import json
import os
import shlex
import urllib.request
from pathlib import Path

base_url = os.environ["BASE_URL"].rstrip("/")
model_name = os.environ["MODEL_NAME"]
api_type = os.environ["API_TYPE"]
browser_cdp_url = os.environ["CLAWBENCH_BROWSER_CDP_URL"]

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
                print(f"WARN: Hermes does not rotate keys - using first of {len(parsed)}")
    except json.JSONDecodeError:
        pass
if not key and single_key:
    key = single_key
if not key:
    raise SystemExit("ERROR: no API key provided (API_KEYS or API_KEY)")

# Resolve the upstream model id (OpenRouter only). OpenRouter expects the
# canonical provider-qualified id for most non-OpenAI models.
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
            model_id = m.get("id", "")
            if model_id == model_name or model_id.endswith(f"/{model_name}"):
                resolved_model = model_id
                break
    except Exception as e:
        print(f"WARN: could not resolve OpenRouter model ID: {e}")

# Map ClawBench API types to Hermes provider/api_mode settings.
dotenv_lines = []
if is_openrouter:
    provider = "openrouter"
    api_mode = "chat_completions"
    dotenv_lines.extend([
        f"OPENROUTER_API_KEY={key}",
        f"OPENROUTER_BASE_URL={base_url}",
    ])
elif api_type == "openai-completions":
    provider = "custom"
    api_mode = "chat_completions"
    dotenv_lines.extend([
        f"OPENAI_API_KEY={key}",
        f"OPENAI_BASE_URL={base_url}",
    ])
elif api_type == "openai-responses":
    provider = "custom"
    api_mode = "codex_responses"
    dotenv_lines.extend([
        f"OPENAI_API_KEY={key}",
        f"OPENAI_BASE_URL={base_url}",
    ])
elif api_type == "anthropic-messages":
    provider = "anthropic"
    api_mode = "anthropic_messages"
    dotenv_lines.extend([
        f"ANTHROPIC_API_KEY={key}",
        f"ANTHROPIC_BASE_URL={base_url}",
    ])
elif api_type == "google-generative-ai":
    provider = "gemini"
    api_mode = "chat_completions"
    dotenv_lines.extend([
        f"GOOGLE_API_KEY={key}",
        f"GEMINI_API_KEY={key}",
        f"GEMINI_BASE_URL={base_url}",
    ])
else:
    raise SystemExit(f"ERROR: unsupported api_type for hermes harness: {api_type}")

effort_map = {
    "minimal": "minimal",
    "low": "low",
    "medium": "medium",
    "adaptive": "medium",
    "high": "high",
    "xhigh": "xhigh",
}
thinking = (os.environ.get("THINKING_LEVEL") or "").lower()
reasoning_effort = effort_map.get(thinking, "medium") if thinking and thinking != "off" else "none"

def yaml_scalar(value: str) -> str:
    return json.dumps(value)

config = f"""\
model:
  provider: {yaml_scalar(provider)}
  default: {yaml_scalar(resolved_model)}
  base_url: {yaml_scalar(base_url)}
  api_mode: {yaml_scalar(api_mode)}
agent:
  reasoning_effort: {yaml_scalar(reasoning_effort)}
  show_reasoning: true
  max_turns: 90
browser:
  cdp_url: {yaml_scalar(browser_cdp_url)}
  cloud_provider: "local"
  allow_private_urls: true
  command_timeout: 60
security:
  redact_secrets: false
"""

hermes_home = Path(os.path.expanduser("~/.hermes"))
config_path = hermes_home / "config.yaml"
config_path.write_text(config)
os.chmod(config_path, 0o600)

env_path = hermes_home / ".env"
env_path.write_text("\n".join(dotenv_lines) + "\n")
os.chmod(env_path, 0o600)

run_env = {
    "HERMES_HOME": str(hermes_home),
    "HERMES_MODEL_NAME": resolved_model,
    "HERMES_PROVIDER": provider,
    "HERMES_API_MODE": api_mode,
    "BROWSER_CDP_URL": browser_cdp_url,
    "NO_COLOR": "1",
    "TERM": "xterm-256color",
}
for line in dotenv_lines:
    name, value = line.split("=", 1)
    run_env[name] = value

run_env_path = Path("/tmp/hermes-env.sh")
run_env_path.write_text(
    "".join(f"export {name}={shlex.quote(value)}\n" for name, value in run_env.items())
)
os.chmod(run_env_path, 0o600)

print(
    "Hermes config: "
    f"model={resolved_model}, provider={provider}, api_mode={api_mode}, "
    f"reasoning_effort={reasoning_effort}, browser_cdp={browser_cdp_url}"
)
PYEOF
