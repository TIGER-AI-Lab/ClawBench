#!/usr/bin/env bash
set -euo pipefail

: "${CLAW_TASK:?Missing CLAW_TASK}"
: "${CLAW_START_URL:?Missing CLAW_START_URL}"
: "${CLAW_OUTPUT_DIR:?Missing CLAW_OUTPUT_DIR}"

mkdir -p "$CLAW_OUTPUT_DIR"

XVFB_DISPLAY=${XVFB_DISPLAY:-99}
Xvfb ":$XVFB_DISPLAY" -screen 0 1280x1024x24 &
XVFB_PID=$!
export DISPLAY=":$XVFB_DISPLAY"

cleanup() {
    kill "$XVFB_PID" 2>/dev/null || true
}
trap cleanup EXIT

cd "$(dirname "$0")"

python agent.py
