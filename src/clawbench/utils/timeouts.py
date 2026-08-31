"""Host-side deadlines shared by the single-run and batch drivers.

Kept in `utils` because `batch.py` needs the same numbers `run_support.docker`
does, and importing that module would drag in `run_support.config`, which
resolves a container engine at import time and exits when neither Docker nor
Podman is installed. `batch.py` must stay importable without one.
"""

# Head-room over the in-container watchdog (entrypoint.sh's MAX_WAIT) before
# the host kills the container itself. Only reached when that watchdog never
# fires: entrypoint crash, wedged Chromium, engine hiccup, zombie container.
HOST_TIMEOUT_GRACE_S = 300

# Head-room over a run's own host-side deadline, covering the work that happens
# outside docker_wait: image pull, result copy, judge call, upload. Larger than
# HOST_TIMEOUT_GRACE_S so clawbench-run reports its own timeout first and the
# batch bound stays a backstop for a child process that is itself wedged.
BATCH_JOB_GRACE_S = 900

# How long a wedged clawbench-run gets to tear itself down after SIGTERM
# before the batch escalates to SIGKILL. Its handler raises KeyboardInterrupt
# and unwinds through `finally: docker_rm(container)`, which also deletes the
# disposable mailbox and the browser runtime, so this covers a few short
# subprocess and network calls rather than any agent work.
JOB_KILL_GRACE_S = 60

# Fallback when a task file has no readable time_limit.
DEFAULT_TIME_LIMIT_S = 1800
