#!/usr/bin/env bash
# Thin wrapper around the clawbench-rescore CLI.
#
# Default usage (lenient rubric, ds-v4-pro judge, eval_results/ output):
#   scripts/rescore.sh <batch_dir>
#
# Use --rubric both to also write the strict-rubric judge:
#   scripts/rescore.sh <batch_dir> --rubric both
#
# All flags pass through to the underlying CLI; see --help for the full list.
set -euo pipefail
exec uv run --project "$(dirname "$0")/.." python -m clawbench.eval.rescore "$@"
