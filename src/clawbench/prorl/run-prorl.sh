#!/bin/bash
#
# Polar shell-harness entry for ClawBench.
#
# Polar's gateway injects an OpenAI-compatible endpoint whose API key IS the
# session id; every call to it is proxied and captured into the trajectory that
# gets trained. We point the ClawBench browser agent's *policy* model at that
# endpoint via the env vars the bundled harnesses actually read
# (BASE_URL / API_KEY / API_TYPE / MODEL_NAME), set the task INSTRUCTION, and
# hand off to the image's env-driven /run-harness.sh (no flags — the concrete
# harness is baked into the image; pick it with --image at submit time).
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

# Route the ClawBench agent model through the captured gateway endpoint, using
# the exact env vars the harness runners consume.
export BASE_URL="${OPENAI_BASE_URL}"
export API_KEY="${OPENAI_API_KEY}"
export API_TYPE="openai-completions"
export MODEL_NAME="${POLAR_MODEL_NAME}"

# The browser runtime (brought up by prepare/setup.sh -> start-runtime.sh)
# exposes CDP on :9223. The harness setup reads CLAWBENCH_BROWSER_CDP_URL; the
# base entrypoint that would normally default it is bypassed by this custom
# shell, so set it here.
export CLAWBENCH_BROWSER_CDP_URL="${CLAWBENCH_BROWSER_CDP_URL:-http://127.0.0.1:9223}"
export CLAWBENCH_BROWSER_MODE="${CLAWBENCH_BROWSER_MODE:-local}"

# The task instruction drives the episode (the base entrypoint/harness reads
# $INSTRUCTION).
INSTRUCTION_FILE="${CLAWBENCH_INSTRUCTION_FILE:-/app/instruction.md}"
if [ -f "${INSTRUCTION_FILE}" ]; then
  INSTRUCTION="$(cat "${INSTRUCTION_FILE}")"
  export INSTRUCTION
fi

# Wait for the browser runtime that the `prepare`/setup.sh step brought up.
for _ in $(seq 1 60); do
  if curl -sf http://127.0.0.1:7878/api/status >/dev/null 2>&1; then
    break
  fi
  sleep 1
done

# Hand off to the harness runner baked into the image. It connects to the
# existing CDP browser and calls the policy model via the BASE_URL/API_KEY env
# above (env-driven; no flags). A non-zero exit still yields a gradeable
# trajectory, so don't fail hard on the agent.
if [ ! -x /run-harness.sh ]; then
  echo "ERROR: /run-harness.sh missing — image built without a ClawBench harness layer" >&2
  echo "missing_harness" >/data/.stop-reason 2>/dev/null || true
  exit 1
fi
exec /run-harness.sh
