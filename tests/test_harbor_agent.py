"""Tests for clawbench.harbor.agent (the Harbor-as-runner ClawbenchHarnessAgent).

These cover the runner -> harness model-env contract: how a Harbor
``provider/model`` string is translated into the ``MODEL_NAME`` / ``BASE_URL`` /
``API_TYPE`` / ``API_KEY(S)`` env vars the in-container harness consumes, and the
diagnostics that surface an inner model/credential failure.
"""

from __future__ import annotations

import asyncio
from pathlib import Path
from types import SimpleNamespace

import pytest

from clawbench.harbor import model_map as mm
from clawbench.harbor.agent import ClawbenchHarnessAgent


def _agent(tmp_path: Path, model: str, **kwargs) -> ClawbenchHarnessAgent:
    return ClawbenchHarnessAgent(tmp_path, model_name=model, **kwargs)


def test_gemini_default_routes_through_openai_compat(tmp_path: Path) -> None:
    """gemini/* must resolve to the OpenAI-compat endpoint, not the native root.

    Regression guard: with ``google-generative-ai`` the shared mapping sets
    ``api_base=None`` (native ``generateContent``), discarding the
    ``/v1beta/openai`` base ClawBench's keys are issued for -> auth failure / 0
    actions. The runner must emit ``openai-completions`` so the base is forwarded.
    """
    agent = _agent(tmp_path, "gemini/gemini-3.5-flash", api_key="k", harness="harbor")
    env = agent._resolve_model_env()

    assert env["MODEL_NAME"] == "gemini-3.5-flash"
    assert env["BASE_URL"] == "https://generativelanguage.googleapis.com/v1beta/openai"
    assert env["API_TYPE"] == "openai-completions"
    assert env["API_TYPE"] != "google-generative-ai"  # the bug
    assert env["API_KEY"] == "k"
    assert env["API_KEYS"] == '["k"]'

    # The harness feeds these through the shared mapping; confirm it lands on the
    # OpenAI-compat path (openai/<model> with the /v1beta/openai api_base) rather
    # than LiteLLM's native gemini provider (api_base=None -> generateContent).
    mapped = mm.build_litellm_model(
        env["BASE_URL"], env["MODEL_NAME"], env["API_TYPE"], "k"
    )
    assert mapped.model == "openai/gemini-3.5-flash"
    assert mapped.api_base == "https://generativelanguage.googleapis.com/v1beta/openai"
    assert mapped.env == {"OPENAI_API_KEY": "k"}


def test_explicit_base_url_and_api_type_override_provider_defaults(
    tmp_path: Path,
) -> None:
    agent = _agent(
        tmp_path,
        "openai/glm-5.1",
        api_key="k",
        base_url="https://api.z.ai/api/paas/v4",
        api_type="openai-completions",
    )
    env = agent._resolve_model_env()
    assert env["BASE_URL"] == "https://api.z.ai/api/paas/v4"
    assert env["API_TYPE"] == "openai-completions"
    assert env["MODEL_NAME"] == "glm-5.1"


def test_anthropic_provider_default(tmp_path: Path) -> None:
    agent = _agent(tmp_path, "anthropic/claude-haiku-4-5", api_key="k")
    env = agent._resolve_model_env()
    assert env["BASE_URL"] == "https://api.anthropic.com"
    assert env["API_TYPE"] == "anthropic-messages"


def test_unknown_provider_without_overrides_raises(tmp_path: Path) -> None:
    agent = _agent(tmp_path, "mystery/model-x", api_key="k")
    with pytest.raises(ValueError, match="unknown provider"):
        agent._resolve_model_env()


def test_missing_api_key_raises(tmp_path: Path) -> None:
    agent = _agent(tmp_path, "gemini/gemini-3.5-flash")
    with pytest.raises(ValueError, match="no API key"):
        agent._resolve_model_env()


class _FakeEnv:
    """Minimal async environment returning a canned exec result."""

    def __init__(self, stdout: str) -> None:
        self._stdout = stdout
        self.commands: list[str] = []

    async def exec(self, command: str, **_kwargs):  # noqa: ANN003
        self.commands.append(command)
        return SimpleNamespace(stdout=self._stdout, stderr="", return_code=0)


def test_collect_harness_diagnostics_parses_reason_and_stderr(tmp_path: Path) -> None:
    agent = _agent(tmp_path, "gemini/gemini-3.5-flash", api_key="k")
    blob = (
        "harbor_failed\n"
        "<<<STDERR>>>\n"
        "Unknown Error in LLM interaction: litellm.AuthenticationError: "
        "API key not valid.\n"
    )
    env = _FakeEnv(blob)
    reason, inner = asyncio.run(agent._collect_harness_diagnostics(env))  # type: ignore[arg-type]
    assert reason == "harbor_failed"
    assert "AuthenticationError" in inner
    # It reads the persisted reason + the surviving /tmp stderr tail.
    assert "/data/.stop-reason" in env.commands[0]
    assert "/tmp/harbor-stderr.log" in env.commands[0]


def test_collect_harness_diagnostics_empty_when_no_artifacts(tmp_path: Path) -> None:
    agent = _agent(tmp_path, "gemini/gemini-3.5-flash", api_key="k")
    env = _FakeEnv("<<<STDERR>>>")
    reason, inner = asyncio.run(agent._collect_harness_diagnostics(env))  # type: ignore[arg-type]
    assert reason == ""
    assert inner == ""
