"""Provider implementations for local and remote browser runtimes."""

from __future__ import annotations

import argparse
import json
import os
import socket
import urllib.parse
from dataclasses import dataclass, field
from typing import Any, Protocol

BROWSER_RUNTIME_CHOICES = ("local", "remote-cdp", "steel", "browserbase")
DEFAULT_BROWSER_CDP_URL = os.environ.get(
    "CLAWBENCH_BROWSER_CDP_URL",
    "http://127.0.0.1:9222",
)


class BrowserRuntimeError(RuntimeError):
    """Browser runtime error with a stable result category."""

    def __init__(
        self,
        message: str,
        *,
        category: str = "browser_runtime_setup_failed",
    ) -> None:
        super().__init__(message)
        self.category = category


@dataclass
class BrowserSession:
    provider: str
    cdp_url: str
    mode: str
    session_id: str | None = None
    viewer_url: str | None = None
    debug_url: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)
    recording_mode: str = "x11"
    local_viewer_port: int | None = None
    cleanup_status: str | None = None
    cleanup_error: str | None = None

    def to_metadata(self) -> dict[str, Any]:
        return {
            "provider": self.provider,
            "mode": self.mode,
            "session_id": self.session_id,
            "cdp_url": redact_cdp_url(self.cdp_url),
            "viewer_url": self.viewer_url,
            "debug_url": self.debug_url,
            "recording_mode": self.recording_mode,
            "local_viewer_port": self.local_viewer_port,
            "cleanup_status": self.cleanup_status,
            "cleanup_error": self.cleanup_error,
            "metadata": _redact_metadata(self.metadata),
        }


class BrowserRuntimeProvider(Protocol):
    name: str

    def start(self, task: dict[str, Any], time_limit_s: int) -> BrowserSession:
        """Start or reserve a browser runtime and return its CDP endpoint."""
        ...

    def cleanup(self, session: BrowserSession) -> None:
        """Release any provider resources associated with a session."""
        ...


def _redact_metadata(value: Any) -> Any:
    if isinstance(value, dict):
        redacted: dict[str, Any] = {}
        for key, item in value.items():
            if any(secret in key.lower() for secret in ("api_key", "token", "secret")):
                redacted[key] = "[REDACTED]" if item else item
            else:
                redacted[key] = _redact_metadata(item)
        return redacted
    if isinstance(value, list):
        return [_redact_metadata(item) for item in value]
    if isinstance(value, str) and "apiKey=" in value:
        return redact_cdp_url(value)
    return value


def redact_cdp_url(url: str) -> str:
    parsed = urllib.parse.urlsplit(url)
    query = urllib.parse.parse_qsl(parsed.query, keep_blank_values=True)
    if not query:
        return url
    redacted = [
        (key, "[REDACTED]" if key.lower() in {"apikey", "api_key", "token"} else val)
        for key, val in query
    ]
    return urllib.parse.urlunsplit(
        parsed._replace(query=urllib.parse.urlencode(redacted))
    )


def _parse_options(raw: str | None) -> dict[str, Any]:
    if not raw:
        return {}
    try:
        value = json.loads(raw)
    except json.JSONDecodeError as e:
        raise BrowserRuntimeError(f"--browser-runtime-options must be JSON: {e}") from e
    if not isinstance(value, dict):
        raise BrowserRuntimeError("--browser-runtime-options must decode to an object")
    return value


def _env_value(env: dict[str, str], key: str) -> str | None:
    value = env.get(key) or os.environ.get(key)
    return value if value else None


def _pick_free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        s.bind(("127.0.0.1", 0))
        return int(s.getsockname()[1])


class LocalBrowserRuntimeProvider:
    name = "local"

    def start(self, task: dict[str, Any], time_limit_s: int) -> BrowserSession:
        return BrowserSession(
            provider=self.name,
            mode="local",
            cdp_url=DEFAULT_BROWSER_CDP_URL,
            recording_mode="x11",
            local_viewer_port=_pick_free_port(),
        )

    def cleanup(self, session: BrowserSession) -> None:
        session.cleanup_status = "not_required"


class RemoteCdpBrowserRuntimeProvider:
    name = "remote-cdp"

    def __init__(self, *, cdp_url: str | None, options: dict[str, Any]) -> None:
        self.cdp_url = cdp_url
        self.options = options

    def start(self, task: dict[str, Any], time_limit_s: int) -> BrowserSession:
        if not self.cdp_url:
            raise BrowserRuntimeError(
                "remote-cdp browser runtime requires --browser-cdp-url or "
                "CLAWBENCH_BROWSER_CDP_URL"
            )
        return BrowserSession(
            provider=self.name,
            mode="remote",
            cdp_url=self.cdp_url,
            viewer_url=self.options.get("viewer_url"),
            debug_url=self.options.get("debug_url"),
            metadata={"options": self.options} if self.options else {},
            recording_mode="disabled",
        )

    def cleanup(self, session: BrowserSession) -> None:
        session.cleanup_status = "not_required"


class SteelBrowserRuntimeProvider:
    name = "steel"

    def __init__(self, *, options: dict[str, Any]) -> None:
        self.options = options

    def start(self, task: dict[str, Any], time_limit_s: int) -> BrowserSession:
        raise BrowserRuntimeError(
            "steel browser runtime is reserved but not implemented yet"
        )

    def cleanup(self, session: BrowserSession) -> None:
        session.cleanup_status = "not_required"


class BrowserbaseRuntimeProvider:
    name = "browserbase"

    def __init__(self, *, options: dict[str, Any]) -> None:
        self.options = options

    def start(self, task: dict[str, Any], time_limit_s: int) -> BrowserSession:
        raise BrowserRuntimeError(
            "browserbase browser runtime is reserved but not implemented yet"
        )

    def cleanup(self, session: BrowserSession) -> None:
        session.cleanup_status = "not_required"


def make_browser_runtime_provider(
    args: argparse.Namespace,
    env: dict[str, str],
) -> BrowserRuntimeProvider:
    runtime = (
        getattr(args, "browser_runtime", None)
        or _env_value(env, "CLAWBENCH_BROWSER_RUNTIME")
        or "local"
    )
    options = _parse_options(
        getattr(args, "browser_runtime_options", None)
        or _env_value(env, "CLAWBENCH_BROWSER_RUNTIME_OPTIONS")
    )
    if runtime == "local":
        return LocalBrowserRuntimeProvider()
    if runtime == "remote-cdp":
        return RemoteCdpBrowserRuntimeProvider(
            cdp_url=(
                getattr(args, "browser_cdp_url", None)
                or _env_value(env, "CLAWBENCH_BROWSER_CDP_URL")
            ),
            options={
                **(
                    {"viewer_url": _env_value(env, "CLAWBENCH_BROWSER_VIEWER_URL")}
                    if _env_value(env, "CLAWBENCH_BROWSER_VIEWER_URL")
                    else {}
                ),
                **options,
            },
        )
    if runtime == "steel":
        return SteelBrowserRuntimeProvider(options=options)
    if runtime == "browserbase":
        return BrowserbaseRuntimeProvider(options=options)
    raise BrowserRuntimeError(
        f"unknown browser runtime {runtime!r}; expected one of {BROWSER_RUNTIME_CHOICES}"
    )
