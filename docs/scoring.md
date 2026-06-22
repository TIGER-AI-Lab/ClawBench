# ClawBench — Scoring Logic

This document specifies how a ClawBench run is scored. It is the canonical reference for the numbers shown on:

- **Live leaderboard:** https://huggingface.co/spaces/TIGER-Lab/ClawBench
- **Website snapshot:** https://claw-bench.com/leaderboard
- **Current HF leaderboard CSV:** https://huggingface.co/datasets/TIGER-Lab/ClawBench/blob/main/leaderboard/results.csv

Anyone can reproduce every number on the leaderboard from the public traces in [`NAIL-Group/ClawBenchV1Trace`](https://huggingface.co/datasets/NAIL-Group/ClawBenchV1Trace) and [`TIGER-Lab/ClawBenchV2Trace`](https://huggingface.co/datasets/TIGER-Lab/ClawBenchV2Trace) by running `scripts/clawbench_rescore.py` (see [Reproducibility](#reproducibility) below).

## Summary

Scoring is two stages applied in order. Each stage produces a boolean per (task × run).

```
                ┌──────────────┐         ┌──────────────┐
agent run ───►  │ Interception │ ──true─►│  LLM judge   │ ──true─► reward = 1
                └──────────────┘         └──────────────┘
                       │ false                  │ false
                       └─► reward = 0  ◄────────┘
```

Aggregate metrics (per model × corpus):

```text
intercepted_rate = sum(intercepted) / N
reward_rate      = sum(intercepted ∧ judge_match) / N
```

`N` = number of tasks in the corpus (V1: 153, V2: 130).

## Stage 1 — Final-request interception

A **request interceptor** runs inside the sandbox container. It blocks the *final* outgoing HTTP request whose URL and method match the task's `eval_schema`. The intent is to capture the agent's commit-intent (checkout, form submit, post, etc.) **before** it actually hits the live website — both for evaluation and for safety.

Per-task interceptor config lives in `test-cases/<corpus>/<slug>/task.json`:

```jsonc
{
  "eval_schema": {
    "url_pattern": "myrecipes\\.com/api/v\\d+/review/save",
    "method": "POST"
  }
}
```

A run is **intercepted** iff the agent's final outgoing request matched the URL regex *and* the HTTP method. The result lives in `data/interception.json`:

```jsonc
{
  "intercepted": true,
  "url": "https://www.myrecipes.com/api/v2/review/save",
  "method": "POST",
  "body": {"rating": 4, "tip": "Add a pinch of salt for balance.", "recipe_id": 12345}
}
```

If `intercepted: false`, **reward = 0** for that task regardless of how close the agent got. Common reasons:

- agent timed out (`time_limit_exceeded` in `run-meta.json`)
- agent gave up before reaching the terminal step
- agent reached a different endpoint than the rubric expects (alternate-flow miss)
- agent hit a CAPTCHA / login / verification wall and could not solve it

Note that **Stage 1 alone is too lenient** — an agent that intercepts but submits the wrong payload would pass. Stage 2 closes that gap.

## Stage 2 — LLM judge

For every run where `intercepted: true`, an LLM judge reviews the intercepted body against the natural-language instruction. The judge returns one of:

- `match: true` — body satisfies the instruction
- `match: false` — body does not satisfy
- `match: null` — judge could not decide (rare; treated as `false` in aggregate)

The judge is configured per run; default is `deepseek-v4-pro` at temperature 0. Output lives in `data/judge.json`:

```jsonc
{
  "match": true,
  "reason": "The POST body submits rating=4 with a non-trivial tip mentioning 'add a pinch of salt', which fulfills the instruction to rate 4 stars and add a helpful tip.",
  "judge_model": "deepseek-v4-pro",
  "raw": "<full JSON response from the model>",
  "error": null
}
```

### Judge prompt (verbatim)

The judge sees the task instruction and the intercepted body (truncated to 4 KB for headers + body), and is asked to return strict JSON with `match` (bool) and `reason` (≤ 300 chars). The exact prompt is in [`src/clawbench/runner/judge.py`](../src/clawbench/runner/judge.py) — search for `SYSTEM_PROMPT`.

System prompt sketch:

> You are evaluating whether an AI agent's final HTTP request fulfills a natural-language instruction. You will be given the instruction and the request body. Return strict JSON `{"match": boolean, "reason": "≤ 300 chars"}`. Be strict: a body that matches on form but not on the user's intent should be `match: false`.

User message contains the `instruction` and a compact JSON dump of `(url, method, body)`. Headers are stripped of authentication. Payload is truncated past 4 KB.

### Final score

```python
final_pass = intercepted AND (judge_match is True)
```

Per-run record in `run-meta.json` gets:

```jsonc
{
  "intercepted": true,
  "judge_match": true,
  "final_pass": true,
  "result_category": "passed"
}
```

## Why two stages

| Stage | What it catches | What it misses |
|---|---|---|
| Interception only | "agent reached the right endpoint" | wrong payload submitted |
| Judge only (no interception gate) | "agent's reasoning was right" | agent never actually completed the action |
| **Both** | **end-to-end task completion with correct payload** | very edge-case: agent intercepts a syntactically-equivalent endpoint not in the regex |

Empirically, requiring both moves headline scores down sharply (typical Stage-1-only is 1.5–2× Stage-2 numbers), surfacing models that "almost get there" vs. models that actually complete the task. The two-stage system also makes failure diagnosis cheap — the run-meta tells you which stage cut off.

## Aggregating to a leaderboard row

Each (model × harness × corpus) batch produces one `rescore-summary.json`:

```jsonc
{
  "batch_dir": "/path/to/batch",
  "n_total": 130,
  "n_intercepted": 63,
  "n_judge_match": 24,
  "n_judge_mismatch": 34,
  "n_judge_error": 5,
  "pass_rate_stage1_only": 0.4846,
  "pass_rate_with_judge":  0.1846,
  "tasks": [ ... per-task records ... ]
}
```

The leaderboard row is one row per batch, with columns from the script's output:

```csv
model,harness,dataset,passed,total,pass_rate,wall_hours
glm-5.1,hermes,v2,24,130,18.46,11.35
```

### Leaderboard provenance

The current public leaderboard rows are published from
[`TIGER-Lab/ClawBench`](https://huggingface.co/datasets/TIGER-Lab/ClawBench)
at `leaderboard/results.csv`. Older mirrors or data-card tables can lag behind
that CSV, so use the TIGER-Lab dataset as the canonical source for the latest
rows.

For V2 rows, the backing traces live in
[`TIGER-Lab/ClawBenchV2Trace`](https://huggingface.co/datasets/TIGER-Lab/ClawBenchV2Trace).
Each row should be traceable to a model/harness batch directory and its
`rescore-summary*.json` output. When checking or updating a row, record:

- leaderboard CSV row (`model`, `harness`, `dataset`, `passed`, `total`)
- trace dataset and batch prefix
- `rescore-summary*.json` path used for the row
- judge/rubric variant, such as lenient vs. strict
- verification date

## Reproducibility

To re-grade an existing trace bundle (no agent re-run required):

```bash
# 1. install the package
pip install clawbench-eval

# 2. download the trace bundle for the model you want to re-score
hf download --repo-type dataset TIGER-Lab/ClawBenchV2Trace \
  --include "*-claude-sonnet-4-6-*" \
  --local-dir ./v2-traces

# 3. set your judge model's API key in env
export DEEPSEEK_API_KEY=sk-...

# 4. (one-time) add the judge model to models.yaml — see docs/models.md

# 5. rescore
python scripts/clawbench_rescore.py \
  --judge-model deepseek-v4-pro \
  --only-batch ./v2-traces \
  --force        # re-judge existing judge.json files
```

Output: per-run `judge.json` updated in place, plus a fresh `rescore-summary.json` at the batch root.

## Common questions

- **Why DeepSeek instead of Claude / GPT?** Open weights (closer to reproducible) and substantially cheaper for what we need. Swap with `--judge-model <other>` if you want — see `docs/models.md` for setting one up.
- **Does the judge see the screenshot?** No, by design. The judge sees the intercepted HTTP request + instruction only. Visual judgment lives in a separate (out-of-scope, future) stage.
- **What if interception fires before the agent has finished?** The interceptor only fires on requests matching `eval_schema.url_pattern` *and* `method`. Setting this regex correctly is a per-task curation responsibility; mistakes are caught in human review (see `docs/contributing/adding-a-task.md`).
- **Why is `n_judge_error > 0`?** Network blips, rate limits, the judge returning non-JSON. In aggregate we treat these as `match: false` (no credit). Persistent errors flag a config bug.
- **Where does the `33.3%` headline number come from?** Sonnet 4.6 on V1: `n_intercepted=51, n_judge_match=51, n_total=153`. Stage 1 + Stage 2 collapse onto the same number because Sonnet's intercepted payloads almost always match the instruction on V1.

## See also

- [`src/clawbench/runner/judge.py`](../src/clawbench/runner/judge.py) — the judge implementation (~250 lines).
- [`scripts/clawbench_rescore.py`](../scripts/clawbench_rescore.py) — the rescoring CLI.
- [`test-cases/task.schema.json`](../test-cases/task.schema.json) — `eval_schema` field definition.
- [Trace dataset (V1)](https://huggingface.co/datasets/NAIL-Group/ClawBenchV1Trace) — every layer of every V1 run.
- [Trace dataset (V2)](https://huggingface.co/datasets/TIGER-Lab/ClawBenchV2Trace) — V2 traces (rolling, as new models are evaluated).
