#!/bin/bash
set -e
#
# Random-click baseline — a NON-TRIVIAL floor: it clicks at random but with no
# task intent, so it should still score ~0. Shows that browsing activity alone
# (without hitting the target action) does not pass the interceptor.
#
/setup-random-click.sh
mkdir -p /data
: > /data/agent-messages.jsonl
python3 /random_clicker.py || true
exit 0
