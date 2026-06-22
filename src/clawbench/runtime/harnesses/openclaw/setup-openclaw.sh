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
#
# Three things are needed for the allowlist to actually enforce in --local mode:
#   1. security: "allowlist" — engage the allowlist code path.
#   2. ask: "off" — disable the approval-prompt flow. With the default
#      "on-miss", non-allowlisted commands fall through to a gateway-side
#      approval request which auto-resolves to allow-once in --local mode
#      (no human approver wired), defeating the allowlist entirely.
#   3. safeBinProfiles for ls/cat/find/file — the built-in
#      SAFE_BIN_PROFILES only ships profiles for jq/grep/cut/sort/head/tail/
#      tr/uniq/wc, so any safeBins entry not in that set is silently dropped
#      ("ignoring unprofiled safeBins entries" warning in gateway.log).
#      User-provided profiles are merged with the built-in, so we only need
#      to declare the 4 missing bins. Empty `{}` profiles allow any args.
cat > ~/.openclaw/openclaw.json << JSONEOF
{
  "gateway": {
    "port": 18789,
    "mode": "local"
  },
  "tools": {
    "exec": {
      "host": "gateway",
      "security": "allowlist",
      "ask": "off",
      "safeBins": ["ls", "cat", "find", "file", "jq", "cut", "uniq", "head", "tail", "tr", "wc", "grep", "sort"],
      "safeBinProfiles": {
        "ls": {},
        "cat": {},
        "find": {},
        "file": {}
      }
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
        "cdpUrl": "$CLAWBENCH_BROWSER_CDP_URL",
        "color": "#FB542B"
      }
    }
  }
}
JSONEOF

# Write the exec-approvals file with ask=off and askFallback=deny.
# This is the *only* place the per-tool/per-host approval policy actually
# lives — `tools.exec.ask` in openclaw.json is just a per-call default that
# gets combined with this file via maxAsk(). If we don't pin ask=off here,
# the agent's ask defaults to "on-miss" (DEFAULT_ASK) and any unprofiled
# command falls into the gateway approval flow, which auto-resolves in
# --local mode without a wired human approver — defeating the allowlist.
cat > ~/.openclaw/exec-approvals.json << 'APPROVALSEOF'
{
  "version": 1,
  "defaults": {
    "security": "allowlist",
    "ask": "off",
    "askFallback": "deny"
  },
  "agents": {}
}
APPROVALSEOF
chmod 600 ~/.openclaw/exec-approvals.json

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
