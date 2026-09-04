"""Browser runtime provider selection and session lifecycle tests."""

from __future__ import annotations

import argparse
import json
import urllib.error
import urllib.request
from email.message import Message
from pathlib import Path

import pytest

from clawbench.runner.run_support.browser_runtime import (
    BrowserRuntimeError,
    make_browser_runtime_provider,
)
from clawbench.runner.run_support.browser_runtime.providers import (
    BrowserbaseRuntimeProvider,
    BrowserSession,
    KernelRuntimeProvider,
    RemoteCdpBrowserRuntimeProvider,
    SteelBrowserRuntimeProvider,
    redact_cdp_url,
)


class _FakeResponse:
    def __init__(
        self,
        payload: object,
        *,
        status: int = 200,
        headers: dict[str, str] | None = None,
    ) -> None:
        self.payload = payload
        self.status = status
        self.headers = headers or {}

    def __enter__(self) -> _FakeResponse:
        return self

    def __exit__(self, *args: object) -> None:
        return None

    def read(self) -> bytes:
        if isinstance(self.payload, bytes):
            return self.payload
        return json.dumps(self.payload).encode()


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
        "BROWSERBASE_API_KEY",
        "KERNEL_API_KEY",
        "KERNEL_BASE_URL",
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


def test_browserbase_requires_api_key() -> None:
    provider = BrowserbaseRuntimeProvider(api_key=None, options={})

    with pytest.raises(BrowserRuntimeError, match="BROWSERBASE_API_KEY"):
        provider.start({}, 60)
    with pytest.raises(BrowserRuntimeError, match="BROWSERBASE_API_KEY"):
        make_browser_runtime_provider(_args(browser_runtime="browserbase"), {})


def test_kernel_requires_api_key() -> None:
    provider = KernelRuntimeProvider(api_key=None, options={})

    with pytest.raises(BrowserRuntimeError, match="KERNEL_API_KEY"):
        provider.start({}, 60)
    with pytest.raises(BrowserRuntimeError, match="KERNEL_API_KEY"):
        make_browser_runtime_provider(_args(browser_runtime="kernel"), {})


def test_browserbase_rejects_reserved_options() -> None:
    with pytest.raises(BrowserRuntimeError, match="keepAlive"):
        BrowserbaseRuntimeProvider(
            api_key="bb-secret",
            options={"keepAlive": True},
        )


def test_kernel_rejects_reserved_options() -> None:
    with pytest.raises(BrowserRuntimeError, match="timeout_seconds"):
        KernelRuntimeProvider(
            api_key="kernel-secret",
            options={"timeout_seconds": 300},
        )


