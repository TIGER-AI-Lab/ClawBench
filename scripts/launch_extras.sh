#!/bin/bash
# Extras: 10 new free models added after main sweep started.
# Runs serially with max-concurrent 1 to be polite to the box (main sweep already uses 2 conc + glm-extra uses 2 conc).
set -u
export PATH="$HOME/.local/bin:$PATH"
ROOT=/home/nick/work/ClawBench
LOGS=$ROOT/claw-output/_logs
SWEEP=$ROOT/claw-output/sweep
MASTER=$LOGS/sweep-extras-master.log
mkdir -p "$LOGS" "$SWEEP"
cd "$ROOT" || exit 2

MODELS=(
  "inclusionai/ring-2.6-1t:free"
  "qwen/qwen3-next-80b-a3b-instruct:free"
  "qwen/qwen3-coder:free"
  "z-ai/glm-4.5-air:free"
  "nvidia/nemotron-3-nano-30b-a3b:free"
  "meta-llama/llama-3.3-70b-instruct:free"
  "google/gemma-4-31b-it:free"
  "openai/gpt-oss-20b:free"
  "nousresearch/hermes-3-llama-3.1-405b:free"
  "cognitivecomputations/dolphin-mistral-24b-venice-edition:free"
)
DATASETS=("v1" "v2")

ts() { date -Iseconds; }
log() { echo "[$(ts)] $*" | tee -a "$MASTER"; }

watch_and_maybe_abort() {
  local log=$1
  local batch_pid=$2
  while ps -p $batch_pid > /dev/null 2>&1; do
    sleep 30
    [ -f "$log" ] || continue
    local last
    last=$(grep -oE "BATCH\] [0-9]+/[0-9]+ done.*[0-9]+m[0-9]+s elapsed" "$log" | tail -1)
    [ -z "$last" ] && continue
    local done_n pass_n elapsed_min
    done_n=$(echo "$last" | grep -oE "BATCH\] [0-9]+" | grep -oE "[0-9]+")
    pass_n=$(echo "$last" | grep -oE "[0-9]+ passed" | grep -oE "[0-9]+")
    elapsed_min=$(echo "$last" | grep -oE "[0-9]+m[0-9]+s elapsed" | grep -oE "^[0-9]+")
    if [ "${done_n:-0}" -ge 10 ] && [ "${pass_n:-0}" -eq 0 ] && [ "${elapsed_min:-99}" -lt 10 ]; then
      log "ABORT: 10 done, 0 pass, ${elapsed_min}m elapsed -> rate-limit/dead model"
      kill $batch_pid 2>/dev/null
      sleep 3
      ps -p $batch_pid > /dev/null 2>&1 && kill -KILL $batch_pid
      pgrep -f "clawbench-batch.*$3" 2>&1 | xargs -r kill -KILL 2>/dev/null
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
      log "SKIP $model x $ds"
      continue
    fi
    mkdir -p "$out"
    log "START $model x $ds -> $out"
    uv run --project . clawbench-batch \
        --cases-suite "$ds" --all-cases \
        --harness hermes \
        --models "$model" \
        --max-concurrent 1 --stagger-delay 25 \
        --output-dir "$out" \
        --no-upload \
        > "$out/batch.log" 2>&1 &
    batch_pid=$!
    if watch_and_maybe_abort "$out/batch.log" $batch_pid "$model"; then
      wait $batch_pid 2>/dev/null
      rc=$?
      log "DONE  $model x $ds  exit=$rc"
    else
      log "ABORTED $model x $ds (rate-limit)"
    fi
    touch "$out/.done"
  done
done
log "ALL EXTRAS DONE"
