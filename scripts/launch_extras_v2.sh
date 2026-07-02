#!/bin/bash
set -u
export PATH="$HOME/.local/bin:$PATH"
ROOT=/home/nick/work/ClawBench
SWEEP=$ROOT/claw-output/sweep
LOGS=$ROOT/claw-output/_logs
MASTER=$LOGS/sweep-extras-v2-master.log
mkdir -p "$LOGS" "$SWEEP"
cd "$ROOT" || exit 2

MODELS=(
  "google/gemma-4-26b-a4b-it:free"
  "nvidia/nemotron-nano-12b-v2-vl:free"
  "nvidia/nemotron-nano-9b-v2:free"
)
DATASETS=("v1" "v2")

ts() { date -Iseconds; }
log() { echo "[$(ts)] $*" | tee -a "$MASTER"; }

watch_and_maybe_abort() {
  local lg=$1; local pid=$2; local model=$3
  while ps -p $pid > /dev/null 2>&1; do
    sleep 30
    [ -f "$lg" ] || continue
    local last
    last=$(grep -oE "BATCH\] [0-9]+/[0-9]+ done.*[0-9]+m[0-9]+s elapsed" "$lg" | tail -1)
    [ -z "$last" ] && continue
    local d p e
    d=$(echo "$last" | grep -oE "BATCH\] [0-9]+" | grep -oE "[0-9]+")
    p=$(echo "$last" | grep -oE "[0-9]+ passed" | grep -oE "[0-9]+")
    e=$(echo "$last" | grep -oE "[0-9]+m[0-9]+s elapsed" | grep -oE "^[0-9]+")
    if [ "${d:-0}" -ge 10 ] && [ "${p:-0}" -eq 0 ] && [ "${e:-99}" -lt 10 ]; then
      log "ABORT: $d done, 0 pass, ${e}m -> dead/rate-limit"
      kill $pid 2>/dev/null; sleep 3; ps -p $pid > /dev/null 2>&1 && kill -KILL $pid
      pgrep -f "clawbench-batch.*$model" 2>&1 | xargs -r kill -KILL 2>/dev/null
      return 1
    fi
  done
  return 0
}

for model in "${MODELS[@]}"; do
  safe=$(echo "$model" | tr "/:" "__")
  for ds in "${DATASETS[@]}"; do
    out="$SWEEP/$safe/$ds"
    if [ -f "$out/.done" ]; then
      log "SKIP $model x $ds"; continue
    fi
    mkdir -p "$out"
    log "START $model x $ds"
    uv run --project . clawbench-batch \
        --cases-suite "$ds" --all-cases \
        --harness hermes \
        --models "$model" \
        --max-concurrent 1 --stagger-delay 25 \
        --output-dir "$out" \
        --no-upload \
        > "$out/batch.log" 2>&1 &
    bp=$!
    if watch_and_maybe_abort "$out/batch.log" $bp "$model"; then
      wait $bp 2>/dev/null
      log "DONE  $model x $ds  exit=$?"
    else
      log "ABORTED $model x $ds"
    fi
    touch "$out/.done"
  done
done
log "ALL EXTRAS V2 DONE"
