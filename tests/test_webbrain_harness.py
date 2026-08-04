"""Unit tests for the WebBrain extension harness driver."""

from __future__ import annotations

import importlib.util
from pathlib import Path

import pytest


DRIVER_PATH = (
    Path(__file__).parents[1]
    / "src/clawbench/runtime/harnesses/webbrain/run-webbrain-agent.py"
)


def _load_driver():
    spec = importlib.util.spec_from_file_location("webbrain_harness", DRIVER_PATH)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_model_config_uses_first_rotating_key_and_normalizes_base_url() -> None:
    driver = _load_driver()

    config = driver.model_config(
        {
            "API_TYPE": "openai-completions",
            "API_KEYS": '["key-one", "key-two"]',
            "API_KEY": "fallback",
            "BASE_URL": "https://example.test/v1/",
            "MODEL_NAME": "example/model",
        }
    )

    assert config == {
        "api_key": "key-one",
        "base_url": "https://example.test/v1",
        "model": "example/model",
    }


def test_storage_config_maps_model_without_assuming_vision_support() -> None:
    driver = _load_driver()

    stored = driver.webbrain_storage_config(
        {
            "api_key": "secret",
            "base_url": "https://example.test/v1",
            "model": "example/model",
        }
    )

    assert stored["activeProvider"] == "clawbench"
    assert stored["tracingEnabled"] is True
    assert stored["onboardingComplete"] is True
    assert stored["askBeforeConsequentialActions"] is False
    assert stored["clarifyTimeoutSec"] == 0
    assert stored["planReviewMode"] == "never"
    assert stored["providers"]["clawbench"] == {
        "type": "openai",
        "category": "cloud",
        "label": "ClawBench",
        "providerName": "clawbench",
        "baseUrl": "https://example.test/v1",
        "model": "example/model",
        "contextWindow": 200000,
        "supportsVision": False,
        "supportsTools": True,
        "supportsAskStreaming": True,
        "supportsStreamUsageOptions": False,
        "apiKey": "secret",
        "enabled": True,
        "configured": True,
    }


def test_stop_request_reason_requires_a_confirmed_interception(tmp_path: Path) -> None:
    driver = _load_driver()
    interception = tmp_path / "interception.json"

    assert driver.stop_request_reason(interception) == "stop_requested"

    interception.write_text('{"intercepted": false, "request": null}', encoding="utf-8")
    assert driver.stop_request_reason(interception) == "stop_requested"

    interception.write_text(
        '{"intercepted": true, "request": {"url": "https://example.test"}}',
        encoding="utf-8",
    )
    assert driver.stop_request_reason(interception) == "eval_matched"


def test_stop_request_reason_fails_closed_for_invalid_json(tmp_path: Path) -> None:
    driver = _load_driver()
    interception = tmp_path / "interception.json"
    interception.write_text("not-json", encoding="utf-8")

    assert driver.stop_request_reason(interception) == "stop_requested"


@pytest.mark.parametrize(
    ("overrides", "message"),
    [
        ({"API_TYPE": "anthropic-messages"}, "unsupported API_TYPE"),
        ({"API_KEYS": "[]", "API_KEY": ""}, "no API key"),
        ({"BASE_URL": ""}, "BASE_URL"),
        ({"MODEL_NAME": ""}, "MODEL_NAME"),
    ],
)
def test_model_config_rejects_unsupported_or_incomplete_input(
    overrides: dict[str, str], message: str
) -> None:
    driver = _load_driver()
    env = {
        "API_TYPE": "openai-completions",
        "API_KEYS": "[]",
        "API_KEY": "key",
        "BASE_URL": "https://example.test/v1",
        "MODEL_NAME": "model",
    }
    env.update(overrides)

    with pytest.raises(ValueError, match=message):
        driver.model_config(env)


def test_webbrain_extension_id_ignores_unrelated_targets() -> None:
    driver = _load_driver()
    targets = [
        {"type": "page", "url": "about:blank"},
        {
            "type": "service_worker",
            "url": "chrome-extension://abcdefghijklmnop/worker.js",
        },
        {
            "type": "service_worker",
            "url": "chrome-extension://webbrainextension/src/background.js",
        },
    ]

    assert driver.webbrain_extension_id(targets) == "webbrainextension"


def test_webbrain_extension_id_fails_when_worker_is_missing() -> None:
    driver = _load_driver()

    with pytest.raises(RuntimeError, match="service worker"):
        driver.webbrain_extension_id([{"type": "page", "url": "about:blank"}])


def test_transcript_rows_preserve_updates_traces_and_terminal_result() -> None:
    driver = _load_driver()
    result = {
        "content": "Task complete",
        "conversationId": "conversation-1",
        "updates": [{"type": "tool_result", "data": {"name": "navigate"}}],
    }
    traces = [
        {
            "run": {"runId": "run-1", "status": "done"},
            "events": [
                {
                    "runId": "run-1",
                    "seq": 1,
                    "kind": "llm_response",
                    "data": {
                        "model": "example/model",
                        "usage": {"prompt_tokens": 10, "completion_tokens": 4},
                    },
                }
            ],
        }
    ]

    rows = driver.transcript_rows("Do the task", result, traces)

    assert [row["type"] for row in rows] == [
        "user",
        "agent_update",
        "webbrain_trace",
        "assistant",
    ]
    assert rows[2]["trace"]["kind"] == "llm_response"
    assert rows[-1]["content"] == "Task complete"


def test_usage_rows_normalize_webbrain_trace_usage() -> None:
    driver = _load_driver()
    traces = [
        {
            "run": {"runId": "run-1"},
            "events": [
                {
                    "seq": 3,
                    "kind": "llm_response",
                    "data": {
                        "model": "example/model",
                        "usage": {
                            "prompt_tokens": 100,
                            "completion_tokens": 20,
                            "prompt_tokens_details": {"cached_tokens": 30},
                        },
                    },
                },
                {"seq": 4, "kind": "tool", "data": {}},
            ],
        }
    ]

    assert driver.usage_rows(traces, "fallback-model") == [
        {
            "type": "usage",
            "source_harness": "webbrain",
            "call_id": "run-1:3",
            "model": "example/model",
            "input_tokens": 70,
            "output_tokens": 20,
            "cache_read_tokens": 30,
            "cache_write_tokens": 0,
            "reasoning_tokens": 0,
            "total_tokens": 120,
            "estimated_cost_usd": None,
            "cost_status": "price_unavailable",
        }
    ]
