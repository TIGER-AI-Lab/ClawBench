#!/bin/bash
# Low-priority openclaw queue. Runs serially with max-concurrent 1.
# Auto-aborts (10 done, 0 pass, <10 min) on dead/rate-limited models.
set -u
export PATH="$HOME/.local/bin:$PATH"
ROOT=/home/nick/work/ClawBench
LOGS=$ROOT/claw-output/_logs
SWEEP=$ROOT/claw-output/sweep
MASTER=$LOGS/sweep-openclaw-master.log
mkdir -p "$LOGS" "$SWEEP"
cd "$ROOT" || exit 2

# Skip glm-5.1 v1 (done) and glm-5.1 v2 (running)
EXPS=(
  "openrouter/owl-alpha:v1"
  "openrouter/owl-alpha:v2"
  "deepseek-v4-pro:v1"
  "deepseek-v4-pro:v2"
  "deepseek/deepseek-v4-flash:v1"
  "deepseek/deepseek-v4-flash:v2"
  "poolside/laguna-m.1:free:v1"
  "poolside/laguna-m.1:free:v2"
)

ts() { date -Iseconds; }
log() { echo "[$(ts)] $*" | tee -a "$MASTER"; }

watch_and_maybe_abort() {
  local lg=$1; local pid=$2; local model=$3
  while ps -p $pid > /dev/null 2>&1; do
    sleep 30
    [ -f "$lg" ] || continue
    last=$(grep -oE "BATCH\] [0-9]+/[0-9]+ done.*[0-9]+m[0-9]+s elapsed" "$lg" | tail -1)
    [ -z "$last" ] && continue
    d=$(echo "$last" | grep -oE "BATCH\] [0-9]+" | grep -oE "[0-9]+")
    p=$(echo "$last" | grep -oE "[0-9]+ passed" | grep -oE "[0-9]+")
    e=$(echo "$last" | grep -oE "[0-9]+m[0-9]+s elapsed" | grep -oE "^[0-9]+")
    if [ "${d:-0}" -ge 10 ] && [ "${p:-0}" -eq 0 ] && [ "${e:-99}" -lt 10 ]; then
      log "ABORT: $d done, 0 pass, ${e}m -> dead/rate-limit"
      kill $pid 2>/dev/null; sleep 3; ps -p $pid > /dev/null 2>&1 && kill -KILL $pid
      pgrep -f "clawbench-batch.*$model" 2>&1 | xargs -r kill -KILL 2>/dev/null
      podman ps --format "{{.Names}}" | grep openclaw | xargs -r podman rm -f 2>&1
      return 1
    fi
  done
  return 0
}

for exp in "${EXPS[@]}"; do
  # split last :vN suffix
  ds="${exp##*:}"
  model="${exp%:*}"
  safe=$(echo "$model" | tr "/:" "__")
  out="$SWEEP/${safe}__openclaw__${ds}"
  if [ -f "$out/.done" ]; then
    log "SKIP $model x openclaw x $ds (already done)"
    continue
  fi
  mkdir -p "$out"
  log "START $model x openclaw x $ds -> $out"
  uv run --project . clawbench-batch \
      --cases-suite "$ds" --all-cases \
      --harness openclaw \
      --models "$model" \
      --max-concurrent 1 --stagger-delay 30 \
      --output-dir "$out" \
      --no-upload \
      > "$out/batch.log" 2>&1 &
  bp=$!
  if watch_and_maybe_abort "$out/batch.log" $bp "$model"; then
    wait $bp 2>/dev/null
    log "DONE  $model x openclaw x $ds  exit=$?"
  else
    log "ABORTED $model x openclaw x $ds"
  fi
  touch "$out/.done"
done
log "ALL OPENCLAW QUEUE DONE"
