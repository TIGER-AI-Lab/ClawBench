#!/usr/bin/env python3
"""ClawBench driver for the Harbor agent framework (Terminus 2 agent).

Harbor (https://github.com/harbor-framework/harbor, Apache-2.0) is an
agent-evaluation framework. Its only first-party LLM agent is **Terminus 2**, a
terminal agent: its action space is shell keystrokes sent to a tmux pane and its
observation is the terminal screen. Harbor itself ships no browser/CDP agent.

ClawBench tasks are browser tasks, so this driver bridges the two faithfully:

* It runs the *real* Terminus 2 agent (real Harbor `LiteLLM` backend, real tmux
  loop) inside the already-running ClawBench container.
* It gives Terminus a ``LocalEnvironment`` (a minimal ``BaseEnvironment`` whose
  ``exec`` runs commands locally) instead of having Harbor spin up its own
  sandbox — the ClawBench container *is* the sandbox.
* Inside Terminus' tmux shell it exposes the ``agent-browser`` CLI (the same
  CDP-attaching browser tool the hermes harness uses), pre-pointed at the shared
  Chrome at http://127.0.0.1:9222. Terminus drives the browser via that CLI, so
  every action flows through CDP and is captured by the ClawBench recorder
  extension into /data/actions.jsonl, and the eval interceptor's
  /data/.stop-requested signal still works.

The model/provider mapping mirrors the pi harness (Harbor and pi both use
LiteLLM): ``gemini/<model>`` / ``openai/<model>`` / ``anthropic/<model>`` /
``openrouter/<model>`` plus an ``api_base`` when a custom base_url is supplied.
"""

import asyncio
import json
import os
import subprocess
import sys
from pathlib import Path

from harbor.agents.terminus_2.terminus_2 import Terminus2
from harbor.environments.base import BaseEnvironment, ExecResult
from harbor.llms.base import LLMBackend
from harbor.models.agent.context import AgentContext

DATA_DIR = Path("/data")
LOGS_DIR = Path("/logs/agent")
CDP_URL = "http://127.0.0.1:9222"


class LocalEnvironment(BaseEnvironment):
    """A ``BaseEnvironment`` that executes everything in the local container.

    Harbor's built-in environments (docker, daytona, modal, ...) each launch
    their own sandbox. ClawBench has already started the container (with Chrome
    + recorder extension), so we just run commands here. Only the abstract
    surface that Terminus 2 / TmuxSession touch is implemented; the rest raise
    ``NotImplementedError`` so misuse is obvious.
    """

    def __init__(self) -> None:
        # BaseEnvironment.__init__ expects a task-definition object; Terminus
        # never reads it for a plain terminal task, so bypass the parent
        # constructor and set only the attributes the agent actually uses.
        self.default_user = None
        self.session_id = "clawbench-harbor"

    @staticmethod
    def type() -> str:
        return "local"

    def _validate_definition(self) -> None:  # pragma: no cover - nothing to check
        return None

    async def start(self, force_build: bool = False) -> None:
        return None

    async def stop(self, delete: bool = False) -> None:
        return None

    async def exec(
        self,
        command: str,
        cwd: str | None = None,
        env: dict[str, str] | None = None,
        timeout_sec: int | None = None,
        user: str | int | None = None,
    ) -> ExecResult:
        # ``user`` is ignored: the ClawBench container already runs as root.
        proc_env = {**os.environ, **(env or {})}
        try:
            proc = await asyncio.create_subprocess_exec(
                "bash",
                "-lc",
                command,
                cwd=cwd,
                env=proc_env,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
            )
            stdout, stderr = await asyncio.wait_for(
                proc.communicate(), timeout=timeout_sec
            )
            return ExecResult(
                stdout=stdout.decode("utf-8", "replace"),
                stderr=stderr.decode("utf-8", "replace"),
                return_code=proc.returncode if proc.returncode is not None else -1,
            )
        except asyncio.TimeoutError:
            try:
                proc.kill()
            except ProcessLookupError:
                pass
            return ExecResult(stdout="", stderr="command timed out", return_code=124)

    async def upload_file(self, source_path, target_path: str) -> None:
        Path(target_path).parent.mkdir(parents=True, exist_ok=True)
        Path(target_path).write_bytes(Path(source_path).read_bytes())

    async def upload_dir(self, source_dir, target_dir: str) -> None:
        import shutil

        shutil.copytree(source_dir, target_dir, dirs_exist_ok=True)

    async def download_file(self, source_path: str, target_path) -> None:
        Path(target_path).parent.mkdir(parents=True, exist_ok=True)
        Path(target_path).write_bytes(Path(source_path).read_bytes())

    async def download_dir(self, source_dir: str, target_dir) -> None:
        import shutil

        shutil.copytree(source_dir, target_dir, dirs_exist_ok=True)


