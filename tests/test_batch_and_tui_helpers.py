"""Host-only tests for batch and TUI selection helpers."""

from __future__ import annotations

import argparse
import asyncio
from pathlib import Path
from typing import Any, cast

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


def test_browserbase_batch_defaults_to_one_concurrent_session(
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
            }
        },
    )
    args = argparse.Namespace(
        models=["model-a"],
        all_models=False,
        cases=["test-cases/v1/001-daily-life-food-uber-eats"],
        all_cases=False,
        case_range=None,
        cases_dir=batch.CASE_SUITES["v1"],
        dry_run=True,
        output_dir=str(tmp_path),
        max_concurrent=None,
        stagger_delay=0,
        resume=None,
        no_upload=True,
        harness="openclaw",
        browser_runtime="browserbase",
        browser_cdp_url=None,
        browser_runtime_options=None,
        judge="judge-model",
        no_judge=True,
    )

    rc = asyncio.run(batch.async_main(args))

    assert rc == 0
    assert args.max_concurrent == 1


def test_kernel_batch_defaults_to_one_concurrent_session(
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
            }
        },
    )
    args = argparse.Namespace(
        models=["model-a"],
        all_models=False,
        cases=["test-cases/v1/001-daily-life-food-uber-eats"],
        all_cases=False,
        case_range=None,
        cases_dir=batch.CASE_SUITES["v1"],
        dry_run=True,
        output_dir=str(tmp_path),
        max_concurrent=None,
        stagger_delay=0,
        resume=None,
        no_upload=True,
        harness="openclaw",
        browser_runtime="kernel",
        browser_cdp_url=None,
        browser_runtime_options=None,
        judge="judge-model",
        no_judge=True,
    )

    rc = asyncio.run(batch.async_main(args))

    assert rc == 0
    assert args.max_concurrent == 1


def test_tui_hides_managed_runtimes_for_extension_harness(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    captured_values: list[str] = []

    class _Prompt:
        def ask(self) -> str:
            return "local"

    def fake_select(*args: object, **kwargs: object) -> _Prompt:
        choices = cast(list[Any], kwargs["choices"])
        captured_values.extend(choice.value for choice in choices)
        return _Prompt()

    monkeypatch.setattr(tui.questionary, "select", fake_select)

    selected = tui._pick_browser_runtime("claude-code-chrome-extension")

    assert selected == "local"
    assert captured_values == ["local"]


def test_tui_lists_kernel_for_remote_capable_harness(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    captured_values: list[str] = []

    class _Prompt:
        def ask(self) -> str:
            return "kernel"

    def fake_select(*args: object, **kwargs: object) -> _Prompt:
        choices = cast(list[Any], kwargs["choices"])
        captured_values.extend(choice.value for choice in choices)
        return _Prompt()

    monkeypatch.setattr(tui.questionary, "select", fake_select)

    selected = tui._pick_browser_runtime("openclaw")

    assert selected == "kernel"
    assert captured_values == ["local", "kernel", "browserbase", "steel"]
