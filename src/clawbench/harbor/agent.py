"""A Harbor agent that runs an existing ClawBench harness (scope b).

``harbor run --agent-import-path clawbench.harbor.agent:ClawbenchHarnessAgent``
runs a ClawBench harness as a Harbor agent. The single prebuilt
``clawbench-harbor-task`` image always runs harbor's ``/run-harness.sh``, so the
only supported value today is ``--ak harness=harbor``; any other value raises (a
``--ak harness=hermes`` could not actually select a different harness from the one
baked image, so it must not silently mis-run). Per-harness images are future work.
The harness is passed as an agent kwarg because Harbor's import-path mode only
forwards ``--ak key=value`` kwargs to the agent constructor. Do **not** pass
``--agent`` — that flag is typed as the ``AgentName`` enum
(oracle/terminus/hermes/...), so ``--agent clawbench`` fails validation.
``--agent-import-path`` alone sets ``config.agent.import_path``:

    harbor run --path <task-dir> \
      --agent-import-path clawbench.harbor.agent:ClawbenchHarnessAgent \
      --ak harness=harbor --ak api_key=<API_KEY> \
      --ve JUDGE_API_KEY=<JUDGE_KEY> \
      --model gemini/gemini-3.5-flash --env docker

Lifecycle inside the Harbor-managed container (CMD overridden to ``sleep
infinity``):

* ``setup()`` boots the ClawBench services (Xvfb, extension-server, Chrome+CDP,
  socat, noVNC) by running ``/entrypoint.sh`` with ``SERVICES_ONLY=1`` in the
  background, then waits for the Chrome CDP endpoint to come up.
* ``run()`` translates Harbor's ``provider/model`` to the ClawBench
  ``MODEL_NAME``/``BASE_URL``/``API_TYPE``/``API_KEYS`` env contract (via the
  shared ``model_map``), exports ``INSTRUCTION``/``TIME_LIMIT_S``, then runs the
  selected harness' ``/run-harness.sh``. The in-container interceptor writes
  ``/data/interception.json`` identically to the native runner, which the Harbor
  verifier (``clawbench.harbor.verify``) then scores.
"""

from __future__ import annotations

import json
import os
from pathlib import Path

from harbor.agents.base import BaseAgent
from harbor.environments.base import BaseEnvironment
from harbor.models.agent.context import AgentContext

from clawbench.harbor.model_map import build_litellm_model

# Map ClawBench LiteLLM provider prefix back to a (BASE_URL, API_TYPE) contract.
# This is the inverse of model_map.build_litellm_model and is used to translate a
# Harbor `provider/model` string into the env vars the harnesses read.
#
# Gemini note: ClawBench drives Gemini over its **OpenAI-compatible** endpoint
# (``/v1beta/openai/chat/completions``) and its credentials are issued for that
# path -- exactly as the Harbor verifier's judge does (the judge api_type is
# derived via ``model_map.judge_api_type`` -> ``openai-completions``). We therefore
# map gemini to ``openai-completions`` so ``build_litellm_model`` forwards the
# ``/v1beta/openai`` base as ``api_base`` (LiteLLM ``openai/<model>`` -> POST
# ``/chat/completions``). Using ``google-generative-ai`` instead would make
# ``build_litellm_model`` set ``api_base=None`` (its base starts with
# ``generativelanguage.googleapis.com``), silently DISCARDING the OpenAI-compat
# base and routing to LiteLLM's native Gemini provider (``generateContent``) -- the
# endpoint ClawBench's keys are *not* issued for, which fails auth and produces a
# 0-action ``infra_failure`` (the bug this maps around).
_PROVIDER_DEFAULTS: dict[str, tuple[str, str]] = {
    "gemini": (
        "https://generativelanguage.googleapis.com/v1beta/openai",
        "openai-completions",
    ),
    "anthropic": ("https://api.anthropic.com", "anthropic-messages"),
    "openai": ("https://api.openai.com/v1", "openai-completions"),
    "openrouter": ("https://openrouter.ai/api/v1", "openai-completions"),
}

# The only harness the single prebuilt clawbench-harbor-task image can run. The
# `harness` kwarg is validated against this in __init__ (see M6): a different value
# cannot select a different harness from the one baked image, so it is rejected.
DEFAULT_HARNESS = "harbor"
CDP_VERSION_URL = "http://127.0.0.1:9222/json/version"
# /run-harness.sh self-stops its agent at TIME_LIMIT_S, then spends ~20s on
# mandatory cleanup (kill agent, promote transcript, 15s grace recording, stop
# recording). The agent's exec() timeout must exceed TIME_LIMIT_S by at least this
# grace, or it kills the harness mid-cleanup -- aborting the trial before the
# verifier runs, so no reward is ever written for a run that hits its time limit.
HARNESS_CLEANUP_GRACE_S = 60