def _pick_api_key() -> str:
    keys_json = os.environ.get("API_KEYS", "")
    if keys_json:
        try:
            parsed = json.loads(keys_json)
            if parsed:
                if len(parsed) > 1:
                    print(
                        f"WARN: Harbor does not rotate keys; using first of {len(parsed)}",
                        flush=True,
                    )
                return parsed[0]
        except json.JSONDecodeError:
            pass
    single = os.environ.get("API_KEY", "")
    if single:
        return single
    raise SystemExit("ERROR: no API key provided (API_KEYS or API_KEY)")


def _resolve_openrouter_model(base_url: str, model_name: str, key: str) -> str:
    """OpenRouter wants the canonical provider-qualified id (e.g. ``x-ai/grok-4``)."""
    import urllib.request

    try:
        req = urllib.request.Request(
            f"{base_url}/models", headers={"Authorization": f"Bearer {key}"}
        )
        resp = json.loads(urllib.request.urlopen(req, timeout=10).read())
        for m in resp.get("data", []):
            mid = m.get("id", "")
            if mid == model_name or mid.endswith(f"/{model_name}"):
                return mid
    except Exception as e:  # noqa: BLE001 - best effort, fall back to bare name
        print(f"WARN: could not resolve OpenRouter model ID: {e}", flush=True)
    return model_name


def build_litellm_model(base_url: str, model_name: str, api_type: str, key: str):
    """Map ClawBench (base_url, model_name, api_type) to LiteLLM (model, api_base, env).

    Returns ``(litellm_model, api_base, env_vars)``. ``env_vars`` are the
    provider credentials LiteLLM reads from the process environment.

    The canonical mapping lives in ``clawbench.harbor.model_map`` so the runner
    direction shares the exact same logic. That package is not installed in this
    minimal harness container, so when the import fails we fall back to the inline
    copy below — kept byte-for-byte equivalent and covered by the model_map tests.

    Gemini note: LiteLLM's native ``gemini/<model>`` provider talks to Google's
    native generative-language API using ``GEMINI_API_KEY`` and does NOT post to
    ``/chat/completions`` — so it sidesteps the 404 that hits raw OpenAI-compat
    callers on the native Gemini root. A custom Gemini base_url (e.g. an
    OpenAI-compat proxy) is forwarded as ``api_base``.
    """
    try:
        from clawbench.harbor.model_map import build_litellm_model as _shared
    except ImportError:
        pass
    else:
        mapped = _shared(base_url, model_name, api_type, key)
        return mapped.model, mapped.api_base, mapped.env

    base_url = base_url.rstrip("/")
    env: dict[str, str] = {}

    if "openrouter.ai" in base_url:
        resolved = _resolve_openrouter_model(base_url, model_name, key)
        env["OPENROUTER_API_KEY"] = key
        env["OPENROUTER_API_BASE"] = base_url
        return f"openrouter/{resolved}", None, env

    if api_type == "anthropic-messages":
        env["ANTHROPIC_API_KEY"] = key
        api_base = (
            None if base_url.startswith("https://api.anthropic.com") else base_url
        )
        return f"anthropic/{model_name}", api_base, env

    if api_type == "google-generative-ai":
        # An OpenAI-compatible Gemini endpoint (``/v1beta/openai`` or any ``/openai``
        # base) must route through LiteLLM's *openai* provider so the api_base is
        # preserved (POST ``/chat/completions``). LiteLLM's native ``gemini``
        # provider would drop the api_base and POST ``generateContent`` -- the
        # endpoint these OpenAI-compat keys are NOT issued for (silent auth failure
        # / 0 actions). This mirrors model_map.build_litellm_model exactly so the
        # fallback stays byte-for-byte equivalent to the shared mapping.
        if "/v1beta/openai" in base_url or base_url.endswith("/openai"):
            env["OPENAI_API_KEY"] = key
            return f"openai/{model_name}", base_url, env
        env["GEMINI_API_KEY"] = key
        env["GOOGLE_API_KEY"] = key
        # Native Google root is the default for LiteLLM's gemini provider; only
        # override when a non-default (e.g. proxy) base_url is configured.
        api_base = (
            None
            if base_url.startswith("https://generativelanguage.googleapis.com")
            else base_url
        )
        return f"gemini/{model_name}", api_base, env

    if api_type in ("openai-completions", "openai-responses"):
        env["OPENAI_API_KEY"] = key
        return f"openai/{model_name}", base_url, env

    raise SystemExit(f"ERROR: unsupported api_type for harbor harness: {api_type}")


# Reasoning-effort levels accepted by Terminus 2 / LiteLLM.
_EFFORT_MAP = {
    "minimal": "minimal",
    "low": "low",
    "medium": "medium",
    "adaptive": "medium",
    "high": "high",
    "xhigh": "high",
}


def _reasoning_effort() -> str | None:
    thinking = (os.environ.get("THINKING_LEVEL") or "").lower()
    if not thinking or thinking == "off":
        return None
    return _EFFORT_MAP.get(thinking, "medium")


