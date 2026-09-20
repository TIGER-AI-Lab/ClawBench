# Task sources

Every browser-agent benchmark encodes its tasks slightly differently — WebArena-style JSON, Mind2Web step traces, WebVoyager judge prompts. Task-source adapters convert those definitions into ClawBench's own task type so an external corpus can run through ClawBench's submission interception, five-layer recording, and judge pipeline without hand-converting files or forking the upstream repo.

Adapters are **import-only**: nothing writes back to an upstream format.

This page describes the foundation that is in place today — the shared task type, the registry, and the `clawbench-sources` CLI. Individual benchmark adapters land incrementally; see [issue #72](https://github.com/TIGER-AI-Lab/ClawBench/issues/72) for the sequence. Available so far: [`webvoyager`](../eval/adapters/webvoyager.md).

## Listing what is registered

```bash
uv run clawbench-sources
uv run clawbench-sources --json          # same rows, machine-readable
```

```
SOURCE            STATE    UPSTREAM                                    PIN  PATH
clawbench-native  bundled  -                                           -    <repo>/test-cases
webvoyager        missing  https://github.com/MinorJerry/WebVoyager    -    ~/.cache/clawbench/sources/webvoyager
```

`STATE` is `bundled` when the tasks ship with ClawBench, `cached` when an external checkout is present, and `missing` when it still needs fetching.

```bash
uv run clawbench-sources show clawbench-native     # status + field-mapping table
uv run clawbench-sources cases clawbench-native    # every task the source exposes
uv run clawbench-sources cases clawbench-native --path test-cases/v2
```

A source can also be addressed as `<name>:<path>` to pin it to an explicit clone:

```bash
uv run clawbench-sources cases claw-eval:/srv/checkouts/claw-eval
```

Without a path, a source resolves under `$CLAWBENCH_SOURCES_DIR`, else `$XDG_CACHE_HOME/clawbench/sources`, else `~/.cache/clawbench/sources`. Set `CLAWBENCH_OFFLINE=1` to forbid network fetches; a source with no local checkout then fails loudly instead of cloning.

## The shared task type

Adapters produce `ClawBenchTask` (`src/clawbench/adapters/schema.py`), a superset of `test-cases/task.schema.json` plus provenance:

| Field | Meaning |
|---|---|
| `task_id` | ClawBench's identifier for the task |
| `source` | registered adapter name |
| `source_id` | the upstream benchmark's own identifier |
| `instruction` | prompt sent to the agent |
| `time_limit` | **minutes**, matching `task.json` and the container watchdog |
| `eval_schema` | interceptor config, when the source has a submission contract |
| `scoring_layers` | which scoring mechanisms this source can honour |
| `extra_info` / `judge_context` / `metadata` | carried through as in `task.json` |
| `warnings` | field-mapping gaps found at load time |

Most upstream schemas express time limits in seconds; adapters convert.

## Scoring layers

An adapter declares which layers its tasks can be judged by:

| Layer | Applies when |
|---|---|
| `submission_intercept` | the task has a final write request to intercept |
| `end_state_dom_match` | ClawBench's default judge pipeline applies |
| `step_trace_replay` | the upstream rubric is per-step (Mind2Web-style) |
| `goal_predicate` | the upstream rubric is a boolean goal function (WorkArena/BrowserGym) |
| `llm_judge_only` | the upstream rubric is a free-form judge prompt (WebVoyager) |

A layer a source cannot support scores `null` in the recording — never `0` — so leaderboard aggregation never confuses "the agent failed" with "this task was never scored on that axis". `ClawBenchTask.to_task_json()` refuses to render a native `task.json` for a task with no interception contract, rather than inventing one.

## Field-mapping warnings

When an adapter cannot map a field 1:1 it attaches an `AdapterWarning` to the task instead of dropping it silently. Each warning names the source, the task, the field, the fallback used, and the pinned upstream revision the mapping was written against:

```
[mind2web/t1] time_limit: upstream has no per-task limit (using 300s) [upstream abc1234]
```

Adapters pin an upstream commit or tag so a rename upstream cannot quietly change what a run measures.

## Writing an adapter

Subclass `AdapterBase`, declare the metadata, and register it:

```python
from clawbench.adapters import AdapterBase, ScoringLayer, register

@register
class MyBenchmarkAdapter(AdapterBase):
    name = "my-benchmark"
    upstream = "https://github.com/example/my-benchmark"
    pinned_sha = "abc1234"
    scoring_layers = (ScoringLayer.LLM_JUDGE_ONLY,)

    def load(self, path):
        ...  # -> list[ClawBenchTask]
```

Document the field mapping as a table in the module docstring — `clawbench-sources show <name>` prints it. `native.py` is the reference implementation.

Related: [`docs/cli.md`](cli.md) · [`docs/harbor.md`](harbor.md) · [`CONTRIBUTING.md`](../CONTRIBUTING.md)
