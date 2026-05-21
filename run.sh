#!/bin/bash
cd "$(dirname "$0")" || exit
export PYTHONPATH="$PWD/src${PYTHONPATH:+:$PYTHONPATH}"
exec uv run clawbench
