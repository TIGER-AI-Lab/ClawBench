# The ClawBench Trace Cookbook

**What you can build on 500+ full recordings of AI agents using the real web.**

Every ClawBench run publishes a synchronized five-layer recording — not just a
score. This document is for researchers who want to *build on* that data:
training signals, process rewards, failure taxonomies, security analyses.
Published works have already used these traces for on-policy distillation
(TurnOPD, arXiv:2607.05804), trace-level evaluation (ClawTrack,
arXiv:2607.28037), and redundant-step detection (RedundancyBench,
arXiv:2605.29893).

## The data

| Dataset | Contents |
| --- | --- |
| [NAIL-Group/ClawBenchV1Trace](https://huggingface.co/datasets/NAIL-Group/ClawBenchV1Trace) | One directory per (model × V1 task) run |
| [TIGER-Lab/ClawBenchV2Trace](https://huggingface.co/datasets/TIGER-Lab/ClawBenchV2Trace) | Same bundle for V2 runs; rolling |

Each run directory contains:

| File | Layer | Typical use |
| --- | --- | --- |
| `agent-messages.jsonl` | Agent transcript (thinking, text, tool calls) | SFT / distillation / process supervision |
| `actions.jsonl` | Every DOM event (click, input, scroll, pageLoad) | Action-level analysis, redundancy detection |
| `requests.jsonl` | Every HTTP request (headers, body, params) | Security auditing, intent verification |
| `screenshots/*.png` | Timestamped PNG per action | Vision grounding, GUI datasets |
| `recording.mp4` | Full session video (H.264, 15 fps) | Qualitative analysis, demos |
| `interception.json` | The final blocked request | Outcome labels (Stage-1) |
| `run-meta.json` | Model, harness, task, timing | Joins and filtering |

Pull a single model or task without downloading everything:

```bash
# All Claude Opus V1 runs, JSONL layers only (no video):
hf download --repo-type dataset NAIL-Group/ClawBenchV1Trace \
  --include "*claude-opus*/**/*.jsonl" --include "*claude-opus*/**/*.json" \
  --local-dir ./traces

# One task across all models:
hf download --repo-type dataset NAIL-Group/ClawBenchV1Trace \
  --include "*001-daily-life-food-uber-eats*/**" --exclude "*.mp4" \
  --local-dir ./traces
```

Load a run in ~10 lines:

```python
import json, pathlib

run = pathlib.Path("traces/<run-dir>")
meta = json.loads((run / "run-meta.json").read_text())
msgs = [json.loads(l) for l in (run / "agent-messages.jsonl").open()]
acts = [json.loads(l) for l in (run / "actions.jsonl").open()]
outcome = json.loads((run / "interception.json").read_text())
print(meta["model"], len(msgs), "messages,", len(acts), "actions")
```

## Recipes

**1. Agent SFT / distillation data.** `agent-messages.jsonl` from passing runs
is on-policy expert data for browser agents — real sites, real DOM, real
recoveries from pop-ups and consent walls. Filter by `interception.json`
outcome for success-only trajectories, or keep failures for contrastive
training. TurnOPD used exactly this shape of data for turn-aware on-policy
distillation.

**2. Process reward models.** Join `actions.jsonl` timestamps against the
final outcome to get step-level credit assignment targets. RedundancyBench
built a redundant-step detection benchmark this way — best method only reaches
24.9%, so the problem is open.

**3. Failure taxonomies.** For every failed run you have the agent's own
reasoning at the moment things went wrong. Cluster failure modes across
models: selector staleness, consent-wall loops, hallucinated UI, premature
termination. Our blog series ([trace autopsies](blog/)) publishes worked
examples.

**4. Security & privacy auditing.** `requests.jsonl` records every byte agents
tried to send. What do agents leak into query params? Do they ever call
endpoints the task never required? The interceptor already blocks irreversible
requests; the logs let you study near-misses.

**5. Judge research.** Two-stage labels (deterministic interception + LLM
judge verdicts under lenient/strict rubrics) make the traces a testbed for
verifier/judge robustness studies — rubric sensitivity is measurable per run.

**6. Site-drift studies.** Repeated runs of the same task over months capture
how production websites change under agents' feet — a longitudinal resource no
sandbox benchmark can produce.

## Citing

If you build on the traces, please cite the benchmark (see
[Citation](../README.md#citation)) — and open an issue so we can feature your
work in [Awesome Works using ClawBench](../README.md#awesome-works-using-clawbench).
