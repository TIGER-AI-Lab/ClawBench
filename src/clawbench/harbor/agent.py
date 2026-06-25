"""A Harbor agent that runs an existing ClawBench harness (scope b).

``harbor run --agent-import-path clawbench.harbor.agent:ClawbenchHarnessAgent``
exposes every browser ClawBench harness (harbor/hermes/pi/openclaw/browser-use/
claw-code/opencode/...) as a Harbor agent. The harness is selected via an agent
kwarg, because Harbor's import-path mode only forwards ``--ak key=value`` kwargs
to the agent constructor. Do **not** pass ``--agent`` — that flag is typed as the
``AgentName`` enum (oracle/terminus/hermes/...), so ``--agent clawbench`` fails
validation. ``--agent-import-path`` alone sets ``config.agent.import_path``:

    harbor run --path <task-dir> \
      --agent-import-path clawbench.harbor.agent:ClawbenchHarnessAgent \
      --ak harness=hermes --ak api_key=<API_KEY> \
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

import os
from pathlib import Path

from harbor.agents.base import BaseAgent
from harbor.environments.base import BaseEnvironment
from harbor.models.agent.context import AgentContext

from clawbench.harbor.model_map import build_litellm_model

# Map ClawBench LiteLLM provider prefix back to a (BASE_URL, API_TYPE) contract.
# This is the inverse of model_map.build_litellm_model and is used to translate a
# Harbor `provider/model` string into the env vars the harnesses read.
_PROVIDER_DEFAULTS: dict[str, tuple[str, str]] = {
    "gemini": (
        "https://generativelanguage.googleapis.com/v1beta/openai",
        "google-generative-ai",
    ),
    "anthropic": ("https://api.anthropic.com", "anthropic-messages"),
    "openai": ("https://api.openai.com/v1", "openai-completions"),
    "openrouter": ("https://openrouter.ai/api/v1", "openai-completions"),
}

# Harnesses known to ClawBench. Defaults to ``harbor`` (the validated path).
DEFAULT_HARNESS = "harbor"
CDP_VERSION_URL = "http://127.0.0.1:9222/json/version"


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
        **kwargs,
    ) -> None:
        super().__init__(*args, **kwargs)
        self.harness = harness or os.environ.get("CLAWBENCH_HARNESS") or DEFAULT_HARNESS
        # Allow overrides; otherwise derived from the model provider / env.
        self._base_url = base_url or os.environ.get("CLAWBENCH_BASE_URL")
        self._api_type = api_type or os.environ.get("CLAWBENCH_API_TYPE")
        self._api_key = api_key or os.environ.get("CLAWBENCH_API_KEY")
        self._time_limit_s = time_limit_s

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
            "API_KEYS": f'["{api_key}"]',
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

        # Make the personal-info bundle available where the harnesses expect it.
        await environment.exec(
            "if [ -d /clawbench/my-info ] && [ ! -d /my-info ]; then "
            "cp -r /clawbench/my-info /my-info; fi || true"
        )

        run_script = "/run-harness.sh"
        # When a non-default harness is requested we still call /run-harness.sh:
        # each harness image installs its own runner there. The `harness` kwarg
        # selects which image was baked at export time; record it for clarity.
        self.logger.info(
            "Running ClawBench harness=%s model=%s", self.harness, self.model_name
        )

        result = await environment.exec(
            f"{run_script}",
            env=env,
            timeout_sec=self._time_limit_s,
        )
        # Surface the harness output; the real signal is /data/interception.json.
        self.logger.info("harness exit=%s", getattr(result, "return_code", "?"))
        if context.metadata is None:
            context.metadata = {}
        context.metadata["clawbench_harness"] = self.harness
        context.metadata["clawbench_run_script"] = run_script

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
