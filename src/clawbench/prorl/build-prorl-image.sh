#!/bin/bash
#
# Build the combined ClawBench+harness image for Polar RL rollouts.
# Requires the Harbor runtime image (clawbench-harbor) to exist first.
#
set -euo pipefail

TAG="${1:-clawbench-prorl:latest}"
HERE="$(cd "$(dirname "$0")" && pwd)"
RUNTIME_ROOT="$(cd "${HERE}/.." && pwd)/runtime"

if ! docker image inspect clawbench-harbor >/dev/null 2>&1; then
  echo "ERROR: base image 'clawbench-harbor' not found." >&2
  echo "Build it first, e.g.:" >&2
  echo "  docker build -t clawbench-harbor -f ${RUNTIME_ROOT}/harbor/Dockerfile ${RUNTIME_ROOT}" >&2
  exit 1
fi

echo "Building ${TAG} (context: ${RUNTIME_ROOT})"
docker build -t "${TAG}" -f "${HERE}/Dockerfile.prorl" "${RUNTIME_ROOT}"
echo "Built ${TAG}"
