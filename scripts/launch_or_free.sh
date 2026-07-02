#!/bin/bash
set -u
export PATH="$HOME/.local/bin:$PATH"
ROOT=/home/nick/work/ClawBench
SWEEP=$ROOT/claw-output/sweep
LOG=$ROOT/claw-output/_logs/launch-or-free.log
cd "$ROOT" || exit 2

ts() { date -Iseconds; }

for ds in v1 v2; do
  out="$SWEEP/openrouter_free/$ds"
  if [ -f "$out/.done" ]; then
    echo "[$(ts)] SKIP openrouter/free x $ds" | tee -a "$LOG"
    continue
  fi
  mkdir -p "$out"
  echo "[$(ts)] START openrouter/free x $ds" | tee -a "$LOG"
  uv run --project . clawbench-batch \
      --cases-suite "$ds" --all-cases \
      --harness hermes \
      --models openrouter/free \
      --max-concurrent 1 --stagger-delay 25 \
      --output-dir "$out" \
      --no-upload \
      > "$out/batch.log" 2>&1
  rc=$?
  echo "[$(ts)] DONE openrouter/free x $ds exit=$rc" | tee -a "$LOG"
  touch "$out/.done"
done
echo "[$(ts)] OR-FREE all done" | tee -a "$LOG"
