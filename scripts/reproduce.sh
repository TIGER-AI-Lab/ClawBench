#!/usr/bin/env bash
# Thin wrapper around the clawbench-reproduce CLI.
#
# Downloads a model's V2 trace subset from TIGER-Lab/ClawBenchV2Trace,
# re-judges with deepseek-v4-pro under both rubrics, and diffs vs the
# published leaderboard row.
#
#   scripts/reproduce.sh --model deepseek-v4-flash
#   scripts/reproduce.sh --model claude-opus-4-7 --tolerance 1.5
#
# All flags pass through; see --help for the full list.
set -euo pipefail
exec uv run --project "$(dirname "$0")/.." python -m clawbench.eval.reproduce "$@"
