# Operating long batches

A full V2 sweep is 8–20 hours per (model × harness). Over that span something
outside the agent's control will go wrong — a container gets OOM-killed, a
provider returns 502 for half a minute, a queue cap trips at task 75. This page
covers what to do about it: how to resume, how to make resuming automatic, how
to find out promptly, and what an abort does and does not cost you.

## How to resume a run

Every batch writes into one directory, `test-output/batch-<timestamp>/`, with
one run directory per (case × model) and a `batch-logs/` folder beside them.
That directory *is* the checkpoint. To continue an interrupted batch, re-run
the same command with `--resume` pointing at it:

```bash
uv run clawbench-batch --models deepseek-v4-flash --cases-suite v2 --all-cases \
  --harness hermes --resume test-output/batch-20260912-081500
```

Jobs the batch already finished are skipped; everything else runs. The rest of
the command line must match the original — the batch directory records
outcomes, not the flags that produced them.

## Making resume automatic

```bash
uv run clawbench-batch --models deepseek-v4-flash --cases-suite v2 --all-cases \
  --harness hermes --auto-restart 3
```

`--auto-restart N` runs the batch under a small supervisor. If the batch
process exits non-zero — including being killed outright — the supervisor
waits (`--auto-restart-delay`, default 30s) and re-invokes it with `--resume`
into the same directory, up to N times. The supervisor holds no browser, no
containers, and no model calls, which is exactly why it survives the failures
the batch does not.

Some things to know:

- The batch directory is created *before* the first attempt, so every attempt
  — including the first — runs as a resume into one place. You can also pass
  `--resume` yourself to supervise an existing batch.
- **Ctrl-C is never retried.** An interrupt stops the supervisor after the
  current attempt winds down; only failures restart.
- The final exit status is the last attempt's: `0` only when an attempt
  finished with every job in a terminal state.
- It is single-host. If the machine itself goes away, so does the supervisor;
  resume by hand when it comes back.

## Getting told when something happens

```bash
uv run clawbench-batch-watch test-output/batch-20260912-081500 \
  --pid <batch pid> --heartbeat-every 10
```

`clawbench-batch-watch` polls a batch directory and posts to a webhook when
the batch **aborts** (with the last task, an error tail from the newest log, and
elapsed time), when it **completes** (with pass/total and wall-clock), and
optionally a **heartbeat** every N completed tasks. It reads only artifacts the
batch already writes, so it needs nothing from the batch process.

Abort is detected two ways: if you pass `--pid`, the batch process exiting
without a `batch-summary.json` is an abort; either way, `--stall-timeout`
(default 45 minutes) with no new artifacts is treated as one.

Configure routing once per operator in `~/.config/clawbench/notify.toml`:

```toml
webhook_url = "https://hooks.slack.com/services/…"   # or a Discord webhook
interval_s = 60
heartbeat_every = 10
stall_timeout_s = 2700
```

Flags override the file. With no webhook configured the watcher still prints
each notification, which is enough for a terminal or a log.

## What survives an abort and what does not

**Survives.** Every run directory that reached `run-meta.json` — its trace
bundle, its interception result, its judge verdict if the judge ran. Those are
what `--resume` skips.

**Does not survive.** The task that was in flight when the process died. Its
run directory may exist with a partial recording and no `run-meta.json`; on
resume that task is re-run from scratch and the partial output is discarded.
There is no action-level checkpointing inside a task, and there is no plan for
one — a task is the unit of work.

**Is not restored.** Batch-level bookkeeping from the aborted attempt.
`batch-summary.json` is written at the end of an attempt, so an aborted attempt
leaves none; the summary you get is the final attempt's, and jobs it skipped
because they were already done appear there as `skipped`. Use
`clawbench-rescore` on the batch directory for a full accounting across
attempts.

Related: [`docs/cli.md`](cli.md) · [`eval/scoring.md`](../eval/scoring.md)
