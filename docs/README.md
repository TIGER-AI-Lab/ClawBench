# ClawBench documentation

[Project overview](../README.md) · [中文介绍](README.zh-CN.md)

## Run a benchmark

| Guide | Use it for |
| --- | --- |
| [Getting started](getting-started.md) | Install, configure a model and judge, choose a harness, and run your first task |
| [CLI reference](cli.md) | Find commands, suite selectors, and common options |
| [Browser runtimes](browser-runtimes.md) | Configure local browsers, remote CDP, Kernel, or Browserbase |
| [V1 vs V2](v1-vs-v2.md) | Understand corpus design and choose a suite |
| [Task walkthrough](walkthrough.md) | Follow a task specification through recording and evaluation |
| [FAQ](faq.md) | Understand account setup, task state, artifacts, and live-site behavior |

## Inspect and evaluate runs

| Guide | Use it for |
| --- | --- |
| [Trace cookbook](trace-cookbook.md) | Locate recordings, messages, request logs, and provenance |
| [Rescore and analyze](cli.md#clawbench-rescore) | Judge saved requests or report on a completed batch |
| [Reproduce the leaderboard](../README.md#reproduce-the-leaderboard) | Re-run agents or re-judge published traces |
| [Human-reference evaluation](../eval/README.md) | Compare full trajectories under the original V1 rubric |
| [Answer-mode tasks](answer-mode-tasks.md) | Define and judge tasks that produce an answer |
| [OpenEval / EvalPort export](../eval/README.md#export-results-to-openeval--evalport) | Share a rescored batch as a ResultSet |

Native request scoring and human-reference trajectory evaluation are distinct
workflows. Compare results with the same corpus revision, harness, and rubric.

## Integrate another runner

- [Harbor](harbor.md): convert ClawBench tasks into a Harbor dataset.
- [EdgeBench / SForge](edgebench.md): export tasks and judge returned results.
- [ProRL-Agent-Server](prorl-rl-env.md): submit and inspect RL rollouts.

## Contribute

- [Source layout](../src/README.md): entry points, module responsibilities, and
  workspace versus package paths.
- [Contributing](../CONTRIBUTING.md): add tasks, set up development, and run checks.
- [Runtime server](../src/clawbench/runtime/runtime-server/README.md): browser
  instrumentation, request interception, and recording.
- [Agent context](../AGENTS.md): repository instructions for coding agents.
- [Changelog](../CHANGELOG.md) and [news archive](news.md): engineering changes
  and project announcements.

Keep installation steps in Getting started, command options in the CLI
reference, and code ownership in Source layout. Link to these guides when
adding a feature so the same instructions do not drift across multiple pages.