def test_browserbase_create_session_payload_and_metadata(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    requests: list[urllib.request.Request] = []

    def fake_urlopen(
        request: urllib.request.Request,
        timeout: int,
    ) -> _FakeResponse:
        requests.append(request)
        assert timeout == 15
        return _FakeResponse(
            {
                "id": "sess_123",
                "connectUrl": (
                    "wss://connect.browserbase.com?"
                    "sessionId=sess_123&apiKey=bb-secret&signingKey=signed"
                ),
                "region": "us-east-1",
                "expiresAt": "2026-08-03T12:00:00Z",
            }
        )

    monkeypatch.setattr(urllib.request, "urlopen", fake_urlopen)
    provider = BrowserbaseRuntimeProvider(
        api_key="bb-secret",
        options={
            "region": "us-east-1",
            "proxies": True,
            "browserSettings": {"solveCaptchas": True},
        },
    )

    session = provider.start({}, 1800)

    assert len(requests) == 1
    request = requests[0]
    assert request.get_method() == "POST"
    assert request.full_url.endswith("/v1/sessions")
    assert request.headers["X-bb-api-key"] == "bb-secret"
    assert isinstance(request.data, bytes)
    payload = json.loads(request.data)
    assert payload == {
        "region": "us-east-1",
        "proxies": True,
        "browserSettings": {
            "solveCaptchas": True,
            "viewport": {"width": 1920, "height": 1080},
            "recordSession": True,
        },
        "keepAlive": True,
        "timeout": 1920,
    }
    assert session.provider == "browserbase"
    assert session.mode == "remote"
    assert session.recording_mode == "provider"
    assert session.recording_url == "https://browserbase.com/sessions/sess_123"
    assert session.viewer_url == session.recording_url
    metadata = session.to_metadata()
    assert "bb-secret" not in json.dumps(metadata)
    assert "signed" not in json.dumps(metadata)
    assert "apiKey=%5BREDACTED%5D" in metadata["cdp_url"]
    assert "signingKey=%5BREDACTED%5D" in metadata["cdp_url"]


def test_browserbase_timeout_is_bounded(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    payloads: list[dict[str, object]] = []

    def fake_urlopen(
        request: urllib.request.Request,
        timeout: int,
    ) -> _FakeResponse:
        assert isinstance(request.data, bytes)
        payloads.append(json.loads(request.data))
        return _FakeResponse(
            {
                "id": f"sess_{len(payloads)}",
                "connectUrl": (
                    f"wss://connect.browserbase.com?sessionId=sess_{len(payloads)}"
                ),
            }
        )

    monkeypatch.setattr(urllib.request, "urlopen", fake_urlopen)
    provider = BrowserbaseRuntimeProvider(api_key="bb-secret", options={})

    provider.start({}, 1)
    provider.start({}, 99999)

    assert [payload["timeout"] for payload in payloads] == [121, 21600]


def test_browserbase_cleanup_releases_session(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls: list[tuple[str, str, dict[str, object] | None]] = []

    def fake_urlopen(
        request: urllib.request.Request,
        timeout: int,
    ) -> _FakeResponse:
        if request.data:
            assert isinstance(request.data, bytes)
            payload = json.loads(request.data)
        else:
            payload = None
        calls.append((request.get_method(), request.full_url, payload))
        return _FakeResponse({"status": "COMPLETED"})

    monkeypatch.setattr(urllib.request, "urlopen", fake_urlopen)
    provider = BrowserbaseRuntimeProvider(api_key="bb-secret", options={})
    session = BrowserSession(
        provider="browserbase",
        mode="remote",
        session_id="sess_123",
        cdp_url="wss://connect.browserbase.com?sessionId=sess_123",
    )

    provider.cleanup(session)

    assert calls == [
        (
            "POST",
            "https://api.browserbase.com/v1/sessions/sess_123",
            {"status": "REQUEST_RELEASE"},
        )
    ]
    assert session.cleanup_status == "released"


def test_browserbase_http_errors_do_not_expose_api_key(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def fake_urlopen(
        request: urllib.request.Request,
        timeout: int,
    ) -> _FakeResponse:
        raise urllib.error.HTTPError(
            request.full_url,
            401,
            "bb-secret",
            hdrs=Message(),
            fp=None,
        )

    monkeypatch.setattr(urllib.request, "urlopen", fake_urlopen)
    provider = BrowserbaseRuntimeProvider(api_key="bb-secret", options={})

    with pytest.raises(BrowserRuntimeError) as exc_info:
        provider.start({}, 60)

    assert "authentication failed" in str(exc_info.value)
    assert "bb-secret" not in str(exc_info.value)


def test_browserbase_malformed_response_is_safe(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        urllib.request,
        "urlopen",
        lambda request, timeout: _FakeResponse(b"not-json"),
    )
    provider = BrowserbaseRuntimeProvider(api_key="bb-secret", options={})

    with pytest.raises(BrowserRuntimeError, match="malformed JSON"):
        provider.start({}, 60)


def test_kernel_session_replay_and_cleanup(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    calls: list[tuple[str, str, object, str | None]] = []
    replay_downloads = 0

    def fake_urlopen(
        request: urllib.request.Request,
        timeout: int,
    ) -> _FakeResponse:
        nonlocal replay_downloads
        assert timeout == 30
        if request.data:
            assert isinstance(request.data, bytes)
            payload = json.loads(request.data)
        else:
            payload = None
        accept = request.headers.get("Accept")
        calls.append((request.get_method(), request.full_url, payload, accept))
        assert request.headers["Authorization"] == "Bearer kernel-secret"
        if request.full_url.endswith("/browsers"):
            return _FakeResponse(
                {
                    "session_id": "browser_123",
                    "cdp_ws_url": "wss://proxy.onkernel.test/cdp?jwt=cdp-secret",
                    "browser_live_view_url": (
                        "https://proxy.onkernel.test/browser/live/viewer-secret"
                    ),
                    "region": "us-east",
                    "stealth": True,
                    "timeout_seconds": 1920,
                }
            )
        if request.full_url.endswith("/browsers/browser_123/replays"):
            if request.get_method() == "POST":
                return _FakeResponse(
                    {
                        "replay_id": "replay_123",
                        "replay_view_url": (
                            "https://proxy.onkernel.test/replay?jwt=replay-secret"
                        ),
                    }
                )
            return _FakeResponse(
                [
                    {
                        "replay_id": "replay_123",
                        "finished_at": "2026-08-18T12:00:00Z",
                        "replay_view_url": (
                            "https://proxy.onkernel.test/replay?jwt=replay-secret"
                        ),
                    }
                ]
            )
        if request.full_url.endswith("/replays/replay_123/stop"):
            return _FakeResponse(b"")
        if request.full_url.endswith("/replays/replay_123"):
            replay_downloads += 1
            if replay_downloads == 1:
                return _FakeResponse(
                    b"not-ready",
                    status=202,
                    headers={"Retry-After": "0"},
                )
            return _FakeResponse(b"mp4-data")
        if request.full_url.endswith("/browsers/browser_123"):
            return _FakeResponse(b"")
        raise AssertionError(f"unexpected request: {request.full_url}")

    monkeypatch.setattr(urllib.request, "urlopen", fake_urlopen)
    provider = KernelRuntimeProvider(
        api_key="kernel-secret",
        options={"region": "us-east"},
        replay_poll_interval_s=0,
        replay_poll_timeout_s=1,
    )

    session = provider.start({}, 1800)
    provider.finalize(session, tmp_path)
    provider.cleanup(session)

    create_payload = calls[0][2]
    assert create_payload == {
        "stealth": True,
        "region": "us-east",
        "headless": False,
        "timeout_seconds": 1920,
    }
    assert session.provider == "kernel"
    assert session.recording_mode == "provider-download"
    assert session.cleanup_status == "deleted"
    assert replay_downloads == 2
    assert (tmp_path / "data" / "recording.mp4").read_bytes() == b"mp4-data"
    metadata = json.dumps(session.to_metadata())
    assert "cdp-secret" not in metadata
    assert "viewer-secret" not in metadata
    assert "replay-secret" not in metadata
    assert "jwt=%5BREDACTED%5D" in session.to_metadata()["cdp_url"]
    assert session.to_metadata()["viewer_url"] == "[REDACTED]"
    assert calls[-1][:2] == (
        "DELETE",
        "https://api.onkernel.com/browsers/browser_123",
    )


def test_kernel_factory_honors_base_url() -> None:
    provider = make_browser_runtime_provider(
        _args(browser_runtime="kernel"),
        {
            "KERNEL_API_KEY": "kernel-secret",
            "KERNEL_BASE_URL": "https://kernel.example.test/",
        },
    )

    assert isinstance(provider, KernelRuntimeProvider)
    assert provider.api_url == "https://kernel.example.test"


def test_kernel_http_errors_do_not_expose_api_key(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def fake_urlopen(
        request: urllib.request.Request,
        timeout: int,
    ) -> _FakeResponse:
        raise urllib.error.HTTPError(
            request.full_url,
            401,
            "kernel-secret",
            hdrs=Message(),
            fp=None,
        )

    monkeypatch.setattr(urllib.request, "urlopen", fake_urlopen)
    provider = KernelRuntimeProvider(api_key="kernel-secret", options={})

    with pytest.raises(BrowserRuntimeError) as exc_info:
        provider.start({}, 60)

    assert "authentication failed" in str(exc_info.value)
    assert "kernel-secret" not in str(exc_info.value)


def test_redact_cdp_url_masks_common_secret_query_params() -> None:
    redacted = redact_cdp_url(
        "wss://example.test/devtools?apiKey=secret&jwt=one&token=two&x=ok"
    )

    assert redacted == (
        "wss://example.test/devtools?apiKey=%5BREDACTED%5D&"
        "jwt=%5BREDACTED%5D&token=%5BREDACTED%5D&x=ok"
    )
