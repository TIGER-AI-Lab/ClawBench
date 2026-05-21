"""Host-only tests for batch and TUI selection helpers."""

from __future__ import annotations

import argparse
import asyncio
from pathlib import Path

import pytest

from clawbench import tui
from clawbench.runner import batch


def test_tui_range_parser_selects_cases_without_platform_assumptions() -> None:
    cases = [
        "001-daily-life-food-uber-eats",
        "002-daily-life-food-doordash",
        "v2-1065b-daily-life-home-services-handy",
        "369-entertainment-hobbies-general-goodreads",
    ]

    selected = tui._parse_range_input("1-2,1065b,369", cases)

    assert selected == cases


def test_batch_dry_run_builds_job_matrix_without_container_runtime(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    monkeypatch.setattr(
        batch,
        "load_models_yaml",
        lambda: {
            "model-a": {
                "base_url": "https://api.example.test",
                "api_type": "openai-completions",
                "api_key": "secret",
            },
            "model-b": {
                "base_url": "https://api.example.test",
                "api_type": "openai-completions",
                "api_key": "secret",
            },
        },
    )
    args = argparse.Namespace(
        models=["model-*"],
        all_models=False,
        cases=["test-cases/v1/001-daily-life-food-uber-eats"],
        all_cases=False,
        case_range=None,
        cases_dir=batch.CASE_SUITES["v1"],
        dry_run=True,
        output_dir=str(tmp_path),
        max_concurrent=2,
        stagger_delay=0,
        resume=None,
        no_upload=True,
        harness="openclaw",
        judge="judge-model",
        no_judge=True,
    )

    rc = asyncio.run(batch.async_main(args))

    assert rc == 0
