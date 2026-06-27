"""ClawBench ↔ Harbor integration (Harbor as a *runner* for ClawBench tasks).

This package is the opposite direction of the ``runtime/harnesses/harbor`` driver
(which makes Harbor's Terminus-2 agent a ClawBench harness). Here Harbor is the
runner: ``harbor run`` orchestrates ClawBench v2 tasks.

Modules
-------
model_map
    Single source of truth mapping ClawBench ``(base_url, model_name, api_type)``
    to a LiteLLM ``provider/model`` string (shared by both directions).
export
    ``clawbench-export-harbor`` console script: convert a ClawBench
    ``test-cases/v2/<case>/task.json`` into a Harbor task directory.
verify
    ``python -m clawbench.harbor.verify``: the reward shim run by the Harbor
    verifier (``tests/test.sh``); reuses ClawBench's pure-Python Stage-1 +
    Stage-2 scoring and writes Harbor's ``reward.txt``.
agent
    ``ClawbenchHarnessAgent``: a Harbor ``BaseAgent`` that boots the ClawBench
    in-container services and runs an existing ClawBench harness.
parity
    ``clawbench-harbor-parity`` console script: run one cell natively and via
    Harbor and diff the scoring outcome.
"""

__all__: list[str] = []
