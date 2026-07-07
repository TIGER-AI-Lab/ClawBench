#!/bin/bash
#
# Polar shell-harness entry for ClawBench.
#
# Polar's gateway injects an OpenAI-compatible endpoint whose API key IS the
# session id; every call to it is proxied and captured into the trajectory that
# gets trained. We point the ClawBench browser agent's *policy* model at that
# endpoint, then drive one episode against the Chromium session that the runtime
# `prepare` step already started (CDP on :9223, runtime-server on :7878).
#
# CRITICAL: the Stage-2 LLM judge must NOT use $OPENAI_BASE_URL — it runs later,
# host-side, inside the `harbor` evaluator (tests/test.sh -> verify.py) using the
# independent CLAWBENCH_JUDGE_* endpoint. Do not export judge vars from here.
#
set -euo pipefail

: "${OPENAI_BASE_URL:?Polar must inject OPENAI_BASE_URL}"
: "${OPENAI_API_KEY:?Polar must inject OPENAI_API_KEY (the session id)}"

# The trained policy model. The gateway rewrites this name to the served model,
# so the concrete value only has to be a name the harness will send.
POLAR_MODEL_NAME="${POLAR_MODEL_NAME:-clawbench-policy}"

# Route the ClawBench agent model through the captured gateway endpoint.
export CLAWBENCH_BASE_URL="${OPENAI_BASE_URL}"
export CLAWBENCH_API_KEY="${OPENAI_API_KEY}"
export CLAWBENCH_API_TYPE="openai-completions"
export MODEL_NAME="${POLAR_MODEL_NAME}"

# Which ClawBench browser harness drives the episode (hermes is model-agnostic
# over an OpenAI-compatible endpoint). Overridable at submit time.
CLAWBENCH_HARNESS="${CLAWBENCH_HARNESS:-hermes}"

# Wait for the browser runtime that `prepare`/setup.sh brought up.
for _ in $(seq 1 60); do
  if curl -sf http://127.0.0.1:7878/api/status >/dev/null \
    && curl -sf http://127.0.0.1:9223/json/version >/dev/null; then
    break
  fi
  sleep 1
done

INSTRUCTION_FILE="${CLAWBENCH_INSTRUCTION_FILE:-/app/instruction.md}"

# Hand off to the ClawBench harness runner baked into the image. It connects to
# the existing CDP browser and calls the policy model via the CLAWBENCH_* env
# above. The reward is computed separately by the evaluator, so a non-zero exit
# here still yields a gradeable trajectory.
exec /app/run-harness.sh \
  --harness "${CLAWBENCH_HARNESS}" \
  --instruction-file "${INSTRUCTION_FILE}"
