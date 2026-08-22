"""Provider implementations for local and remote browser runtimes."""

from __future__ import annotations

import argparse
import json
import os
import socket
import time
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Protocol

BROWSER_RUNTIME_CHOICES = ("local", "remote-cdp", "steel", "browserbase", "kernel")
_BROWSERBASE_API_URL = "https://api.browserbase.com/v1"
_BROWSERBASE_ALLOWED_OPTIONS = {
    "browserSettings",
    "extensionId",
    "projectId",
    "proxies",
    "region",
    "userMetadata",
}
_KERNEL_API_URL = "https://api.onkernel.com"
_KERNEL_ALLOWED_OPTIONS = {
    "proxy",
    "region",
    "stealth",
    "tags",
}
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
    viewer_url_sensitive: bool = False
    debug_url: str | None = None
    recording_url: str | None = None
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
            "viewer_url": (
                "[REDACTED]"
                if self.viewer_url_sensitive
                else redact_cdp_url(self.viewer_url)
                if self.viewer_url
                else None
            ),
            "debug_url": redact_cdp_url(self.debug_url) if self.debug_url else None,
            "recording_url": (
                redact_cdp_url(self.recording_url) if self.recording_url else None
            ),
            "recording_mode": self.recording_mode,
            "local_viewer_port": self.local_viewer_port,
            "cleanup_status": self.cleanup_status,
            "cleanup_error": self.cleanup_error,
            "metadata": _redact_metadata(self.metadata),
        }


class BrowserRuntimeProvider(Protocol):
    name: str
    default_recording_mode: str

    def start(self, task: dict[str, Any], time_limit_s: int) -> BrowserSession:
        """Start or reserve a browser runtime and return its CDP endpoint."""
        ...

    def finalize(self, session: BrowserSession, output_dir: Path) -> None:
        """Collect provider artifacts after the browser workload finishes."""
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
    if isinstance(value, str) and value.startswith(
        ("http://", "https://", "ws://", "wss://")
    ):
        return redact_cdp_url(value)
    return value


def redact_cdp_url(url: str) -> str:
    parsed = urllib.parse.urlsplit(url)
    query = urllib.parse.parse_qsl(parsed.query, keep_blank_values=True)
    if not query:
        return url
    redacted = []
    for key, val in query:
        normalized = key.lower().replace("-", "").replace("_", "")
        sensitive = any(
            part in normalized
            for part in ("apikey", "jwt", "token", "secret", "signingkey")
        )
        redacted.append((key, "[REDACTED]" if sensitive else val))
    return urllib.parse.urlunsplit(
        parsed._replace(query=urllib.parse.urlencode(redacted))
    )


class _BrowserbaseApiError(RuntimeError):
    def __init__(self, message: str, *, status: int | None = None) -> None:
        super().__init__(message)
        self.status = status


class _KernelApiError(RuntimeError):
    def __init__(self, message: str, *, status: int | None = None) -> None:
        super().__init__(message)
        self.status = status


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
    default_recording_mode = "x11"

    def start(self, task: dict[str, Any], time_limit_s: int) -> BrowserSession:
        return BrowserSession(
            provider=self.name,
            mode="local",
            cdp_url=DEFAULT_BROWSER_CDP_URL,
            recording_mode="x11",
            local_viewer_port=_pick_free_port(),
        )

    def finalize(self, session: BrowserSession, output_dir: Path) -> None:
        pass

    def cleanup(self, session: BrowserSession) -> None:
        session.cleanup_status = "not_required"


class RemoteCdpBrowserRuntimeProvider:
    name = "remote-cdp"
    default_recording_mode = "disabled"

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

    def finalize(self, session: BrowserSession, output_dir: Path) -> None:
        pass

    def cleanup(self, session: BrowserSession) -> None:
        session.cleanup_status = "not_required"


class SteelBrowserRuntimeProvider:
    name = "steel"
    default_recording_mode = "disabled"

    def __init__(self, *, options: dict[str, Any]) -> None:
        self.options = options

    def start(self, task: dict[str, Any], time_limit_s: int) -> BrowserSession:
        raise BrowserRuntimeError(
            "steel browser runtime is reserved but not implemented yet"
        )

    def finalize(self, session: BrowserSession, output_dir: Path) -> None:
        pass

    def cleanup(self, session: BrowserSession) -> None:
        session.cleanup_status = "not_required"


