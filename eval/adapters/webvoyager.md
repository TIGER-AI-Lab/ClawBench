# Running WebVoyager tasks under ClawBench

[WebVoyager](https://github.com/MinorJerry/WebVoyager) is the closest scope-peer of ClawBench: live websites, a multimodal browser agent, one question per task with a free-text answer. This adapter loads its task list so those tasks run through ClawBench's five-layer trace pipeline and two-stage scoring, without forking the upstream repo.

This page covers what ships today — the task loader — and what it deliberately does not do yet. See [`docs/task-sources.md`](../../docs/task-sources.md) for the adapter framework itself.

## 1. Get the tasks

```bash
git clone --depth 1 https://github.com/MinorJerry/WebVoyager.git ~/.cache/clawbench/sources/webvoyager
```

The adapter reads `data/WebVoyager_data.jsonl` (one task per line) and, when present, `data/reference_answer.json`. Point it at the checkout, or straight at the `.jsonl`:

```bash
uv run clawbench-sources cases webvoyager                      # default cache location
uv run clawbench-sources cases webvoyager:/path/to/WebVoyager  # explicit clone
uv run clawbench-sources show webvoyager                       # status + field mapping
```

Each task prints with any field-mapping warnings beneath it — a missing start URL, or no reference answer for that id.

## 2. How a WebVoyager task scores

WebVoyager scores by a screenshot-and-LLM judge over the trajectory. There is no final write request to intercept, which is what ClawBench's Stage 1 keys on.

ClawBench already solved this for the claw-eval port, and the adapter reuses that path exactly:

1. The instruction is the upstream question plus a footer telling the agent to submit its final answer at `http://127.0.0.1:7878/submit` — a form served by the runtime server inside the container.
2. The form posts to `POST /api/task-submit`, and the task's `eval_schema` targets that endpoint. **That submission is the Stage-1 interception.**
3. Stage 2 hands the submitted answer to the LLM judge with the task's `judge_context`: the upstream reference answers, labelled `[golden]` (exact) or `[possible]` (acceptable), and a rubric saying how to weigh them.

So a WebVoyager task produces the standard trace bundle — `recording.mp4`, `actions.jsonl`, `agent-messages.jsonl`, `requests.jsonl`, `interception.json`, `run-meta.json` — and the standard `intercepted` / `judge_match` pair, with no change to the runner.

## 3. Field mapping

| ClawBench | WebVoyager | Note |
|---|---|---|
| `task_id` | `id`, lower-cased | e.g. `allrecipes--0` |
| `source_id` | `id` | verbatim, for joining back to upstream |
| `instruction` | `ques` + submit footer | |
| `url` | `web` | start URL; warns if absent |
| `category` | `web_name` | the site |
| `time_limit` | — | upstream is step-bounded (15 steps), not wall-clock; 10 minutes, matching the claw-eval port |
| `eval_schema` | — | `POST /api/task-submit` |
| `judge_context.reference_solution` | `reference_answer.json` | warns if no entry for this id |

A task with no `id` or no `ques` cannot be a task and fails the load with its line number. Everything else missing becomes a warning on the task, never a silent drop.

## 4. Not done here

- **The upstream screenshot judge.** #190 asks for both scores side by side — WebVoyager's screenshot judge and ClawBench's interception + payload judge — so the two paradigms can be compared on the same runs. That needs their judge prompt wired as a second scorer and belongs with the runner change that records a second verdict in `run-meta.json`. The loader is a prerequisite for it, not a substitute.
- **Reproducing the upstream number.** Checking ±3pp against `gpt-4-1106-preview-runs.zip` requires the passthrough above and real runs.
- **Pinning.** `pinned_sha` is unset until the shared `_pins.yaml` lands (#72, step 5). Until then, load warnings report no upstream revision.
- **GAIA and other subsets.** Only `WebVoyager_data.jsonl` is read. `data/GAIA_web.jsonl` has the same shape and can be loaded by passing its path directly, but it has not been checked.

Related: [`docs/task-sources.md`](../../docs/task-sources.md) · [`docs/answer-mode-tasks.md`](../../docs/answer-mode-tasks.md) · [`eval/scoring.md`](../scoring.md)
