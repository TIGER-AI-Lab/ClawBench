"""Shared timing constants for the Harbor-as-runner integration.

Kept harbor-free (no ``import harbor``) so the export tool
(``clawbench-export-harbor``) can reuse them without requiring the Harbor
runtime to be installed on the host that only *produces* task dirs.
"""

from __future__ import annotations

# /run-harness.sh self-stops its agent at TIME_LIMIT_S, then spends ~20s on
# mandatory cleanup (kill agent, promote transcript, 15s grace recording, stop
# recording). Both the agent's environment.exec() timeout AND Harbor's outer
# [agent].timeout_sec must exceed TIME_LIMIT_S by at least this grace, or the
# harness is killed mid-cleanup -- aborting the trial before the verifier runs,
# so no reward is ever written for a run that hits its time limit.
HARNESS_CLEANUP_GRACE_S = 60
