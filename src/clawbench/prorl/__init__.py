"""Run ClawBench as an RL environment for ProRL-Agent-Server ("Polar").

Polar (NVIDIA-NeMo/ProRL-Agent-Server) trains agents with a
"Harness as Environment" model: a Rollout Server (:8080) expands a task into
``num_samples`` sessions, each driven on a Gateway node that (a) runs an agent
*harness* inside a container, (b) proxies + captures the policy's LLM calls into
a token-faithful trajectory, and (c) grades the final container state with an
*evaluator*, attaching a reward to the trajectory.

ClawBench slots in with almost no new machinery:

* **Harness** — the generic Polar ``shell`` harness runs a ClawBench browser
  episode whose model client is pointed at the gateway-injected
  ``$OPENAI_BASE_URL`` / ``$OPENAI_API_KEY`` (the key value is the session id),
  so every policy call is captured. See ``run-prorl.sh``.
* **Reward** — Polar's built-in ``harbor`` evaluator runs ``tests/test.sh`` and
  reads ``/logs/verifier/reward.json`` — exactly what ClawBench's harbor task
  export already writes. No new reward code.
* **Submission** — :mod:`clawbench.prorl.submit` builds the Polar ``TaskRequest``
  per ClawBench task and drives submit/poll/read-reward.

The Stage-2 LLM judge deliberately uses a *separate* endpoint
(``CLAWBENCH_JUDGE_BASE_URL``), never ``$OPENAI_BASE_URL`` — otherwise judge
tokens would be captured and scored as trainable policy tokens.
"""

from clawbench.prorl.models import (
    AgentSpec,
    BuilderSpec,
    EvaluatorSpec,
    PrepareAction,
    RuntimeSpec,
    TaskRequest,
)

__all__ = [
    "AgentSpec",
    "BuilderSpec",
    "EvaluatorSpec",
    "PrepareAction",
    "RuntimeSpec",
    "TaskRequest",
]
