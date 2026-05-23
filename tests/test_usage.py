"""Token and estimated-cost accounting tests."""

from __future__ import annotations

import json
from pathlib import Path

from clawbench.runner.run_support.usage import (
    format_usage_status,
    resolve_openrouter_model,
    summarize_usage_file,
    summarize_usage_lines,
)


PRICING = {
    "provider/test-model": {
        "id": "provider/test-model",
        "pricing": {
            "prompt": "0.001",
            "completion": "0.002",
            "input_cache_read": "0.0001",
            "input_cache_write": "0.0005",
            "internal_reasoning": "0.003",
        },
    },
    "provider/other-model": {
        "id": "provider/other-model",
        "pricing": {"prompt": "0.01", "completion": "0.02"},
    },
}


def _line(row: dict) -> str:
    return json.dumps(row)


def test_resolve_openrouter_model_exact_then_suffix() -> None:
    exact = resolve_openrouter_model(["provider/test-model"], PRICING)
    assert exact is not None
    assert exact["id"] == "provider/test-model"

    suffix = resolve_openrouter_model(["test-model"], PRICING)
    assert suffix is not None
    assert suffix["id"] == "provider/test-model"

    assert resolve_openrouter_model(["missing"], PRICING) is None


def test_openclaw_usage_and_cost_math() -> None:
    lines = [
        _line(
            {
                "type": "message",
                "id": "a1",
                "message": {
                    "role": "assistant",
                    "model": "test-model",
                    "usage": {
                        "input": 100,
                        "output": 20,
                        "cacheRead": 50,
                        "cacheWrite": 10,
                        "totalTokens": 180,
                    },
                },
            }
        ),
        _line(
            {
                "type": "message",
                "id": "a2",
                "message": {
                    "role": "assistant",
                    "model": "test-model",
                    "usage": {"input": 10, "output": 5, "totalTokens": 15},
                },
            }
        ),
    ]

    summary = summarize_usage_lines(
        lines,
        model_cfg={"model": "test-model", "base_url": "https://openrouter.ai/api/v1"},
        pricing_models=PRICING,
    )

    assert summary["status"] == "estimated"
    assert summary["api_calls"] == 2
    assert summary["total_tokens"] == 195
    assert summary["input_tokens"] == 110
    assert summary["output_tokens"] == 25
    assert summary["cache_read_tokens"] == 50
    assert summary["cache_write_tokens"] == 10
    assert summary["estimated_cost_usd"] == 0.17
    assert "195 tok" in format_usage_status(summary)


def test_claude_code_duplicate_stream_rows_count_once() -> None:
    row = {
        "type": "assistant",
        "message": {
            "id": "gen-1",
            "role": "assistant",
            "model": "test-model",
            "usage": {
                "input_tokens": 100,
                "output_tokens": 30,
                "cache_read_input_tokens": 70,
                "total_tokens": 130,
            },
        },
    }
    lines = [_line(row), _line(row), _line({**row, "uuid": "different-fragment"})]

    summary = summarize_usage_lines(
        lines,
        model_cfg={"model": "test-model", "base_url": "https://openrouter.ai/api/v1"},
        pricing_models=PRICING,
    )

    assert summary["api_calls"] == 1
    assert summary["input_tokens"] == 100
    assert summary["output_tokens"] == 30
    assert summary["cache_read_tokens"] == 70
    assert summary["total_tokens"] == 200


def test_openai_nested_cached_tokens_are_not_double_counted() -> None:
    lines = [
        _line(
            {
                "usage": {
                    "input_tokens": 100,
                    "output_tokens": 10,
                    "input_tokens_details": {"cached_tokens": 40},
                }
            }
        )
    ]

    summary = summarize_usage_lines(
        lines,
        model_cfg={"model": "test-model", "base_url": "https://openrouter.ai/api/v1"},
        pricing_models=PRICING,
    )

    assert summary["input_tokens"] == 60
    assert summary["cache_read_tokens"] == 40
    assert summary["total_tokens"] == 110


def test_hermes_session_meta_usage_wins_over_message_rows() -> None:
    lines = [
        _line(
            {
                "type": "session_meta",
                "model": "provider/test-model",
                "input_tokens": 300,
                "output_tokens": 40,
                "cache_read_tokens": 500,
                "api_call_count": 7,
            }
        ),
        _line(
            {
                "type": "message",
                "message": {
                    "id": "m1",
                    "role": "assistant",
                    "model": "provider/test-model",
                    "usage": {"input_tokens": 1, "output_tokens": 1},
                },
            }
        ),
    ]

    summary = summarize_usage_lines(
        lines,
        model_cfg={
            "model": "provider/test-model",
            "base_url": "https://openrouter.ai/api/v1",
        },
        pricing_models=PRICING,
    )

    assert summary["api_calls"] == 7
    assert summary["input_tokens"] == 300
    assert summary["output_tokens"] == 40
    assert summary["cache_read_tokens"] == 500
    assert summary["total_tokens"] == 840


def test_summarize_usage_file_handles_missing_file(tmp_path: Path) -> None:
    summary = summarize_usage_file(tmp_path / "missing.jsonl")

    assert summary["status"] == "usage_unavailable"
    assert summary["total_tokens"] == 0
