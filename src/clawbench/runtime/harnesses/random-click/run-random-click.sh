#!/bin/bash
set -e

source /agent-status.sh
#
# Random-click baseline — a NON-TRIVIAL floor: it clicks at random but with no
# task intent, so it should still score ~0. Shows that browsing activity alone
# (without hitting the target action) does not pass the interceptor.
#
/setup-random-click.sh
mkdir -p /data
: > /data/agent-messages.jsonl
capture_agent_command python3 /random_clicker.py
if [ "$AGENT_EXIT_CODE" -eq 0 ]; then
  echo "agent_exited" > /data/.stop-reason
else
  echo "agent_failed" > /data/.stop-reason
fi
exit 0