class BrowserbaseRuntimeProvider:
    name = "browserbase"
    default_recording_mode = "provider"

    def __init__(
        self,
        *,
        api_key: str | None,
        options: dict[str, Any],
        api_url: str = _BROWSERBASE_API_URL,
    ) -> None:
        unknown = sorted(set(options) - _BROWSERBASE_ALLOWED_OPTIONS)
        if unknown:
            allowed = ", ".join(sorted(_BROWSERBASE_ALLOWED_OPTIONS))
            raise BrowserRuntimeError(
                "browserbase runtime options contain unsupported field(s): "
                f"{', '.join(unknown)}; allowed fields: {allowed}"
            )
        browser_settings = options.get("browserSettings")
        if browser_settings is not None and not isinstance(browser_settings, dict):
            raise BrowserRuntimeError(
                "browserbase browserSettings option must be a JSON object"
            )
        for key in ("extensionId", "projectId", "region"):
            value = options.get(key)
            if value is not None and not isinstance(value, str):
                raise BrowserRuntimeError(f"browserbase {key} option must be a string")
        proxies = options.get("proxies")
        if proxies is not None and not isinstance(proxies, (bool, list)):
            raise BrowserRuntimeError(
                "browserbase proxies option must be a boolean or JSON array"
            )
        user_metadata = options.get("userMetadata")
        if user_metadata is not None and not isinstance(user_metadata, dict):
            raise BrowserRuntimeError(
                "browserbase userMetadata option must be a JSON object"
            )
        self.api_key = api_key
        self.options = options
        self.api_url = api_url.rstrip("/")

    def _request(
        self,
        method: str,
        path: str,
        payload: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        assert self.api_key is not None
        data = (
            json.dumps(payload, separators=(",", ":")).encode()
            if payload is not None
            else None
        )
        request = urllib.request.Request(
            f"{self.api_url}{path}",
            data=data,
            method=method,
            headers={
                "Content-Type": "application/json",
                "X-BB-API-Key": self.api_key,
            },
        )
        try:
            with urllib.request.urlopen(request, timeout=15) as response:
                raw = response.read()
        except urllib.error.HTTPError as e:
            if e.code in {401, 403}:
                message = "Browserbase authentication failed"
            elif e.code in {402, 429}:
                message = "Browserbase quota or concurrency limit was exceeded"
            else:
                message = f"Browserbase API returned HTTP {e.code}"
            raise _BrowserbaseApiError(message, status=e.code) from None
        except (urllib.error.URLError, TimeoutError, OSError) as e:
            reason = str(getattr(e, "reason", e))
            for secret in (
                self.api_key,
                urllib.parse.quote(self.api_key, safe=""),
                urllib.parse.quote_plus(self.api_key, safe=""),
            ):
                if secret:
                    reason = reason.replace(secret, "[REDACTED]")
            raise _BrowserbaseApiError(
                f"Browserbase API request failed: {reason}"
            ) from None

        try:
            result = json.loads(raw)
        except (json.JSONDecodeError, UnicodeDecodeError):
            raise _BrowserbaseApiError(
                "Browserbase API returned malformed JSON"
            ) from None
        if not isinstance(result, dict):
            raise _BrowserbaseApiError("Browserbase API returned non-object JSON")
        return result

    def _release(self, session_id: str) -> str:
        try:
            self._request(
                "POST",
                f"/sessions/{session_id}",
                {"status": "REQUEST_RELEASE"},
            )
        except _BrowserbaseApiError as e:
            if e.status in {404, 409}:
                return "already_closed"
            raise
        return "released"

    def start(self, task: dict[str, Any], time_limit_s: int) -> BrowserSession:
        if not self.api_key:
            raise BrowserRuntimeError(
                "browserbase browser runtime requires BROWSERBASE_API_KEY"
            )

        browser_settings = dict(self.options.get("browserSettings") or {})
        browser_settings["viewport"] = {"width": 1920, "height": 1080}
        browser_settings["recordSession"] = True
        payload = {
            key: value
            for key, value in self.options.items()
            if key != "browserSettings"
        }
        payload.update(
            {
                "browserSettings": browser_settings,
                # ClawBench keeps one CDP client attached for capture and
                # interception while the selected harness attaches another.
                "keepAlive": True,
                "timeout": min(21600, max(60, time_limit_s + 120)),
            }
        )
        try:
            result = self._request("POST", "/sessions", payload)
        except _BrowserbaseApiError as e:
            raise BrowserRuntimeError(str(e)) from None

        session_id = result.get("id")
        cdp_url = result.get("connectUrl")
        if not isinstance(session_id, str) or not session_id:
            raise BrowserRuntimeError(
                "Browserbase session response did not include a valid id"
            )
        if not isinstance(cdp_url, str) or not cdp_url.startswith(("ws://", "wss://")):
            try:
                self._release(session_id)
            except _BrowserbaseApiError:
                pass
            raise BrowserRuntimeError(
                "Browserbase session response did not include a valid connectUrl"
            )

        inspector_url = f"https://browserbase.com/sessions/{session_id}"
        return BrowserSession(
            provider=self.name,
            mode="remote",
            session_id=session_id,
            cdp_url=cdp_url,
            viewer_url=inspector_url,
            recording_url=inspector_url,
            metadata={
                "region": result.get("region"),
                "expires_at": result.get("expiresAt"),
                "keep_alive": True,
            },
            recording_mode="provider",
        )

    def finalize(self, session: BrowserSession, output_dir: Path) -> None:
        pass

    def cleanup(self, session: BrowserSession) -> None:
        if not session.session_id:
            session.cleanup_status = "not_required"
            return
        try:
            session.cleanup_status = self._release(session.session_id)
        except _BrowserbaseApiError as e:
            raise BrowserRuntimeError(str(e)) from None


class KernelRuntimeProvider:
    name = "kernel"
    default_recording_mode = "provider-download"

    def __init__(
        self,
        *,
        api_key: str | None,
        options: dict[str, Any],
        api_url: str = _KERNEL_API_URL,
        replay_poll_interval_s: float = 1,
        replay_poll_timeout_s: float = 300,
    ) -> None:
        unknown = sorted(set(options) - _KERNEL_ALLOWED_OPTIONS)
        if unknown:
            allowed = ", ".join(sorted(_KERNEL_ALLOWED_OPTIONS))
            raise BrowserRuntimeError(
                "kernel runtime options contain unsupported field(s): "
                f"{', '.join(unknown)}; allowed fields: {allowed}"
            )
        stealth = options.get("stealth")
        if stealth is not None and not isinstance(stealth, bool):
            raise BrowserRuntimeError("kernel stealth option must be a boolean")
        region = options.get("region")
        if region is not None and region not in {"us-east", "eu-west"}:
            raise BrowserRuntimeError(
                "kernel region option must be 'us-east' or 'eu-west'"
            )
        proxy = options.get("proxy")
        if proxy is not None and not isinstance(proxy, dict):
            raise BrowserRuntimeError("kernel proxy option must be a JSON object")
        tags = options.get("tags")
        if tags is not None and not isinstance(tags, dict):
            raise BrowserRuntimeError("kernel tags option must be a JSON object")
        self.api_key = api_key
        self.options = options
        self.api_url = api_url.rstrip("/")
        self.replay_poll_interval_s = replay_poll_interval_s
        self.replay_poll_timeout_s = replay_poll_timeout_s

    def _request_response(
        self,
        method: str,
        path: str,
        payload: dict[str, Any] | None = None,
        *,
        accept: str = "application/json",
    ) -> tuple[int, Any, bytes]:
        assert self.api_key is not None
        data = (
            json.dumps(payload, separators=(",", ":")).encode()
            if payload is not None
            else None
        )
        request = urllib.request.Request(
            f"{self.api_url}{path}",
            data=data,
            method=method,
            headers={
                "Accept": accept,
                "Authorization": f"Bearer {self.api_key}",
                **({"Content-Type": "application/json"} if data is not None else {}),
            },
        )
        try:
            with urllib.request.urlopen(request, timeout=30) as response:
                return (
                    int(getattr(response, "status", 200)),
                    getattr(response, "headers", {}),
                    response.read(),
                )
        except urllib.error.HTTPError as e:
            if e.code in {401, 403}:
                message = "Kernel authentication failed"
            elif e.code in {402, 429}:
                message = "Kernel quota or concurrency limit was exceeded"
            else:
                message = f"Kernel API returned HTTP {e.code}"
            raise _KernelApiError(message, status=e.code) from None
        except (urllib.error.URLError, TimeoutError, OSError) as e:
            reason = str(getattr(e, "reason", e))
            for secret in (
                self.api_key,
                urllib.parse.quote(self.api_key, safe=""),
                urllib.parse.quote_plus(self.api_key, safe=""),
            ):
                if secret:
                    reason = reason.replace(secret, "[REDACTED]")
            raise _KernelApiError(f"Kernel API request failed: {reason}") from None

    def _request(
        self,
        method: str,
        path: str,
        payload: dict[str, Any] | None = None,
        *,
        accept: str = "application/json",
    ) -> bytes:
        _status, _headers, raw = self._request_response(
            method,
            path,
            payload,
            accept=accept,
        )
        return raw

    def _request_json(
        self,
        method: str,
        path: str,
        payload: dict[str, Any] | None = None,
    ) -> Any:
        raw = self._request(method, path, payload)
        try:
            return json.loads(raw)
        except (json.JSONDecodeError, UnicodeDecodeError):
            raise _KernelApiError("Kernel API returned malformed JSON") from None

    def _delete(self, session_id: str) -> str:
        try:
            self._request("DELETE", f"/browsers/{session_id}")
        except _KernelApiError as e:
            if e.status == 404:
                return "already_closed"
            raise
        return "deleted"

    def session_exists(self, session_id: str) -> bool:
        """Return True if the provider still reports this browser session."""
        try:
            self._request("GET", f"/browsers/{session_id}")
        except _KernelApiError as e:
            if e.status == 404:
                return False
            raise
        return True

    def _stop_replay(self, session_id: str, replay_id: str) -> None:
        try:
            self._request(
                "POST",
                f"/browsers/{session_id}/replays/{replay_id}/stop",
            )
        except _KernelApiError as e:
            if e.status not in {404, 409}:
                raise

    def start(self, task: dict[str, Any], time_limit_s: int) -> BrowserSession:
        if not self.api_key:
            raise BrowserRuntimeError("kernel browser runtime requires KERNEL_API_KEY")

        timeout_seconds = min(259200, max(10, time_limit_s + 120))
        payload = {
            **self.options,
            "headless": False,
            "timeout_seconds": timeout_seconds,
            "viewport": {
                "width": 1920,
                "height": 1080,
                "refresh_rate": 25,
            },
        }
        try:
            result = self._request_json("POST", "/browsers", payload)
        except _KernelApiError as e:
            raise BrowserRuntimeError(str(e)) from None
        if not isinstance(result, dict):
            raise BrowserRuntimeError("Kernel browser response was not a JSON object")

        session_id = result.get("session_id")
        cdp_url = result.get("cdp_ws_url")
        viewer_url = result.get("browser_live_view_url")
        if not isinstance(session_id, str) or not session_id:
            raise BrowserRuntimeError(
                "Kernel browser response did not include a valid session_id"
            )
        if not isinstance(cdp_url, str) or not cdp_url.startswith(("ws://", "wss://")):
            try:
                self._delete(session_id)
            except _KernelApiError:
                pass
            raise BrowserRuntimeError(
                "Kernel browser response did not include a valid cdp_ws_url"
            )
        if not isinstance(viewer_url, str) or not viewer_url.startswith(
            ("http://", "https://")
        ):
            viewer_url = None

        try:
            replay = self._request_json(
                "POST",
                f"/browsers/{session_id}/replays",
                {
                    "framerate": 15,
                    "max_duration_in_seconds": timeout_seconds,
                },
            )
        except _KernelApiError as e:
            try:
                self._delete(session_id)
            except _KernelApiError:
                pass
            raise BrowserRuntimeError(str(e)) from None
        replay_id = replay.get("replay_id") if isinstance(replay, dict) else None
        if not isinstance(replay_id, str) or not replay_id:
            try:
                self._delete(session_id)
            except _KernelApiError:
                pass
            raise BrowserRuntimeError(
                "Kernel replay response did not include a valid replay_id"
            )

        return BrowserSession(
            provider=self.name,
            mode="remote",
            session_id=session_id,
            cdp_url=cdp_url,
            viewer_url=viewer_url,
            viewer_url_sensitive=viewer_url is not None,
            metadata={
                "region": result.get("region"),
                "replay_id": replay_id,
                "stealth": result.get("stealth"),
                "timeout_seconds": result.get("timeout_seconds"),
            },
            recording_mode="provider-download",
        )

    def finalize(self, session: BrowserSession, output_dir: Path) -> None:
        if not session.session_id:
            return
        replay_id = session.metadata.get("replay_id")
        if not isinstance(replay_id, str) or not replay_id:
            raise BrowserRuntimeError(
                "Kernel browser session is missing its replay_id",
                category="browser_runtime_artifact_failed",
            )

        try:
            self._stop_replay(session.session_id, replay_id)
            deadline = time.monotonic() + self.replay_poll_timeout_s
            while True:
                replays = self._request_json(
                    "GET", f"/browsers/{session.session_id}/replays"
                )
                if not isinstance(replays, list):
                    raise _KernelApiError(
                        "Kernel replay list response was not a JSON array"
                    )
                matching = next(
                    (
                        replay
                        for replay in replays
                        if isinstance(replay, dict)
                        and replay.get("replay_id") == replay_id
                    ),
                    None,
                )
                if matching and matching.get("finished_at"):
                    break
                if time.monotonic() >= deadline:
                    raise _KernelApiError(
                        "Kernel replay did not finish processing before timeout"
                    )
                time.sleep(self.replay_poll_interval_s)

            while True:
                status, headers, recording = self._request_response(
                    "GET",
                    f"/browsers/{session.session_id}/replays/{replay_id}",
                    accept="video/mp4",
                )
                if status != 202:
                    break
                if time.monotonic() >= deadline:
                    raise _KernelApiError(
                        "Kernel replay did not finish downloading before timeout"
                    )
                retry_after: str | None = (
                    headers.get("Retry-After") if headers else None
                )
                if retry_after is None:
                    delay = self.replay_poll_interval_s
                else:
                    try:
                        delay = float(retry_after)
                    except ValueError:
                        delay = self.replay_poll_interval_s
                time.sleep(min(max(0, delay), max(0, deadline - time.monotonic())))
            if status != 200:
                raise _KernelApiError(f"Kernel replay download returned HTTP {status}")
            if not recording:
                raise _KernelApiError("Kernel replay download was empty")
            recording_path = output_dir / "data" / "recording.mp4"
            recording_path.parent.mkdir(parents=True, exist_ok=True)
            recording_path.write_bytes(recording)
            session.metadata["recording_bytes"] = len(recording)
            session.metadata["replay_status"] = "downloaded"
        except (_KernelApiError, OSError) as e:
            raise BrowserRuntimeError(
                str(e), category="browser_runtime_artifact_failed"
            ) from None

    def cleanup(self, session: BrowserSession) -> None:
        if not session.session_id:
            session.cleanup_status = "not_required"
            return
        replay_id = session.metadata.get("replay_id")
        try:
            if (
                isinstance(replay_id, str)
                and replay_id
                and session.metadata.get("replay_status") != "downloaded"
            ):
                self._stop_replay(session.session_id, replay_id)
        except _KernelApiError:
            pass
        try:
            session.cleanup_status = self._delete(session.session_id)
        except _KernelApiError as e:
            raise BrowserRuntimeError(str(e)) from None


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
        api_key = _env_value(env, "BROWSERBASE_API_KEY")
        if not api_key:
            raise BrowserRuntimeError(
                "browserbase browser runtime requires BROWSERBASE_API_KEY"
            )
        return BrowserbaseRuntimeProvider(api_key=api_key, options=options)
    if runtime == "kernel":
        api_key = _env_value(env, "KERNEL_API_KEY")
        if not api_key:
            raise BrowserRuntimeError("kernel browser runtime requires KERNEL_API_KEY")
        return KernelRuntimeProvider(
            api_key=api_key,
            options=options,
            api_url=_env_value(env, "KERNEL_BASE_URL") or _KERNEL_API_URL,
        )
    raise BrowserRuntimeError(
        f"unknown browser runtime {runtime!r}; expected one of {BROWSER_RUNTIME_CHOICES}"
    )
