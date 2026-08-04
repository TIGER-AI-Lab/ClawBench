#!/bin/bash
set -e

if [ "${CLAWBENCH_BROWSER_MODE:-local}" != "local" ]; then
  echo "ERROR: the WebBrain harness requires local browser mode so its extension can be loaded"
  exit 1
fi

if [ "${API_TYPE:-}" != "openai-completions" ]; then
  echo "ERROR: unsupported API_TYPE for WebBrain harness: ${API_TYPE:-<missing>} (expected openai-completions)"
  exit 1
fi

if [ -z "${BASE_URL:-}" ] || [ -z "${MODEL_NAME:-}" ]; then
  echo "ERROR: BASE_URL and MODEL_NAME must be set"
  exit 1
fi

if [ ! -f /app/webbrain/src/chrome/manifest.json ]; then
  echo "ERROR: pinned WebBrain extension is missing from the harness image"
  exit 1
fi

echo "WebBrain harness configured for model=${MODEL_NAME}"
