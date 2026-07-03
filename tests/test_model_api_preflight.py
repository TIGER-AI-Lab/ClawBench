from __future__ import annotations

import importlib
import json
import shutil
import sys
import urllib.error
import urllib.parse
from email.message import Message
from pathlib import Path
from types import ModuleType
from typing import Any

import pytest

from clawbench.runner.run_support.api_preflight import (
    ModelApiPreflightError,
    preflight_model_api,
)


class FakeResponse:
    def __init__(self, payload: dict[str, Any]) -> None:
        self.payload = payload

    def __enter__(self) -> FakeResponse:
        return self

    def __exit__(self, *args: object) -> None:
        return None

    def read(self) -> bytes:
        return json.dumps(self.payload).encode("utf-8")


def _headers(req: Any) -> dict[str, str]:
    return dict(req.header_items())


def test_openai_chat_preflight_request(monkeypatch: pytest.MonkeyPatch) -> None:
    calls: list[tuple[Any, int]] = []

    def fake_urlopen(req: Any, timeout: int) -> FakeResponse:
        calls.append((req, timeout))
        return FakeResponse({"choices": [{"message": {"content": "OK"}}]})

    monkeypatch.setattr(
        "clawbench.runner.run_support.api_preflight.urllib.request.urlopen",
        fake_urlopen,
    )

    preflight_model_api(
        {
            "model": "test-chat",
            "base_url": "https://api.example.test/v1",
            "api_type": "openai-completions",
            "api_key": "secret-key",
        },
        timeout=7,
    )

    req, timeout = calls[0]
    payload = json.loads(req.data)
    headers = _headers(req)
    assert timeout == 7
    assert req.full_url == "https://api.example.test/v1/chat/completions"
    assert headers["Authorization"] == "Bearer secret-key"
    assert payload["model"] == "test-chat"
    assert payload["max_tokens"] == 4
    assert payload["messages"] == [{"role": "user", "content": "Reply with OK."}]


def test_openai_responses_preflight_request(monkeypatch: pytest.MonkeyPatch) -> None:
    calls: list[Any] = []

    def fake_urlopen(req: Any, timeout: int) -> FakeResponse:
        calls.append(req)
        return FakeResponse({"output_text": "OK"})

    monkeypatch.setattr(
        "clawbench.runner.run_support.api_preflight.urllib.request.urlopen",
        fake_urlopen,
    )

    preflight_model_api(
        {
            "model": "test-responses",
            "base_url": "https://api.example.test/v1",
            "api_type": "openai-responses",
            "api_key": "secret-key",
        }
    )

    req = calls[0]
    payload = json.loads(req.data)
    assert req.full_url == "https://api.example.test/v1/responses"
    assert _headers(req)["Authorization"] == "Bearer secret-key"
    assert payload == {
        "model": "test-responses",
        "input": "Reply with OK.",
        "max_output_tokens": 4,
    }


def test_anthropic_messages_preflight_request(monkeypatch: pytest.MonkeyPatch) -> None:
    calls: list[Any] = []

    def fake_urlopen(req: Any, timeout: int) -> FakeResponse:
        calls.append(req)
        return FakeResponse({"content": [{"type": "text", "text": "OK"}]})

    monkeypatch.setattr(
        "clawbench.runner.run_support.api_preflight.urllib.request.urlopen",
        fake_urlopen,
    )

    preflight_model_api(
        {
            "model": "claude-test",
            "base_url": "https://api.anthropic.com",
            "api_type": "anthropic-messages",
            "api_key": "secret-key",
        }
    )

    req = calls[0]
    payload = json.loads(req.data)
    headers = _headers(req)
    assert req.full_url == "https://api.anthropic.com/v1/messages"
    assert headers["X-api-key"] == "secret-key"
    assert headers["Anthropic-version"] == "2023-06-01"
    assert payload["model"] == "claude-test"
    assert payload["max_tokens"] == 4


