# Answer / rubric judge — importing rubric-based benchmarks

ClawBench's native scoring is **two-stage HTTP interception**: Stage-1 matches the
agent's request against `eval_schema.{url_pattern, method}`, Stage-2 asks the LLM
judge whether that request fulfils the instruction (`judge_request`).

Many other agent benchmarks — **claw-eval** (#170), **AssistantBench** (#188),
**Online-Mind2Web** (#189), **WebVoyager** (#190) — instead score a **free-text
answer or a rubric**, with no single interceptable target request. To import them
without disturbing the interception path, this adds the missing primitive:

## `judge_answer(...)`

`clawbench.runner.judge.judge_answer(model_cfg, judge_model_name, instruction,
answer, *, judge_context=None)` returns the same verdict dict as `judge_request`
(`match`/`reason`/`judge_model`/`raw`/`error`), but judges the agent's **final
answer/outcome** against the instruction and an optional **rubric** in
`judge_context` (`rubric` / `reference_solution` / `gold_answer`).

Both judges now share `_run_judge()` (dispatch by api_type + parse), so behaviour
and provider support stay identical.

## Proposed "answer-mode" task shape (opt-in, non-breaking)

An imported task is expressed with an `eval_schema.mode` discriminator
(default `"interception"`, unchanged for all existing tasks):

```json
{
  "instruction": "...",              // from the source benchmark's query
  "eval_schema": {"mode": "judge"},  // no url_pattern needed for judge-mode
  "judge_context": {"rubric": "..."},// the source benchmark's rubric / gold
  "metadata": {"category": "...", "source": "claw-eval"},
  "time_limit": 15
}
```

At scoring time: `mode == "interception"` → the current Stage-1 + `judge_request`
path; `mode == "judge"` → skip Stage-1 and score the agent's final answer with
`judge_answer`. (The corpus-integrity guard that requires a non-empty
`url_pattern` becomes mode-aware: required for interception tasks, not judge
tasks.)

## What this unblocks

This is the enabling primitive for the import-adapter issues. e.g. **claw-eval**
(`task_id, query, fixture, language, category`, HF `claw-eval/Claw-Eval`, 300
tasks) maps as `query → instruction`, `category → metadata`, its eval-yaml rubric
→ `judge_context`, `mode: "judge"`. The remaining runner wiring (extract the
agent's final answer from the trajectory, branch on `mode`) is a small, separate
change; this PR lands the tested judge primitive so that work has a foundation and
the direction can be reviewed first.
