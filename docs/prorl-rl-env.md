# ClawBench as a ProRL-Agent-Server ("Polar") RL environment

This document describes how ClawBench V2 tasks are exposed as RL rollouts for
[NVIDIA-NeMo/ProRL-Agent-Server](https://github.com/NVIDIA-NeMo/ProRL-Agent-Server)
("Polar"), closing #219.

## Why this is thin

Polar uses a **"Harness as Environment"** model. A Rollout Server (`:8080`)
expands a task into `num_samples` sessions; each runs on a Gateway node that:

1. starts a container and runs an **agent harness** inside it;
2. **proxies and captures the policy's LLM calls** into a token-faithful
   trajectory (token IDs + logprobs + loss mask) — the agent does nothing
   special, it just calls the gateway-injected endpoint;
3. grades the final container state with an **evaluator**, attaching a reward.

Two facts make the ClawBench integration almost entirely reuse:

- **Reward is done.** Polar ships a built-in **`harbor` evaluator** that runs a
  `tests/test.sh` and reads `/logs/verifier/reward.json` (or `reward.txt`) —
  exactly what `clawbench-harbor-adapt` already produces. No new reward code.
- **Token capture is Polar's job**, not ClawBench's. Because the gateway proxy
  captures tokens, ClawBench does **not** need to emit token IDs (unlike a
  Harbor-native RL rollout, which needs a vLLM/Tinker-served policy to recover
  tokens). ClawBench only has to route the policy model through the injected
  endpoint.

## What this package adds (`clawbench.prorl`)

| Piece | File | Role |
|---|---|---|
| `TaskRequest` models | `models.py` | Typed Polar submission payload + `to_payload()` |
| Submission client | `submit.py` (`clawbench-prorl-submit`) | Stage a task (reusing `harbor_adapter`), build the payload, submit/poll/read reward |
| Shell-harness entry | `run-prorl.sh` | Routes the ClawBench browser episode's policy model at `$OPENAI_BASE_URL`/`$OPENAI_API_KEY` |
| Topology template | `topology.example.yaml` | Fleet config (rollout + gateway + inference) |
| Offline mock | `mock_gateway.py` (`clawbench-prorl-mock`) | Faithful Rollout-Server + `harbor`-evaluator mock for contract testing without GPUs/browser |

### Submission flow

```
clawbench-prorl-submit --task v2-047-... --rollout-url http://host:8080 \
    --harness hermes --model-name clawbench-policy --num-samples 8 \
    --judge-model glm-5.1 --judge-base-url https://api.z.ai/api/paas/v4 --judge-api-key sk-...
```

The concrete browser harness is **baked into the runtime image** (its Dockerfile
layer installs the env-driven `/run-harness.sh`); pick it with `--image`
(defaults to `clawbench-<harness>:latest`). `run-prorl.sh` exports the policy
endpoint as `BASE_URL`/`API_KEY`/`API_TYPE`/`MODEL_NAME` + `INSTRUCTION` — the
vars the harness runners read — then hands off. The `--judge-*` flags populate
the evaluator env (`CLAWBENCH_JUDGE_*`) so Stage-2 judging runs during rollouts;
they are **independent of** the policy endpoint (never `$OPENAI_BASE_URL`).

1. `harbor_adapter.write_harbor_task` stages the task → `instruction.md`,
   `tests/test.sh` (two-stage verifier → `reward.json`), `workdir/{task.json,
   eval-schema.json, setup.sh, extra_info}`.
2. A `TaskRequest` is built:
   - `runtime.prepare` uploads the workdir + the **Harbor runtime scripts**
     (`/app/src/harbor/{prepare-task,start-runtime,verify}.py`) + `run-prorl.sh`
     + instruction, then `exec bash /app/setup.sh` (brings up Chromium/CDP on
     `:9223` + runtime-server). Uploading the Harbor scripts means the image only
     needs to be a **ClawBench harness image** (base + a harness `/run-harness.sh`
     + runtime-server) — no bespoke combined image. `run-prorl.sh` also exports
     `CLAWBENCH_BROWSER_CDP_URL` because the base entrypoint (which normally
     defaults it) is bypassed by the shell harness.
   - `agent` = **shell** harness running `bash /app/run-prorl.sh`.
   - `evaluator` = **harbor** over the staged `tests/`.
   - `builder` = `prefix_merging` (recommended for multi-turn agents).
3. `POST /rollout/task/submit` → poll `GET /rollout/task/{id}` → read
   `sessions[].trajectory.traces[-1].reward`.

### Correctness guard: keep the judge off the policy proxy

`run-prorl.sh` points **only the policy model** at `$OPENAI_BASE_URL`. The
Stage-2 LLM judge runs later, host-side, inside the `harbor` evaluator
(`test.sh` → `verify.py`) using the independent `CLAWBENCH_JUDGE_*` endpoint. If
the judge used `$OPENAI_BASE_URL`, its tokens would be captured and scored as
trainable policy tokens, corrupting the gradient. `test_run_script_routes_policy_but_not_judge`
enforces this.

## Verified offline

`clawbench-prorl-mock` reimplements the Rollout-Server HTTP surface and the
`harbor`-evaluator reward rule (run `test_command`; read `reward.txt` then
`reward.json` scalar/averaged; clamp `[0,1]`). The test suite drives a real
`submit → poll → extract_rewards` handshake against it and asserts the reward
round-trips — proving the full contract without GPUs, an inference server, or a
browser.

```
uv run --frozen pytest tests/test_prorl_*.py -q     # 13 passed
```

## Real training runbook (GPU box, e.g. `nick@ubuntu`)

A full RL *training* run needs GPUs + an inference server + a trainer. The
adapter above makes ClawBench submittable; the remaining infra is standard Polar:

1. **Build the runtime image** (`clawbench-harbor:latest`) with Chromium +
   runtime-server + the browser harness (the existing `src/clawbench/runtime/harbor`
   image). Reference it as `runtime.image` / `--image`.
2. **Serve the policy** on vLLM or SGLang as an OpenAI-compatible server. The
   served model **must be a VLM** (ClawBench agents send screenshots):
   `vllm serve Qwen/Qwen3-VL-8B-Instruct --port 8000`.
3. **Start the fleet**: `polar rollout --topology topology.yaml` (copy
   `topology.example.yaml`; set `model_served` + `inference.base_url`).
4. **Drive rollouts** from the trainer: for each task, `clawbench-prorl-submit`
   (or the equivalent `TaskRequest`) with `--num-samples` = your GRPO group
   size. Polar returns per-session trajectories + rewards to the trainer
   (Polar is registered as a NeMo Gym environment; see the ProRL paper).
5. **Reward shaping (optional):** `reward.json` can carry multiple keys
   (e.g. `{"intercept": x, "judge": y}`); Polar's `harbor` evaluator averages
   them to `[0,1]`. For denser per-step reward, swap in a custom evaluator.

## Relationship to Harbor RL

Harbor can *also* generate RL rollouts (Path A: wrap `Job.run()`, map
`TrialResult → Rollout`), but that path needs ClawBench to emit token IDs
itself (vLLM/Tinker-served policy), because Harbor captures tokens at the LLM
backend rather than a proxy. Polar's proxy model is the lower-friction route for
a browser agent, which is why this package targets Polar first. ClawBench's
`reward.json` already satisfies both.
