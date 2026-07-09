# ClawBench on EdgeBench (SForge)

This packages ClawBench V2 tasks so they can be run through ByteDance Seed's
[EdgeBench](https://github.com/ByteDance-Seed/EdgeBench) harness, **SForge**.

## The mapping (Mapping A — "structured_json score task")

EdgeBench is a two-container harness: an agent runs in a **Work** container and
submits an archive to a **Judge** container that grades it offline. It targets
long-horizon iterative *code* agents; ClawBench is a short one-shot *browser*
task. We bridge the gap without editing SForge source:

| SForge piece | ClawBench mapping |
|---|---|
| Work container | ClawBench browser runtime + harness + interceptor |
| submitted archive (`submit_paths`) | `evidence/` — the interceptor writes `evidence/interception.json` |
| Judge `eval_cmd` | **`clawbench-edgebench-judge`** — re-scores the evidence (Stage-1 interception ∧ Stage-2 LLM judge) → `structured_json` |
| `parser` | `structured_json` (built-in; no SForge source edit) |
| best-of-N submissions | one-shot: `--max-submissions 1`, machinery disabled |

ClawBench's `verify.py` already scores a *captured* `interception.json`, so
moving interception to the Work side (into `evidence/`) and re-scoring it in the
Judge is a natural fit — EdgeBench's judge is offline/archive-only by design.

## Generate the benchmark

```
clawbench-edgebench-adapt --output-dir ./clawbench-edgebench \
    --base-image clawbench-prorl-openclaw:latest
```
Produces a SForge benchmark dir: `tasks/BENCHMARK.yaml` + `tasks/<id>.json`
(+ per-task `specs/`). Each `<id>.json` is Mapping A:
`base_image: browser`, `submit_paths: ["evidence/"]`,
`judge.parser: structured_json`, `judge.eval_cmd: clawbench-edgebench-judge …`,
`score_direction: maximize`, `selection: score_first`.

## Run it

```
# LLM-judge key reaches the Judge container via SFORGE_JUDGE_EXTRA_ENV
export SFORGE_JUDGE_EXTRA_ENV="CLAWBENCH_JUDGE_MODEL=glm-5.1,\
CLAWBENCH_JUDGE_BASE_URL=https://api.z.ai/api/paas/v4,CLAWBENCH_JUDGE_API_KEY=…,\
CLAWBENCH_JUDGE_API_TYPE=openai-completions"
export SFORGE_AGENT_API_KEY=…  SFORGE_AGENT_API_BASE_URL=…  SFORGE_AGENT_MODEL=…

sforge serve --port 8080
sforge run --task <id> --agent <browser-agent> \
    --max-submissions 1 --disable-auto-eval --disable-stop-hook --timeout 900
```

The judge prints, and SForge parses:
```
>>>>> Start Structured Result
{"valid":true,"score":1.0,"summary":"…","details":[…],"metrics":{"intercepted":true}}
>>>>> End Structured Result
```

## What ClawBench supplies vs SForge

ClawBench supplies only the **Judge `eval_cmd`** (`clawbench-edgebench-judge`,
fully unit-tested offline) + the **task definitions** (`clawbench-edgebench-adapt`).
SForge provides the Judge HTTP API, `sforge-submit`, tokens/rounds/best-score,
image build/hashing.

## Not covered here (the two open ends)

1. **A browser Agent for SForge.** SForge's built-in agents (`claude-code`,
   `codex`) are code CLIs. Running a *browser* episode needs either a small
   `Agent` subclass under `sforge/harness/agent/` (one file + one factory line —
   an edit to the EdgeBench repo, or an upstream contribution) or a Work-image
   entrypoint that drives the ClawBench harness and then calls `sforge-submit`.
2. **Container build + a live `sforge run`.** The adapter emits contract-faithful
   task JSON (schema-tested) and the judge is unit-tested offline, but building
   the Work/Judge images and a live end-to-end `sforge run` require Docker + the
   EdgeBench harness on a build box — analogous to how the ProRL image was
   validated separately from its offline contract tests.
