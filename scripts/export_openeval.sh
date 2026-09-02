#!/usr/bin/env bash
# Thin wrapper around scripts/export_openeval.py.
#
# Usage:
#   scripts/export_openeval.sh <batch_dir> --run-id <id> --started-at <iso8601>
#
# Writes <batch_dir>/resultset.json by default (a spec-valid EvalPort
# ResultSet, see https://github.com/adhabnr-ux/evalport). All flags pass
# through to the underlying script; see --help for the full list.
set -euo pipefail
exec uv run --project "$(dirname "$0")/.." python "$(dirname "$0")/export_openeval.py" "$@"
