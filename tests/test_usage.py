"""Token and estimated-cost accounting tests."""

from __future__ import annotations

import json
import importlib.util
import argparse
from pathlib import Path

import pytest

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


EMITTER_HARNESSES = (
    "openclaw",
    "opencode",
    "claude-code",
    "claude-code-chrome-extension",
    "codex",
    "browser-use",
    "claw-code",
    "hermes",
    "pi",
)


def _load_usage_emitter(harness: str):
    path = (
        Path(__file__).parents[1]
        / "src/clawbench/runtime/harnesses"
        / harness
        / "usage-emitter.py"
    )
    spec = importlib.util.spec_from_file_location(
        f"{harness.replace('-', '_')}_usage_emitter",
        path,
    )
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_resolve_openrouter_model_exact_then_suffix() -> None:
    exact = resolve_openrouter_model(["provider/test-model"], PRICING)
    assert exact is not None
    assert exact["id"] == "provider/test-model"

    suffix = resolve_openrouter_model(["test-model"], PRICING)
    assert suffix is not None
    assert suffix["id"] == "provider/test-model"

    assert resolve_openrouter_model(["missing"], PRICING) is None


def test_usage_jsonl_rows_and_cost_math() -> None:
    lines = [
        _line(
            {
                "type": "usage",
                "source_harness": "openclaw",
                "call_id": "a1",
                "model": "test-model",
                "input_tokens": 100,
                "output_tokens": 20,
                "cache_read_tokens": 50,
                "cache_write_tokens": 10,
                "total_tokens": 180,
                "estimated_cost_usd": 0.17,
                "cost_status": "estimated",
                "matched_model_id": "provider/test-model",
            }
        ),
        _line(
            {
                "type": "usage",
                "source_harness": "openclaw",
                "call_id": "a2",
                "model": "test-model",
                "input_tokens": 10,
                "output_tokens": 5,
                "total_tokens": 15,
                "estimated_cost_usd": 0.0,
                "cost_status": "estimated",
                "matched_model_id": "provider/test-model",
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


def test_duplicate_usage_rows_count_once() -> None:
    row = {
        "type": "usage",
        "source_harness": "claude-code",
        "call_id": "gen-1",
        "model": "test-model",
        "input_tokens": 100,
        "output_tokens": 30,
        "cache_read_tokens": 70,
        "total_tokens": 200,
        "estimated_cost_usd": 0.173,
        "cost_status": "estimated",
    }
    lines = [_line(row), _line(row), _line({**row, "timestamp": 2})]

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


def test_price_unavailable_rows_keep_tokens() -> None:
    lines = [
        _line(
            {
                "type": "usage",
                "source_harness": "browser-use",
                "call_id": "b1",
                "model": "test-model",
                "input_tokens": 60,
                "output_tokens": 10,
                "cache_read_tokens": 40,
                "total_tokens": 110,
                "estimated_cost_usd": None,
                "cost_status": "price_unavailable",
            }
        )
    ]

    summary = summarize_usage_lines(
        lines,
        model_cfg={"model": "test-model", "base_url": "https://openrouter.ai/api/v1"},
        pricing_models=PRICING,
    )

    assert summary["status"] == "price_unavailable"
    assert summary["input_tokens"] == 60
    assert summary["cache_read_tokens"] == 40
    assert summary["total_tokens"] == 110


def test_agent_messages_without_usage_json_contract_are_unavailable() -> None:
    lines = [
        _line(
            {
                "type": "message",
                "message": {
                    "role": "assistant",
                    "model": "provider/test-model",
                    "usage": {"input_tokens": 300, "output_tokens": 40},
                },
            }
        )
    ]

    summary = summarize_usage_lines(
        lines,
        model_cfg={
            "model": "provider/test-model",
            "base_url": "https://openrouter.ai/api/v1",
        },
        pricing_models=PRICING,
    )

    assert summary["status"] == "usage_unavailable"
    assert summary["api_calls"] == 0
    assert summary["total_tokens"] == 0


def test_summarize_usage_file_handles_missing_file(tmp_path: Path) -> None:
    summary = summarize_usage_file(tmp_path / "missing.jsonl")

    assert summary["status"] == "usage_unavailable"
    assert summary["total_tokens"] == 0


def test_usage_jsonl_source_is_marked_transient(tmp_path: Path) -> None:
    path = tmp_path / "usage.jsonl"
    path.write_text("")

    summary = summarize_usage_file(path)

    assert summary["usage_source"] == "transient_usage_jsonl"


@pytest.mark.parametrize("harness", EMITTER_HARNESSES)
def test_harness_usage_emitter_writes_contract_rows(
    tmp_path: Path,
    harness: str,
) -> None:
    emitter = _load_usage_emitter(harness)
    src = tmp_path / "agent-messages.jsonl"
    dst = tmp_path / "usage.jsonl"
    src.write_text(
        "\n".join(
            [
                _line(
                    {
                        "type": "message",
                        "id": "openclaw-1",
                        "message": {
                            "role": "assistant",
                            "model": "test-model",
                            "usage": {"input": 10, "output": 3},
                        },
                    }
                ),
                _line(
                    {
                        "type": "assistant",
                        "message": {
                            "id": "claude-1",
                            "model": "test-model",
                            "usage": {
                                "input_tokens": 20,
                                "output_tokens": 4,
                                "cache_read_input_tokens": 6,
                            },
                        },
                    }
                ),
                _line(
                    {
                        "type": "session_meta",
                        "model": "test-model",
                        "input_tokens": 30,
                        "output_tokens": 5,
                    }
                ),
                _line(
                    {
                        "type": "step_finish",
                        "part": {
                            "id": "opencode-part-1",
                            "model": "test-model",
                            "tokens": {
                                "input": 100,
                                "output": 7,
                                "reasoning": 2,
                                "cache": {"read": 11, "write": 0},
                            },
                        },
                    }
                ),
            ]
        )
        + "\n"
    )
    args = argparse.Namespace(
        harness="fixture-harness",
        input=src,
        output=dst,
        model="test-model",
        base_url="https://api.example.test",
        api_key="",
    )

    emitter.emit_once(args)

    rows = [json.loads(line) for line in dst.read_text().splitlines()]
    assert [row["source_harness"] for row in rows] == ["fixture-harness"] * 4
    assert [row["total_tokens"] for row in rows] == [13, 30, 35, 120]
    assert rows[-1]["cache_read_tokens"] == 11
    assert rows[-1]["reasoning_tokens"] == 2
    assert all(row["type"] == "usage" for row in rows)
