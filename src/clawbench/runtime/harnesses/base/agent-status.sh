#!/bin/bash

# The host copies this file from /data after a harness exits. Keep the status
# separate from .stop-reason so watchdog decisions can remain human-readable.
AGENT_STATUS_DIR="${AGENT_STATUS_DIR:-/data}"

write_agent_status() {
  local exit_code="${1:-null}"
  local exit_reason="${2:-unknown}"

  case "$exit_code" in
    null) ;;
    ''|*[!0-9]*) exit_code=null ;;
  esac
  printf '{"agent_exit_code":%s,"agent_exit_reason":"%s"}\n' \
    "$exit_code" "$exit_reason" > "$AGENT_STATUS_DIR/agent-status.json"
}

capture_agent_exit() {
  local pid="$1"
  AGENT_EXIT_CODE=0
  wait "$pid" || AGENT_EXIT_CODE=$?
  write_agent_status "$AGENT_EXIT_CODE" "self_exit"
}

capture_agent_command() {
  AGENT_EXIT_CODE=0
  "$@" || AGENT_EXIT_CODE=$?
  write_agent_status "$AGENT_EXIT_CODE" "self_exit"
}

capture_watchdog_stop() {
  write_agent_status null "watchdog"
}
