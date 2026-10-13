# Reproduce published results

[← ClawBench](../README.md) · [中文](reproduce.zh-CN.md)

## <img src="../assets/icons/check-double.svg" width="20" height="20"> Reproduce the leaderboard

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

## <img src="../assets/icons/bolt.svg" width="20" height="20"> ClawBench-Lite

**New here? Run this first.** [`test-cases/v1-lite/`](../test-cases/v1-lite) is a **20-task curated subset** of V1, selected for household-name sites, real-world relevance, difficulty, and category diversity. It matches the 20-tasks-per-source convention of [browser-use/benchmark](https://github.com/browser-use/benchmark) and gives you a credible signal at a fraction of the full-benchmark cost.

Tier distribution: **flagship 9 / core 8 / wildcard 3** — spanning daily life (OpenTable, DoorDash, Instacart, TaskRabbit), entertainment (Eventbrite, Goodreads, Fandango), creation (Asana, Mailchimp, Squarespace), travel (Airbnb), education (LeetCode), dev-tech (GitHub), academia (Overleaf), personal management (1Password), and more. All Lite tasks are judged by [`eval/agentic_eval.md`](../eval/agentic_eval.md) regardless of `url_pattern` shape.

Run it with `--cases-suite v1-lite`, or inspect the link-backed task files in [`test-cases/v1-lite/`](../test-cases/v1-lite).
