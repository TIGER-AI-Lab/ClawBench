# A task from prompt to evaluation

[Documentation](README.md) · [Getting started](getting-started.md) · [Scoring](../eval/scoring.md)

This walkthrough uses V1 task 001 to show how a task definition becomes a
recorded browser session. It also explains why a recorded trajectory and an
intercepted request are different evaluation inputs.

## Read the task

The relevant fields in [task 001](../test-cases/v1/001-daily-life-food-uber-eats/task.json) are:

```json
{
  "instruction": "On Uber Eats, order delivery: one Pad Thai, deliver to home address, note \"no peanuts\"",
  "time_limit": 30,
  "eval_schema": {
    "url_pattern": "__PLACEHOLDER_WILL_NOT_MATCH__",
    "method": "POST"
  }
}
```

The agent receives the instruction plus browser-use rules and access to
`/my-info/`: a synthetic personal profile, resume, and disposable email
credentials. Agent mode has a 30-minute task limit. The profile supplies the
home address needed for this task.

The `url_pattern` is an intentional sentinel, not an Uber Eats checkout
endpoint. It is designed never to match a real request. The `POST` method alone
does not trigger interception.

## Record a run

After [setting up a model](getting-started.md), run this from a source checkout,
replacing `your-model` with a key in `models/models.yaml`:

```bash
uv run clawbench-run \
  test-cases/v1/001-daily-life-food-uber-eats your-model --no-judge
```

The command prints a noVNC URL for watching the local browser. A plausible
trajectory is to enter the home address, find a restaurant with Pad Thai,
configure one item with the note, and proceed through the available checkout
flow. Login, availability, or payment requirements may affect how far the run
gets. Evaluate the recorded behavior against the task and rubric.

For a human reference trajectory, use the same task with `--human` instead of
the model argument. See the [CLI reference](cli.md#clawbench-run) for options.

## Inspect the evidence

Local outputs are collected under:

```text
test-output/<model>/<harness>-<case>-<model>-<timestamp>/
  run-meta.json
  eval-schema.json
  data/
    actions.jsonl
    requests.jsonl
    agent-messages.jsonl
    screenshots/
    recording.mp4
    interception.json
```

The request log records browser traffic, and the other layers show how the
agent reached its final state. For this sentinel task, there is no configured
checkout request to block: ordinary requests continue to the website, and the
run ends through another stop condition such as agent exit or timeout.
`interception.json` then records `intercepted: false` and the stop reason.

For a task with a real matching schema, the interceptor blocks the matching
request before it reaches the site, records it, and initiates shutdown. The
[Trace Cookbook](trace-cookbook.md) describes the individual artifacts.

## Choose the evaluation workflow

For the historical V1 workflow, follow the [evaluation guide](../eval/README.md)
to compare this trajectory with a human reference under the
[agentic rubric](../eval/agentic_eval.md). Evidence relevant to task 001 includes:

- Whether the agent attempted the required checkout flow.
- Whether the cart contained exactly one Pad Thai.
- Whether the delivery address matched the profile's home address.
- Whether the special instructions included “no peanuts.”

Apply the rubric's rules for payment attempts and verification blockers when
assigning a verdict; reaching a checkout screen alone is insufficient.

The native runner's default request judge is a separate workflow. It runs only
after a request has been intercepted. Because task 001 uses the sentinel, it
cannot pass Stage 1, and enabling the request judge does not evaluate its
trajectory. `--no-judge` collects the run for separate trajectory evaluation;
it does not turn a non-intercepted run into a native pass. Use the
[scoring reference](../eval/scoring.md) for two-stage metrics on tasks with
matching interception schemas.
