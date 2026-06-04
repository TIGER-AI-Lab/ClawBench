#!/bin/bash
set -e

# All config comes from env vars set by the test driver (sourced from models.yaml).
# BASE_URL, MODEL_NAME, and API_TYPE are required.
if [ -z "$BASE_URL" ] || [ -z "$MODEL_NAME" ] || [ -z "$API_TYPE" ]; then
  echo "ERROR: BASE_URL, MODEL_NAME, and API_TYPE must be set"
  exit 1
fi

# Harbor's Terminus 2 agent uses LiteLLM under the hood. The actual provider /
# model / api_base / credential mapping happens in harbor_driver.py (in-process,
# so it can set the provider env vars LiteLLM reads). This script only validates
# the inputs and surfaces the same "feature not exposed" warnings the other
# harnesses print, so behaviour is predictable across harnesses.

if [ -n "$TEMPERATURE" ]; then
  echo "WARN: harbor harness does not pass TEMPERATURE to Terminus; TEMPERATURE='$TEMPERATURE' will be ignored."
fi
if [ -n "$MAX_TOKENS" ]; then
  echo "WARN: harbor harness does not pass MAX_TOKENS to Terminus; MAX_TOKENS='$MAX_TOKENS' will be ignored."
fi

# Terminus writes its tmux pane log + trajectory under /logs/agent.
mkdir -p /logs/agent /root/workspace

echo "harbor setup: model=$MODEL_NAME, api_type=$API_TYPE (mapping resolved in harbor_driver.py)"