def _browser_instruction(task: str) -> str:
    """Prefix the task with a guide teaching Terminus to drive the CDP browser.

    Terminus only knows how to run shell commands. The ``ab`` wrapper (installed
    by the harness) is the ``agent-browser`` CLI pinned to ``--cdp 9222``, so it
    always attaches to the shared ClawBench Chrome over the Chrome DevTools
    Protocol rather than launching a second browser the recorder cannot see.
    The command names below match agent-browser exactly (``open``/``snapshot``/
    ``click``/``fill``), so the model does not have to guess.
    """
    return f"""You are completing a web-browsing task. You do NOT have a desktop or \
mouse; you act ONLY by running shell commands in this terminal.

A Chromium browser is already running and visible to the grader. Control it with \
the `ab` command (the agent-browser CLI, already attached to that exact browser \
over the Chrome DevTools Protocol at {CDP_URL}). Run `ab --help` to see all \
subcommands. Typical flow:

  ab open "https://example.com"   # navigate to a URL
  ab snapshot -i                  # read interactive elements with @refs
  ab click @e5                    # click an element by its @ref from the snapshot
  ab fill @e3 "text"              # clear and type into a field
  ab press Enter                  # press a key to submit
  ab get text @e1                 # read an element's text
  ab screenshot                   # optional visual check

IMPORTANT RULES:
- The `ab` command is ALREADY connected to the shared Chrome over CDP. Do NOT \
add a --cdp flag, do NOT run `agent-browser install`, do NOT launch your own \
browser, and do NOT curl/wget pages.
- ALWAYS act through the `ab` command so the grader sees your actions.
- Use a duration of 2-3 seconds after `ab open`/`ab click` so the page can load \
before your next command. If a command's output looks empty or incomplete, run \
`ab snapshot -i` again to re-read the page rather than assuming it failed.
- Re-run `ab snapshot -i` after each `open`/`click` to get fresh @refs before \
acting; @refs change when the page changes.
- You can chain steps in one command with &&, e.g. \
`ab fill @e1 "a@b.com" && ab fill @e2 "pw" && ab click @e3`.
- Do NOT mark the task complete until you have actually performed the required \
browser actions and verified the result with `ab snapshot -i` or `ab get text`.
- When the task is genuinely complete, stop and give a short final summary.

TASK:
{task}
"""


async def _run_agent(litellm_model, api_base, instruction, reasoning_effort) -> None:
    LOGS_DIR.mkdir(parents=True, exist_ok=True)
    DATA_DIR.mkdir(parents=True, exist_ok=True)

    env = LocalEnvironment()
    agent = Terminus2(
        logs_dir=LOGS_DIR,
        model_name=litellm_model,
        api_base=api_base,
        llm_backend=LLMBackend.LITELLM,
        reasoning_effort=reasoning_effort,
        # Keep the terminal pane wide enough to read web snapshots; disable
        # asciinema recording (ClawBench records the browser, not the terminal).
        tmux_pane_width=200,
        tmux_pane_height=50,
        record_terminal_session=False,
        # The `ab` wrapper already pins agent-browser to the shared Chrome with
        # --cdp 9222. Do NOT also set AGENT_BROWSER_AUTO_CONNECT: agent-browser
        # rejects --cdp and --auto-connect used together.
        extra_env={"BROWSER_CDP_URL": CDP_URL},
    )

    context = AgentContext()
    await agent.setup(environment=env)
    await agent.run(
        instruction=_browser_instruction(instruction),
        environment=env,
        context=context,
    )
    print(
        "Harbor/Terminus finished: "
        f"in={context.n_input_tokens} out={context.n_output_tokens} "
        f"cost={context.cost_usd}",
        flush=True,
    )


def main() -> None:
    base_url = os.environ.get("BASE_URL")
    model_name = os.environ.get("MODEL_NAME")
    api_type = os.environ.get("API_TYPE")
    instruction = os.environ.get("INSTRUCTION")
    if not base_url or not model_name or not api_type:
        raise SystemExit("ERROR: BASE_URL, MODEL_NAME, and API_TYPE must be set")
    if not instruction:
        raise SystemExit("ERROR: INSTRUCTION must be set")

    key = _pick_api_key()
    litellm_model, api_base, provider_env = build_litellm_model(
        base_url, model_name, api_type, key
    )
    os.environ.update(provider_env)

    print(
        f"Harbor config: agent=terminus-2, model={litellm_model}, "
        f"api_base={api_base or '(provider default)'}, "
        f"reasoning_effort={_reasoning_effort() or 'none'}, browser_cdp={CDP_URL}",
        flush=True,
    )

    try:
        asyncio.run(
            _run_agent(litellm_model, api_base, instruction, _reasoning_effort())
        )
    except Exception as e:  # noqa: BLE001 - surface failure to the watchdog
        print(f"Harbor agent error: {e}", file=sys.stderr, flush=True)
        (DATA_DIR / ".stop-reason").write_text("harbor_failed")
        raise


if __name__ == "__main__":
    main()
