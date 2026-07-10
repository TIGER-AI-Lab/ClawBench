#!/bin/bash
set -e
#
# Null baseline harness — the benchmark FLOOR.
#
# It connects to nothing and takes no browser action, so the run records zero
# actions/requests and the interceptor never fires. A do-nothing agent must
# therefore score ~0: this proves ClawBench is not luck-passable and that the
# HTTP interceptor has no false positives without genuine agent activity.
#
/setup-null.sh

mkdir -p /data
# a well-formed (empty) transcript so the run is complete, not "missing files"
: > /data/agent-messages.jsonl

echo "null baseline agent: taking no action for this task"
# exit cleanly — the runtime stops and writes interception.json (intercepted=false)
exit 0
