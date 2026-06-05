#!/usr/bin/env bash
# Build the clawbench-harbor-task services-mode image (Harbor-as-runner).
#
# This stages a build context that contains the repo's runtime/ tree plus a copy
# of the clawbench Python source (as clawbench-src/) and a minimal pyproject, so
# the Dockerfile can `uv pip install` the package for the in-container verifier.
#
# Prereq: the clawbench-harbor and clawbench-base images already exist (build via
#   clawbench-run <case> <model> --harness harbor   or   docker build the base).
#
# Usage: build-harbor-task.sh [IMAGE_TAG]
set -euo pipefail

ENGINE="${CONTAINER_ENGINE:-}"
if [ -z "$ENGINE" ]; then
  if command -v podman >/dev/null 2>&1; then ENGINE=podman
  elif command -v docker >/dev/null 2>&1; then ENGINE=docker
  else echo "ERROR: neither podman nor docker found" >&2; exit 1; fi
fi

IMAGE_TAG="${1:-clawbench-harbor-task}"

# Resolve repo paths relative to this script: .../src/clawbench/runtime/harnesses/harbor-task
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
RUNTIME_DIR="$(cd "$HERE/../.." && pwd)"          # .../src/clawbench/runtime
CLAWBENCH_PKG="$(cd "$RUNTIME_DIR/.." && pwd)"    # .../src/clawbench
SRC_DIR="$(cd "$CLAWBENCH_PKG/.." && pwd)"        # .../src

CTX="$(mktemp -d)"
trap 'rm -rf "$CTX"' EXIT

# runtime/ tree (Dockerfile references harnesses/harbor-task/Dockerfile.harbor-task)
cp -r "$RUNTIME_DIR/." "$CTX/"

# clawbench source as an installable package under clawbench-src/
mkdir -p "$CTX/clawbench-src/src"
cp -r "$CLAWBENCH_PKG" "$CTX/clawbench-src/src/clawbench"
# Drop the heavy runtime tree from the staged copy: the verifier only needs the
# pure-Python scoring + harbor modules, and runtime/ is already in the image.
rm -rf "$CTX/clawbench-src/src/clawbench/runtime"
cat > "$CTX/clawbench-src/pyproject.toml" <<'TOML'
[build-system]
requires = ["hatchling>=1.27"]
build-backend = "hatchling.build"

[project]
name = "clawbench-eval"
version = "0.0.0+harbor-task"
description = "ClawBench scoring modules baked into the Harbor task image"
requires-python = ">=3.9"

[tool.hatch.build.targets.wheel]
packages = ["src/clawbench"]
TOML

echo "Building $IMAGE_TAG (engine=$ENGINE, context=$CTX)..."
"$ENGINE" build \
  -f "$CTX/harnesses/harbor-task/Dockerfile.harbor-task" \
  -t "$IMAGE_TAG" \
  "$CTX"
echo "Built $IMAGE_TAG"
