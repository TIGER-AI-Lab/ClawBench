#!/bin/bash
# Run GLM-5.1 with non-hermes harnesses, both v1 and codex/v2.
# Runs serially, after both required images are built.
set -u

ROOT=/home/nick/work/ClawBench
LOGS=$ROOT/claw-output/_logs
SWEEP=$ROOT/claw-output/sweep
MASTER=$LOGS/glm-extra-master.log
mkdir -p "$LOGS" "$SWEEP"

cd "$ROOT" || exit 2
export PATH="$HOME/.local/bin:$PATH"

ts() { date -Iseconds; }
log() { echo "[$(ts)] $*" | tee -a "$MASTER"; }

# Wait until both images exist (build runs in parallel, may finish at different times)
log "Waiting for clawbench-codex and clawbench-openclaw images..."
until podman images --format "{{.Repository}}" | grep -q "^localhost/clawbench-codex$"; do sleep 30; done
log "  codex image ready"
until podman images --format "{{.Repository}}" | grep -q "^localhost/clawbench-openclaw$"; do sleep 30; done
log "  openclaw image ready"

run_batch() {
  local label=$1 ; shift
  local out=$SWEEP/$label
  if [ -f "$out/.done" ]; then
    log "SKIP $label (already done)"; return
  fi
  mkdir -p "$out"
  log "START $label → $out"
  uv run --project . clawbench-batch \
      "$@" \
      --models glm-5.1 \
      --max-concurrent 2 --stagger-delay 25 \
      --output-dir "$out" \
      --no-upload \
      > "$out/batch.log" 2>&1
  rc=$?
  log "DONE  $label  exit=$rc"
  touch "$out/.done"
}

# Three batches, sequential to keep memory pressure reasonable.
run_batch glm-5.1__codex__v1 \
    --cases-suite v1 --all-cases --harness codex
run_batch glm-5.1__codex__v2 \
    --cases-suite v2 --all-cases --harness codex
run_batch glm-5.1__openclaw__v1 \
    --cases-suite v1 --all-cases --harness openclaw

log "ALL GLM-EXTRA BATCHES DONE"
