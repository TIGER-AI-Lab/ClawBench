# ClawBench on AssistantBench

Runs [AssistantBench](https://huggingface.co/datasets/AssistantBench/AssistantBench)
(Yoran et al., [arXiv:2407.15711](https://arxiv.org/abs/2407.15711)) under the
ClawBench harness, and reports AssistantBench's own answer metric next to
ClawBench's two stages. Advances [#188](https://github.com/TIGER-AI-Lab/ClawBench/issues/188).

AssistantBench is 214 live-web tasks picked to be realistic and time-consuming:
multi-step research, comparison shopping, "which gyms near me have fitness classes
before 7AM". It is the long-horizon slice ClawBench V1 and V2 do not cover, and it
grades a free-text answer rather than an intercepted request.

## The mapping

There is no final write request for Stage-1 to intercept. ClawBench already solved
that shape for the `claw-eval` port, and it is in `main`: the instruction tells the
agent to submit its final answer at the runtime server's
`http://127.0.0.1:7878/submit` form, that form `POST`s to `/api/task-submit`, the
task's `eval_schema` targets that endpoint, and the LLM judge scores the submitted
answer against `judge_context`. This adapter reuses that path verbatim, so an
AssistantBench task runs through the ordinary pipeline with **no runner changes**
and produces the standard five-layer bundle. A test pins the `eval_schema` and the
footer wording against a bundled `claw-eval` task so the two cannot drift.

| ClawBench | AssistantBench |
| --- | --- |
| `metadata.source_task_id` | `id`, verbatim, the real key |
| `metadata.task_id` | `600000 + n`, n over ids in sorted order |
| `metadata.class` | the expertise field inside `metadata` |
| `metadata.sites_involved` | hostnames parsed out of `gold_url` |
| `instruction` | `task` + answer-format block + the claw-eval submit footer |
| `eval_schema` | fixed `POST /api/task-submit` |
| `time_limit` | `--time-limit`, default 30 (upstream is long-horizon) |
| `judge_context.reference_solution` | `answer` + `explanation` + `gold_url` |
| `judge_context.rubric` | derived from whether a gold answer ships |

Gold answers never enter the container: `run.py` mounts only the `eval_schema`
block as `/eval-schema.json`, so `metadata` and `judge_context` stay on the host
where the judge and the scorer read them. A test asserts the gold answer does not
appear in any agent-facing field.

## Three scores, not two

| Stage | Question | Where |
| --- | --- | --- |
| 1 | Did the agent commit to an answer at all? | `run-meta.intercepted` |
| 2 | Does the answer fulfil the instruction, per the rubric? | `judge.json` |
| 3 | Does the answer match gold, by AssistantBench's own metric? | `clawbench-assistantbench-score` |

Stage 3 is deterministic and has no model in the loop, which is the point: it is an
independent check on the LLM judge over the same runs.

## Use it

Download the dataset (Apache-2.0, small) and export a split as JSON lines:

```bash
hf download AssistantBench/AssistantBench --repo-type dataset --local-dir ./assistantbench
```

Then adapt, run, and score:

```bash
clawbench-assistantbench-adapt \
    --input ./assistantbench/validation.jsonl \
    --output-dir test-cases/assistantbench

clawbench-batch --models <model> \
    --cases-dir test-cases/assistantbench --all-cases --harness openclaw

clawbench-assistantbench-score test-output/<model> \
    --gold test-cases/assistantbench/assistantbench-gold.json \
    --json-out assistantbench-score.json
```

`--split`, `--difficulty`, `--ids` and `--limit` narrow the suite;
`--time-limit` sets the per-task wall clock. `--write-run-meta` on the scorer adds
`assistantbench_answer_score` to each scored `run-meta.json`; it is off by default
because it edits run output you already have.

The scorer prints the upstream leaderboard's row: accuracy, answer rate, precision,
exact match, and accuracy by difficulty.

Two things to know about what it averages over. Every metric averages over *runs*,
the way `clawbench-analyze` does, so a task you ran twice weighs twice; the report
says so whenever the run count and the distinct-task count differ. And a
leaderboard row describes one model, so the scorer refuses a directory whose runs
span several models rather than averaging them into a number that means nothing.
Point it at `test-output/<model>`, or pass `--allow-mixed-models` if you really
want them pooled.

## The metric

`clawbench.eval.assistantbench_score` re-implements the `evaluation/` package of the
[AssistantBench leaderboard Space](https://huggingface.co/spaces/AssistantBench/leaderboard)
(Apache-2.0), whose string metric comes from DROP's `drop_eval`. It dispatches on
the shape of the gold answer:

- **number**: `1 - log(ratio)`, floored at 0, so being out by a factor of two keeps
  partial credit and an order of magnitude earns none;
- **string**: token F1 after normalization, gated on the numbers agreeing, so
  "3 bedrooms" never matches "4 bedrooms";
- **record list**: pairwise F1 over key-value records under an optimal 1-1
  alignment, with the denominator being the longer of the two lists, so extra
  records dilute the score.

It is a re-implementation rather than a vendored copy because upstream needs
`numpy` and `scipy` and ClawBench takes neither. `scipy.optimize.linear_sum_assignment`
is replaced by an exact rectangular Jonker-Volgenant solver that the tests check
against brute force.

### Fidelity

Checked against the upstream evaluator running under `numpy` 2.5.3 and `scipy`
1.18.1 over 7249 `(prediction, gold)` pairs: the 3249-pair exhaustive product of a
corpus covering all four answer types, plus 4000 fuzzed pairs. On all 6581 pairs
upstream could score, the two agree exactly, to 1e-9, on both accuracy and answer
rate. On the remaining 668 upstream raises from a malformed prediction: a record
object answering a numeric question, `null`, `true`, a bare list; the port scores
those 0.0 rather than taking down the batch. Every deviation is enumerated in the
module docstring, including the upstream quirks kept on purpose (`,` read as a
decimal point, the log metric exceeding 1 when both values are negative).

## Not done here

- **The held-out test split ships no answers.** Those tasks are still emitted so
  they can be run, and the LLM judge still grades them against the question, but the
  deterministic metric cannot score them locally; scoring the test split means
  submitting to the upstream leaderboard. The adapter reports how many tasks are in
  this state.
- **No live end-to-end run.** The adapter and the metric are covered offline. A
  real AssistantBench batch needs Docker, a model key and hours of live-web time,
  so the `±2pp` reproduction #188 asks for is a follow-up once someone runs it.
- **`--corpus assistantbench` as a first-class selector.** #188 sketches
  `clawbench run --corpus assistantbench`. This ships as a suite generator plus
  `--cases-dir`, matching how `harbor` and `edgebench` already work, and leaving the
  registry question to the task-source adapter work in
  [#72](https://github.com/TIGER-AI-Lab/ClawBench/issues/72).