class ClawbenchHarnessAgent(BaseAgent):
    """Run a ClawBench harness as a Harbor agent."""

    SUPPORTS_ATIF = False
    SUPPORTS_WINDOWS = False

    def __init__(
        self,
        *args,
        harness: str | None = None,
        base_url: str | None = None,
        api_type: str | None = None,
        api_key: str | None = None,
        time_limit_s: int | None = None,
        thinking_level: str | None = None,
        temperature: str | None = None,
        max_tokens: str | None = None,
        **kwargs,
    ) -> None:
        super().__init__(*args, **kwargs)
        self.harness = harness or os.environ.get("CLAWBENCH_HARNESS") or DEFAULT_HARNESS
        if self.harness != DEFAULT_HARNESS:
            # The single prebuilt clawbench-harbor-task image always runs harbor's
            # /run-harness.sh, so the `harness` kwarg cannot actually select a
            # different harness -- it would silently run the wrong one. Fail loudly
            # until per-harness images exist (future work).
            raise ValueError(
                f"harness={self.harness!r} is not supported: the single prebuilt "
                f"clawbench-harbor-task image always runs harbor's /run-harness.sh. "
                f"Only --ak harness={DEFAULT_HARNESS!r} is supported "
                f"(per-harness images are future work)."
            )
        # Allow overrides; otherwise derived from the model provider / env.
        self._base_url = base_url or os.environ.get("CLAWBENCH_BASE_URL")
        self._api_type = api_type or os.environ.get("CLAWBENCH_API_TYPE")
        self._api_key = api_key or os.environ.get("CLAWBENCH_API_KEY")
        self._time_limit_s = time_limit_s
        # Optional model knobs, mirroring the native runner's docker_run env
        # contract (these come from models.yaml natively; here from --ak kwargs).
        # The harbor harness reads THINKING_LEVEL (-> Terminus reasoning_effort);
        # TEMPERATURE/MAX_TOKENS are consumed by the LiteLLM-backed harnesses too.
        self._thinking_level = thinking_level or os.environ.get(
            "CLAWBENCH_THINKING_LEVEL"
        )
        self._temperature = temperature
        self._max_tokens = max_tokens

    @staticmethod
    def name() -> str:
        return "clawbench"

    def version(self) -> str | None:
        try:
            from importlib.metadata import version

            return version("clawbench-eval")
        except Exception:  # noqa: BLE001
            return None

    # ------------------------------------------------------------------ setup
    async def setup(self, environment: BaseEnvironment) -> None:
        """Wait for the ClawBench services (Chrome+CDP); start them if needed.

        The clawbench-harbor-task image bakes ``SERVICES_ONLY=1`` so its
        ``ENTRYPOINT`` auto-boots Chrome/CDP/extension-server even under Harbor's
        ``sleep infinity`` CMD. We first wait for readiness; only if the image was
        built without that hook do we start the services ourselves.
        """
        if await self._wait_ready(environment, timeout=15):
            self.logger.info("ClawBench services already running (CDP ready).")
            return

        self.logger.info("Starting ClawBench services (SERVICES_ONLY)...")
        await environment.exec(
            "mkdir -p /data && "
            "SERVICES_ONLY=1 nohup /entrypoint.sh > /data/services.log 2>&1 &"
        )
        if not await self._wait_ready(environment, timeout=60):
            log = await environment.exec("tail -40 /data/services.log 2>/dev/null")
            self.logger.warning(
                "ClawBench services not ready: %s", log.stdout or log.stderr
            )
            raise RuntimeError("ClawBench services failed to start (no Chrome CDP)")

    async def _wait_ready(self, environment: BaseEnvironment, timeout: int) -> bool:
        """Poll for the services-ready marker (if present) and a live Chrome CDP."""
        ready_cmd = (
            f"for i in $(seq 1 {timeout}); do "
            f"  if curl -sf {CDP_VERSION_URL} >/dev/null 2>&1; then "
            "    echo READY; exit 0; "
            "  fi; sleep 1; "
            "done; echo TIMEOUT; exit 1"
        )
        result = await environment.exec(ready_cmd)
        return "READY" in (result.stdout or "")

    # -------------------------------------------------------------------- run
    def _resolve_model_env(self) -> dict[str, str]:
        """Translate the Harbor ``provider/model`` into ClawBench env vars."""
        if not self.model_name:
            raise ValueError("model_name is required (use --model provider/model)")

        provider = self._parsed_model_provider
        bare_model = self._parsed_model_name or self.model_name

        # API key: explicit kwarg/env, else the provider's standard env var.
        api_key = self._api_key
        if not api_key and provider:
            for env_var in (
                f"{provider.upper().replace('-', '_')}_API_KEY",
                "GEMINI_API_KEY",
                "OPENAI_API_KEY",
                "ANTHROPIC_API_KEY",
                "OPENROUTER_API_KEY",
            ):
                if os.environ.get(env_var):
                    api_key = os.environ[env_var]
                    break
        if not api_key:
            raise ValueError(
                "no API key found for the model; pass --ak api_key=... or set the "
                "provider env var (e.g. GEMINI_API_KEY)"
            )

        base_url = self._base_url
        api_type = self._api_type
        if not (base_url and api_type):
            if provider not in _PROVIDER_DEFAULTS:
                raise ValueError(
                    f"unknown provider {provider!r}; pass --ak base_url=... "
                    "--ak api_type=..."
                )
            default_base, default_type = _PROVIDER_DEFAULTS[provider]
            base_url = base_url or default_base
            api_type = api_type or default_type

        # Validate the mapping is coherent (raises on unsupported combos) and
        # reuse the canonical provider credential env if the harness wants it.
        build_litellm_model(base_url, bare_model, api_type, api_key)

        env = {
            "MODEL_NAME": bare_model,
            "BASE_URL": base_url,
            "API_TYPE": api_type,
            # json.dumps so a key containing quotes/backslashes still yields valid
            # JSON (the harness parses API_KEYS with json.loads).
            "API_KEYS": json.dumps([api_key]),
            "API_KEY": api_key,
        }
        return env

    async def run(
        self,
        instruction: str,
        environment: BaseEnvironment,
        context: AgentContext,
    ) -> None:
        env = self._resolve_model_env()
        env["INSTRUCTION"] = instruction
        if self._time_limit_s:
            env["TIME_LIMIT_S"] = str(self._time_limit_s)
        # Forward optional model knobs only when set, mirroring the native runner
        # (docker_run adds these conditionally). THINKING_LEVEL is what gemini-style
        # "thinking" models need; without it the harbor harness runs with
        # reasoning_effort=none (still valid, just not at parity with the native run).
        if self._thinking_level:
            env["THINKING_LEVEL"] = str(self._thinking_level)
        if self._temperature is not None:
            env["TEMPERATURE"] = str(self._temperature)
        if self._max_tokens is not None:
            env["MAX_TOKENS"] = str(self._max_tokens)

        # Make the personal-info bundle available where the harnesses expect it.
        await environment.exec(
            "if [ -d /clawbench/my-info ] && [ ! -d /my-info ]; then "
            "cp -r /clawbench/my-info /my-info; fi || true"
        )

        run_script = "/run-harness.sh"
        # Only harness="harbor" reaches here (validated in __init__): the single
        # prebuilt image installs its runner at /run-harness.sh. Recorded for
        # clarity in the trial metadata below.
        self.logger.info(
            "Running ClawBench harness=%s model=%s", self.harness, self.model_name
        )

        # Give the harness room to finish its self-stop cleanup before exec() kills
        # it; otherwise a run that reaches TIME_LIMIT_S is killed mid-cleanup and
        # the verifier never runs (no reward written). None -> no exec timeout.
        exec_timeout = (
            self._time_limit_s + HARNESS_CLEANUP_GRACE_S if self._time_limit_s else None
        )
        result = await environment.exec(
            f"{run_script}",
            env=env,
            timeout_sec=exec_timeout,
        )
        # Surface the harness output; the real signal is /data/interception.json.
        self.logger.info("harness exit=%s", getattr(result, "return_code", "?"))
        if context.metadata is None:
            context.metadata = {}
        context.metadata["clawbench_harness"] = self.harness
        context.metadata["clawbench_run_script"] = run_script

        # Surface the inner harness diagnostics so a model/credential error is not
        # silently swallowed (the run produced reward 0 with stop_reason
        # "harbor_failed" and no visible cause). /run-harness.sh records a
        # machine-readable reason in /data/.stop-reason and redirects the agent's
        # stdout/stderr to /tmp/harbor-*.log; it deletes /data/*.log on exit but
        # leaves /tmp/* and /data/.stop-reason, so read those here. We read after
        # the run (not just on a non-zero exit) because the watchdog wrapper exits 0
        # even when the inner agent died on its first LLM call.
        stop_reason, inner_err = await self._collect_harness_diagnostics(environment)
        if stop_reason:
            context.metadata["clawbench_stop_reason"] = stop_reason
        failed = bool(inner_err) or (stop_reason or "").endswith("_failed")
        if inner_err:
            log = self.logger.warning if failed else self.logger.info
            log(
                "ClawBench harness stop_reason=%s; inner error:\n%s",
                stop_reason or "?",
                inner_err,
            )
        elif failed:
            self.logger.warning("ClawBench harness stop_reason=%s", stop_reason)

    async def _collect_harness_diagnostics(
        self, environment: BaseEnvironment
    ) -> tuple[str, str]:
        """Read the inner harness stop-reason and any captured stderr tail.

        Returns ``(stop_reason, inner_error_tail)``; either may be empty.
        """
        diag = await environment.exec(
            "cat /data/.stop-reason 2>/dev/null; "
            "echo '<<<STDERR>>>'; tail -n 40 /tmp/harbor-stderr.log 2>/dev/null"
        )
        blob = diag.stdout or ""
        reason, _, stderr_tail = blob.partition("<<<STDERR>>>")
        return reason.strip(), stderr_tail.strip()

    def populate_context_post_run(self, context: AgentContext) -> None:
        """Best-effort: surface the synced agent-messages count if present."""
        messages = self.logs_dir.parent / "agent-messages.jsonl"
        if not messages.exists():
            messages = Path("/data/agent-messages.jsonl")
        if context.metadata is None:
            context.metadata = {}
        if messages.exists():
            try:
                n = sum(1 for line in messages.read_text().splitlines() if line.strip())
            except OSError:
                n = 0
            context.metadata["clawbench_agent_messages"] = n
