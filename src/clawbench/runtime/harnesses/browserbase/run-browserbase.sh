#!/usr/bin/env bash
set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

if [ -z "$BROWSERBASE_API_KEY" ]; then
    echo "Error: BROWSERBASE_API_KEY environment variable is not set" >&2
    exit 1
fi

if [ -z "$BROWSERBASE_PROJECT_ID" ]; then
    echo "Error: BROWSERBASE_PROJECT_ID environment variable is not set" >&2
    exit 1
fi

if [ $# -lt 1 ]; then
    echo "Usage: $0 <task_file>" >&2
    exit 1
fi

TASK_FILE="$1"

python "$SCRIPT_DIR/agent.py" "$TASK_FILE"
