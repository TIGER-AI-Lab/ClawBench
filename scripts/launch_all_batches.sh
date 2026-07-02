#!/bin/bash
# Sequential queue: 13 models × 2 datasets (v1, v2) = 26 batches.
# Auto-abort: 10 done + 0 pass + <10 min → rate-limit/dead, skip.
set -u

ROOT=/home/nick/work/ClawBench
LOGS=$ROOT/claw-output/_logs
SWEEP=$ROOT/claw-output/sweep
MASTER=$LOGS/sweep-master.log
mkdir -p "$LOGS" "$SWEEP"

cd "$ROOT" || exit 2
export PATH="$HOME/.local/bin:$PATH"

MODELS=(
  "glm-5.1"
  "deepseek/deepseek-v4-flash"
  "openrouter/owl-alpha"
  "openai/gpt-oss-120b:free"
  "minimax/minimax-m2.5:free"
  "nvidia/nemotron-3-super-120b-a12b:free"
  "inclusionai/ring-2.6-1t:free"
  "tencent/hy3-preview:free"
  "nvidia/nemotron-3-nano-omni-30b-a3b-reasoning:free"
  "poolside/laguna-m.1:free"
  "poolside/laguna-xs.2:free"
  "liquid/lfm-2.5-1.2b-thinking:free"
  "baidu/cobuddy:free"
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
  local log_file=$1
  local batch_pid=$2
  local model=$3
  while ps -p $batch_pid > /dev/null 2>&1; do
    sleep 30
    [ -f "$log_file" ] || continue
    local last
    last=$(grep -oE "BATCH\] [0-9]+/[0-9]+ done.*[0-9]+m[0-9]+s elapsed" "$log_file" | tail -1)
    [ -z "$last" ] && continue
    local done_n pass_n elapsed_min
    done_n=$(echo "$last" | grep -oE "BATCH\] [0-9]+" | grep -oE "[0-9]+")
    pass_n=$(echo "$last" | grep -oE "[0-9]+ passed" | grep -oE "[0-9]+")
    elapsed_min=$(echo "$last" | grep -oE "[0-9]+m[0-9]+s elapsed" | grep -oE "^[0-9]+")
    if [ "${done_n:-0}" -ge 10 ] && [ "${pass_n:-0}" -eq 0 ] && [ "${elapsed_min:-99}" -lt 10 ]; then
      log "ABORT: 10 done, 0 pass, ${elapsed_min}m elapsed → rate-limit/dead model"
      kill $batch_pid 2>/dev/null
      sleep 3
      ps -p $batch_pid > /dev/null 2>&1 && kill -KILL $batch_pid
      pgrep -f "clawbench-batch.*$model" 2>&1 | xargs -r kill -KILL 2>/dev/null
      podman ps --format '{{.Names}}' | grep '^clawbench-' | xargs -r podman rm -f > /dev/null 2>&1
      return 1
    fi
  done
  return 0
}

for model in "${MODELS[@]}"; do
  safe=$(echo "$model" | tr '/:' '__')
  for ds in "${DATASETS[@]}"; do
    out="$SWEEP/$safe/$ds"
    if [ -f "$out/.done" ]; then
      log "SKIP $model × $ds (already done)"
      continue
    fi
    mkdir -p "$out"
    log "START $model × $ds → $out"
    uv run --project . clawbench-batch \
        --cases-suite "$ds" --all-cases \
        --harness hermes \
        --models "$model" \
        --max-concurrent 2 --stagger-delay 25 \
        --output-dir "$out" \
        --no-upload \
        > "$out/batch.log" 2>&1 &
    batch_pid=$!
    if watch_and_maybe_abort "$out/batch.log" $batch_pid "$model"; then
      wait $batch_pid 2>/dev/null
      rc=$?
      log "DONE  $model × $ds  exit=$rc"
    else
      log "ABORTED $model × $ds (rate-limit detected)"
    fi
    touch "$out/.done"
  done
done

log "ALL BATCHES DONE"
