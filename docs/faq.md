# Frequently asked questions

[Documentation](README.md) · [Getting started](getting-started.md) · [CLI reference](cli.md)

## What does ClawBench measure?

ClawBench evaluates browser agents on everyday tasks on live websites: ordering
food, booking travel, applying for jobs, managing calendars, and more. Runs
produce recordings and structured evidence so evaluators can check what the
agent actually did. See [V1 vs. V2](v1-vs-v2.md) for how the task suites differ.

## Which suite should I use?

V1 contains 152 tasks across 143 websites; V2 contains 129 tasks. The
[20-task Lite subset](../test-cases/v1-lite/) supports smaller V1 experiments.
Select a suite based on the workflow and scoring method you want to evaluate;
the [CLI reference](cli.md#task-suites) lists all available suites.

A finite task set measures performance on those tasks. Treat differences
between models in the context of corpus coverage, run count, and live-site
variation rather than as a universal ranking of agent capability.

## How should I compare published scores?

Use the [leaderboard](https://huggingface.co/spaces/TIGER-Lab/ClawBench) and
compare rows with the same corpus revision, harness, scoring rubric, and
denominator. The 33.3% figure from the original V1 paper is a historical result.
Published runs can retain their original task counts after tasks are removed
from the shipping corpus.

The harness and model are separate experimental choices. The default harness
is `openclaw`; other published runs use Hermes and additional harnesses. The
related [HarnessBench](https://github.com/reacher-z/HarnessBench) project
focuses on varying the harness while holding the model fixed.

## What data does a run produce?

The five recording layers are session replay, action screenshots, browser
actions, HTTP traffic, and agent messages. Local runs store them under the run's
`data/` directory, alongside `interception.json`; `run-meta.json` records the
configuration and outcome. See the [Trace Cookbook](trace-cookbook.md) for
artifact schemas and download examples.

Agent message formats depend on the harness. For example, Pi preserves complete
messages and tool events but omits streaming message fragments. Replay storage
also depends on the [browser runtime](browser-runtimes.md): Kernel provides a
downloaded video, while Browserbase stores a provider replay URL in metadata.

## How do identity, login, and starting state work?

Each run receives a synthetic Alex Green profile, a resume, and a fresh
disposable PurelyMail email account in `/my-info/`. Tasks that require sign-up
normally start without an existing account. Task-specific files and starting
context come from the task's `extra_info` entries.

The source templates are the [personal profile](../src/clawbench/runtime/shared/alex_green_personal_info.json)
and [resume template](../src/clawbench/runner/run_support/resume_template.json).

## Which tools and harnesses can agents use?

The task prompt requires browser-based task completion. Each harness configures
its browser and file tools; the exact restrictions depend on the harness.
Hermes and Pi use native browser tools, while several coding-agent harnesses
use a Playwright MCP bridge. Pi enables read-only file tools and browser
interaction tools, excluding shell and file-editing tools.

Use `--harness <name>` to select a harness. See [getting started](getting-started.md)
and the [harness registry](../src/clawbench/runtime/harnesses/harnesses.yaml)
for supported configurations.

## Can I use Podman or a remote browser?

Native ClawBench runs support Docker and Podman. Set `CONTAINER_ENGINE=podman`
to select Podman explicitly; macOS and Windows also require a running Podman
machine. See [getting started](getting-started.md) for setup.

[Remote browser runtimes](browser-runtimes.md) include Kernel, Browserbase,
and an existing CDP endpoint. [Harbor](harbor.md) runs use Harbor's Docker
provider.

## How is a task judged successful?

The native runner defaults to two-stage scoring: a request must match the task's
interception schema, then the configured LLM judge checks that request against
the instruction. `--no-judge` reports interception alone. The
[scoring reference](../eval/scoring.md) defines the metrics.

The historical V1 evaluation instead compares recorded agent trajectories with
human references using the [agentic evaluation rubric](../eval/agentic_eval.md).
Follow the [evaluation guide](../eval/README.md) to run that workflow separately.
Tasks with `__PLACEHOLDER_WILL_NOT_MATCH__` cannot pass the native interception
gate; the request judge does not automatically switch to trajectory evaluation.
The [walkthrough](walkthrough.md) illustrates this distinction.

## What exactly does the interceptor block?

The interceptor uses Chrome's CDP `Fetch` domain to match requests against a
task's `url_pattern`, HTTP `method`, and optional `body` or `params` filters.
A match is blocked, saved to `data/interception.json`, and triggers session
shutdown. Requests that do not match the schema continue to the live website.

Blocking is specific to the configured schema. A placeholder pattern is
intended never to match, and therefore does not block checkout or other
submissions. Such a run ends through another stop condition, such as agent exit
or timeout. Interception alone also does not establish that the submitted
content fulfills the instruction.

## How do website changes and bot checks affect results?

Layouts, availability, login flows, and anti-bot systems can change between
runs. Record the corpus revision and run configuration when comparing results,
and inspect traces to distinguish these failures from agent errors.

The historical [agentic rubric](../eval/agentic_eval.md) requires the agent to
attempt encountered CAPTCHAs. In native two-stage scoring, a run that never
reaches the matching request fails Stage 1. Failure prevalence must be measured
from the particular runs being compared.

## How do I reproduce or contribute a result?

[Reproduce the leaderboard](../README.md#reproduce-the-leaderboard) describes
re-running agents and re-judging published traces. Use the same judge, rubric,
corpus revision, and harness when comparing outcomes.

For new tasks, harnesses, or model results, follow [CONTRIBUTING.md](../CONTRIBUTING.md).
Task definitions use [task.schema.json](../test-cases/task.schema.json), and
human mode can record a reference trajectory before submission.
