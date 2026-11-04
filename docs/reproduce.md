# Reproduce the leaderboard

> **Our scores are stable**: two independent runs of the same model under the same judge (`deepseek/deepseek-v4-pro`, lenient rubric) reproduce Intercepted and Reward within ±2 pp on the V2 corpus.

There are **two ways** to verify this on your own machine.

### Path A — Re-run the agent, then score

Confirms the *full pipeline* (your agent + our judge) lines up with our leaderboard row.

```bash
clawbench-batch --models deepseek/deepseek-v4-flash --cases-suite v2 \
  --all-cases --harness hermes --no-judge --output-dir ./my-run
clawbench-rescore ./my-run --judge-model deepseek-v4-pro --rubric both
```

### Path B — Skip the run, re-judge our published traces

Confirms *just the judge* matches ours (cheap, no agent compute, useful for sanity-checking your judge config).

```bash
hf download --repo-type dataset TIGER-Lab/ClawBenchV2Trace \
  --include "batch-aligned-*/deepseek-v4-flash-free/**" --local-dir ./reproduce
clawbench-rescore ./reproduce --judge-model deepseek-v4-pro --rubric both
```

One-shot equivalent of Path B for any model in the leaderboard:

```bash
clawbench-reproduce --model deepseek-v4-flash --tolerance 2.0
```

### Pass criterion

For `deepseek-v4-flash:free × hermes × v2`, the published row is **Intercepted 3.1% / Reward-lenient 2.3% / Reward-strict 0.0% (3 / 129)**. Path A or B counts as **reproduced** when all three metrics land within ±2 pp. Larger gaps usually mean a different judge model, a different rubric prompt, or a harness configuration drift — diff your `eval_results/<batch>/summary.json` against the published row to localize the cause.