def test_gemini_preflight_request_uses_existing_api_version(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls: list[Any] = []

    def fake_urlopen(req: Any, timeout: int) -> FakeResponse:
        calls.append(req)
        return FakeResponse({"candidates": [{"content": {"parts": [{"text": "OK"}]}}]})

    monkeypatch.setattr(
        "clawbench.runner.run_support.api_preflight.urllib.request.urlopen",
        fake_urlopen,
    )

    preflight_model_api(
        {
            "model": "gemini-test",
            "base_url": "https://generativelanguage.googleapis.com/v1beta",
            "api_type": "google-generative-ai",
            "api_key": "gemini-secret",
        }
    )

    req = calls[0]
    payload = json.loads(req.data)
    parsed = urllib.parse.urlsplit(req.full_url)
    query = urllib.parse.parse_qs(parsed.query)
    assert (
        f"{parsed.scheme}://{parsed.netloc}{parsed.path}"
        == "https://generativelanguage.googleapis.com/v1beta/models/gemini-test:generateContent"
    )
    assert query == {"key": ["gemini-secret"]}
    assert payload["contents"][0]["parts"] == [{"text": "Reply with OK."}]
    assert payload["generationConfig"]["maxOutputTokens"] == 4


def test_preflight_failure_redacts_secret_and_suppresses_cause(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def fake_urlopen(req: Any, timeout: int) -> FakeResponse:
        raise urllib.error.HTTPError(
            req.full_url,
            401,
            "invalid secret-key-for-test",
            hdrs=Message(),
            fp=None,
        )

    monkeypatch.setattr(
        "clawbench.runner.run_support.api_preflight.urllib.request.urlopen",
        fake_urlopen,
    )

    with pytest.raises(ModelApiPreflightError) as excinfo:
        preflight_model_api(
            {
                "model": "test-chat",
                "base_url": "https://api.example.test/v1",
                "api_type": "openai-completions",
                "api_key": "secret-key-for-test",
            }
        )

    message = str(excinfo.value)
    assert "secret-key-for-test" not in message
    assert "[REDACTED]" in message
    assert excinfo.value.__cause__ is None
    assert excinfo.value.__suppress_context__ is True


def test_preflight_failure_redacts_url_encoded_query_key(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    secret = "gemini/key+with=special chars"
    encoded_secret = urllib.parse.quote_plus(secret)

    def fake_urlopen(req: Any, timeout: int) -> FakeResponse:
        raise RuntimeError(f"failed url={req.full_url} raw={secret}")

    monkeypatch.setattr(
        "clawbench.runner.run_support.api_preflight.urllib.request.urlopen",
        fake_urlopen,
    )

    with pytest.raises(ModelApiPreflightError) as excinfo:
        preflight_model_api(
            {
                "model": "gemini-test",
                "base_url": "https://generativelanguage.googleapis.com/v1beta",
                "api_type": "google-generative-ai",
                "api_key": secret,
            }
        )

    message = str(excinfo.value)
    assert secret not in message
    assert encoded_secret not in message
    assert "key=[REDACTED]" in message
    assert "raw=[REDACTED]" in message
    assert excinfo.value.__cause__ is None
    assert excinfo.value.__suppress_context__ is True


def _import_run_module(monkeypatch: pytest.MonkeyPatch) -> ModuleType:
    for module_name in (
        "clawbench.runner.run",
        "clawbench.runner.run_support.metadata",
        "clawbench.runner.run_support.docker",
        "clawbench.runner.run_support.config",
    ):
        sys.modules.pop(module_name, None)
    monkeypatch.delenv("CONTAINER_ENGINE", raising=False)
    monkeypatch.setattr(
        shutil,
        "which",
        lambda cmd: str(Path("mock-bin") / cmd) if cmd == "docker" else None,
    )
    return importlib.import_module("clawbench.runner.run")


def test_run_stops_on_preflight_failure_before_docker_build(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    run_mod = _import_run_module(monkeypatch)
    task_dir = tmp_path / "case"
    task_dir.mkdir()
    (task_dir / "task.json").write_text(
        json.dumps(
            {
                "instruction": "Do the task",
                "eval_schema": {"url_pattern": "example", "method": "POST"},
                "time_limit": 1,
            }
        )
    )
    events: list[str] = []

    monkeypatch.setattr(
        run_mod.sys,
        "argv",
        [
            "clawbench-run",
            str(task_dir),
            "model-a",
            "--output-dir",
            str(tmp_path / "out"),
            "--no-upload",
        ],
    )
    monkeypatch.setattr(run_mod, "ensure_workspace_templates", lambda: None)
    monkeypatch.setattr(
        run_mod,
        "load_runtime_env",
        lambda: {
            "PURELY_MAIL_API_KEY": "pm-key",
            "PURELY_MAIL_DOMAIN": "example.test",
        },
    )
    monkeypatch.setattr(
        run_mod,
        "make_browser_runtime_provider",
        lambda args, runtime_env: type("Provider", (), {"name": "local"})(),
    )
    monkeypatch.setattr(
        run_mod,
        "load_model_config",
        lambda model: {
            "model": model,
            "base_url": "https://api.example.test/v1",
            "api_type": "openai-completions",
            "api_key": "secret-key",
            "api_keys": ["secret-key"],
        },
    )
    monkeypatch.setattr(run_mod, "step", lambda label: events.append(label))
    monkeypatch.setattr(
        run_mod,
        "preflight_model_api",
        lambda model_cfg: (_ for _ in ()).throw(
            run_mod.ModelApiPreflightError("bad credentials")
        ),
    )
    monkeypatch.setattr(
        run_mod,
        "docker_build",
        lambda harness: events.append("docker_build"),
    )
    monkeypatch.setattr(
        run_mod,
        "classify_run",
        lambda *args, **kwargs: {
            "result_category": "infra_failure",
            "failure_category": "infra_failure",
            "infra_failure": True,
            "adjusted_eligible": False,
            "infra_flags": [],
            "metrics": {},
        },
    )
    monkeypatch.setattr(
        run_mod,
        "make_run_meta",
        lambda **kwargs: {"failure_reason": kwargs.get("failure_reason")},
    )
    written: list[tuple[Path, dict[str, Any]]] = []
    monkeypatch.setattr(
        run_mod,
        "write_run_meta",
        lambda output_dir, meta: written.append((output_dir, meta)),
    )

    with pytest.raises(SystemExit) as excinfo:
        run_mod.main()

    assert excinfo.value.code == 2
    assert events == ["Checking model API"]
    assert written[0][1]["failure_reason"] == "model_api_preflight: bad credentials"
