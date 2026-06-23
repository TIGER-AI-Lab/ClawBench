"""Browser runtime provider selection and session lifecycle tests."""

from __future__ import annotations

import argparse

import pytest

from clawbench.runner.run_support.browser_runtime import (
    BrowserRuntimeError,
    make_browser_runtime_provider,
)
from clawbench.runner.run_support.browser_runtime.providers import (
    BrowserbaseRuntimeProvider,
    RemoteCdpBrowserRuntimeProvider,
    SteelBrowserRuntimeProvider,
    redact_cdp_url,
)


def _args(**overrides: object) -> argparse.Namespace:
    values: dict[str, object] = {
        "browser_runtime": None,
        "browser_cdp_url": None,
        "browser_runtime_options": None,
    }
    values.update(overrides)
    return argparse.Namespace(**values)


@pytest.fixture(autouse=True)
def _clear_browser_runtime_env(monkeypatch: pytest.MonkeyPatch) -> None:
    for key in (
        "CLAWBENCH_BROWSER_RUNTIME",
        "CLAWBENCH_BROWSER_CDP_URL",
        "CLAWBENCH_BROWSER_RUNTIME_OPTIONS",
        "CLAWBENCH_BROWSER_VIEWER_URL",
        "STEEL_BASE_URL",
        "STEEL_API_KEY",
    ):
        monkeypatch.delenv(key, raising=False)


def test_browser_runtime_env_and_cli_precedence() -> None:
    provider = make_browser_runtime_provider(
        _args(browser_cdp_url="wss://cli.example.test/devtools"),
        {
            "CLAWBENCH_BROWSER_RUNTIME": "remote-cdp",
            "CLAWBENCH_BROWSER_CDP_URL": "wss://env.example.test/devtools",
        },
    )

    assert isinstance(provider, RemoteCdpBrowserRuntimeProvider)
    session = provider.start({}, 60)
    assert session.provider == "remote-cdp"
    assert session.mode == "remote"
    assert session.cdp_url == "wss://cli.example.test/devtools"
    assert session.recording_mode == "disabled"


def test_remote_cdp_requires_url() -> None:
    provider = make_browser_runtime_provider(
        _args(browser_runtime="remote-cdp"),
        {},
    )

    with pytest.raises(BrowserRuntimeError, match="requires"):
        provider.start({}, 60)


def test_local_browser_runtime_defaults_to_local_mode() -> None:
    provider = make_browser_runtime_provider(_args(), {})
    session = provider.start({}, 60)

    assert session.provider == "local"
    assert session.mode == "local"
    assert session.cdp_url == "http://127.0.0.1:9222"
    assert session.recording_mode == "x11"
    assert isinstance(session.local_viewer_port, int)


def test_steel_provider_is_reserved_not_implemented() -> None:
    provider = SteelBrowserRuntimeProvider(options={})

    with pytest.raises(BrowserRuntimeError, match="not implemented"):
        provider.start({}, 60)


def test_browserbase_provider_is_reserved_not_implemented() -> None:
    provider = BrowserbaseRuntimeProvider(options={})

    with pytest.raises(BrowserRuntimeError, match="not implemented"):
        provider.start({}, 60)


def test_redact_cdp_url_masks_common_secret_query_params() -> None:
    redacted = redact_cdp_url(
        "wss://example.test/devtools?apiKey=secret&token=two&x=ok"
    )

    assert redacted == (
        "wss://example.test/devtools?apiKey=%5BREDACTED%5D&token=%5BREDACTED%5D&x=ok"
    )
