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

| Dataset                                                                                    | Contents                                |
| ------------------------------------------------------------------------------------------ | --------------------------------------- |
| [NAIL-Group/ClawBenchV1Trace](https://huggingface.co/datasets/NAIL-Group/ClawBenchV1Trace) | One directory per (model × V1 task) run |
| [TIGER-Lab/ClawBenchV2Trace](https://huggingface.co/datasets/TIGER-Lab/ClawBenchV2Trace)   | Same bundle for V2 runs; rolling        |

Each run directory contains:

| File                   | Layer                                            | Typical use                                 |
| ---------------------- | ------------------------------------------------ | ------------------------------------------- |
| `agent-messages.jsonl` | Agent transcript (thinking, text, tool calls)    | SFT / distillation / process supervision    |
| `actions.jsonl`        | Every DOM event (click, input, scroll, pageLoad) | Action-level analysis, redundancy detection |
| `requests.jsonl`       | Every HTTP request (headers, body, params)       | Security auditing, intent verification      |
| `screenshots/*.png`    | Timestamped PNG per action                       | Vision grounding, GUI datasets              |
| `recording.mp4`        | Full session video (H.264, 15 fps)               | Qualitative analysis, demos                 |
| `interception.json`    | The final blocked request                        | Outcome labels (Stage-1)                    |
| `run-meta.json`        | Model, harness, task, timing, provenance         | Joins and filtering                         |

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

### Provenance

`run-meta.json` carries a `provenance` block naming the exact revisions behind
the names in the rest of the file, so a row on a leaderboard can be traced back
to the code, corpus, and agent build that produced it:

```json
"provenance": {
  "clawbench_version": "0.10.0",
  "commit": "3f3599d...",
  "branch": "main",
  "dirty": false,
  "corpus": {"suite": "v2", "path": "test-cases/v2", "revision": "62ee923..."},
  "harness": {
    "name": "openclaw",
    "image_id": "sha256:...",
    "agent_version": "2026.3.13",
    "pinned_versions": {"openclaw": "2026.3.13"},
    "pins_source": "dockerfile"
  }
}
```

`corpus.revision` is the last commit that touched that suite, so two runs with
the same revision saw the same task text.

`harness.pinned_versions` comes from the version pins in the harness Dockerfile
— the agent and any plugins the image was built with. Both released versions
(`opencode-ai@1.4.4`, `litellm[proxy]==1.77.3`) and pinned revisions
(`pkg@github:owner/repo#<sha>`, `pkg @ git+https://…@<ref>`) count. A floating
dist-tag like `@next` is deliberately **not** recorded: it names a moving
target, so calling it a pin would be a false claim, and `agent_version` is
`null` for a harness pinned that way.

`pins_source` says whether those pins describe the image that actually ran:

| Value | Meaning |
|---|---|
| `"dockerfile"` | The image was built from this checkout's Dockerfile during this run, so its pins are the versions that ran. |
| `"unverified"` | The run reused an existing image (`--no-build`) that may predate the Dockerfile on disk. `pinned_versions` and `agent_version` are `null` — nothing is claimed. |

`clawbench-batch` builds the image once and then runs every task with
`--no-build`, so a batch run still reports `"dockerfile"`; a bare
`clawbench-run --no-build` reports `"unverified"`.

Every field is best-effort. A run from a PyPI install has no git checkout and
reports `commit: null`; a task from an explicit `--cases-dir` reports its suite
name but `revision: null`, because its history is not ClawBench's to claim.
`dirty: null` means the lookup failed, which is not the same claim as `false`.
Filter on these before comparing runs:

```python
same_code = {
    run for run in runs
    if run["provenance"]["commit"] == reference["provenance"]["commit"]
    and run["provenance"]["dirty"] is False
}
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
termination. These traces support worked "trace autopsies" of individual
failures.

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
