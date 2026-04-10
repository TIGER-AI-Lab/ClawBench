#!/bin/bash
set -e

# All config comes from env vars set by the test driver (sourced from models.yaml).
# BASE_URL and API_TYPE are required.
if [ -z "$BASE_URL" ] || [ -z "$API_TYPE" ]; then
  echo "ERROR: BASE_URL and API_TYPE must be set"
  exit 1
fi

PROVIDER="api"
MODEL="api/$MODEL_NAME"
MODEL_ID="$MODEL_NAME"

# Build optional model parameters
MODEL_OPTS=""
if [ -n "$TEMPERATURE" ]; then
  MODEL_OPTS="$MODEL_OPTS, \"temperature\": $TEMPERATURE"
fi
if [ -n "$MAX_TOKENS" ]; then
  MODEL_OPTS="$MODEL_OPTS, \"maxOutputTokens\": $MAX_TOKENS"
fi

mkdir -p ~/.openclaw/agents/main/agent

# Restrict exec to safe read-only commands (allowlist mode).
# The agent cannot run curl, python, node, etc. — only ls/cat/grep and default safe bins.
cat > ~/.openclaw/openclaw.json << JSONEOF
{
  "gateway": {
    "port": 18789,
    "mode": "local"
  },
  "tools": {
    "exec": {
      "security": "allowlist",
      "safeBins": ["ls", "cat", "find", "file", "jq", "cut", "uniq", "head", "tail", "tr", "wc", "grep", "sort"]
    }
  },
  "agents": {
    "defaults": {
      "workspace": "/root/workspace",
      "skipBootstrap": true,
      "model": {
        "primary": "$MODEL"
      }
    }
  },
  "models": {
    "providers": {
      "$PROVIDER": {
        "baseUrl": "$BASE_URL",
        "api": "$API_TYPE",
        "models": [
          { "id": "$MODEL_ID", "name": "$MODEL_ID", "reasoning": true$MODEL_OPTS }
        ]
      }
    }
  },
  "browser": {
    "enabled": true,
    "defaultProfile": "container",
    "profiles": {
      "container": {
        "cdpUrl": "http://127.0.0.1:9222",
        "color": "#FB542B"
      }
    }
  }
}
JSONEOF

# Generate auth-profiles.json with multi-key rotation support
python3 -c "
import json, os

provider = '$PROVIDER'

# Parse keys from API_KEYS env var, fall back to API_KEY
keys_json = os.environ.get('API_KEYS', '')
single_key = os.environ.get('API_KEY', '')

keys = []
if keys_json:
    try:
        parsed = json.loads(keys_json)
    except json.JSONDecodeError:
        parsed = []
    keys = [{'key': k, 'source': 'apikey'} for k in parsed]
if not keys and single_key:
    keys = [{'key': single_key, 'source': 'apikey'}]

profiles = {}
order = []
for i, entry in enumerate(keys, 1):
    name = f'{provider}:api-{i}'
    profiles[name] = {
        'provider': provider,
        'type': 'api_key',
        'key': entry['key'],
    }
    order.append(name)

result = {'profiles': profiles, 'order': {provider: order}}

path = os.path.expanduser('~/.openclaw/agents/main/agent/auth-profiles.json')
with open(path, 'w') as f:
    json.dump(result, f, indent=2)
os.chmod(path, 0o600)

print(f'Auth profiles: {len(keys)} API key(s) for {provider}')
"
