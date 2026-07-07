#!/bin/bash
#
# Build the combined ClawBench+harness image for Polar RL rollouts.
# Requires the Harbor runtime image (clawbench-harbor) to exist first.
#
set -euo pipefail

TAG="${1:-clawbench-prorl:latest}"
HERE="$(cd "$(dirname "$0")" && pwd)"
# Context is src/clawbench so the build can COPY from both runtime/ and prorl/.
CONTEXT="$(cd "${HERE}/.." && pwd)"
RUNTIME_ROOT="${CONTEXT}/runtime"

if ! docker image inspect clawbench-harbor >/dev/null 2>&1; then
  echo "ERROR: base image 'clawbench-harbor' not found." >&2
  echo "Build it first, e.g.:" >&2
  echo "  docker build -t clawbench-harbor -f ${RUNTIME_ROOT}/harbor/Dockerfile ${RUNTIME_ROOT}" >&2
  exit 1
fi

echo "Building ${TAG} (context: ${CONTEXT})"
docker build -t "${TAG}" -f "${HERE}/Dockerfile.prorl" "${CONTEXT}"
echo "Built ${TAG}"
