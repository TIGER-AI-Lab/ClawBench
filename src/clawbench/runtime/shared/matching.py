"""Stage-1 interception matching — the one copy of the benchmark's ground truth.

The decision "does this HTTP request hit the task's target?" is made in two
places that must agree exactly:

* ``runtime-server/server.py`` — live, inside the container, deciding which
  request to block and record as ``interception.json``.
* ``eval/edgebench_judge.py`` — offline, re-deriving Stage 1 from submitted
  evidence rather than trusting the agent's own flag.

They used to be two hand-maintained copies, and they had drifted: one kept
repeated query keys as a list while the other silently took the first value,
and one caught a malformed ``url_pattern`` while the other let ``re.error``
escape inside the CDP loop and kill interception for the rest of the run.
Both now import this module.

Keep this file **stdlib-only**. It is copied verbatim into the runtime image
next to ``server.py`` (see ``harnesses/base/Dockerfile.base``), where none of
the ``clawbench`` package is installed.
"""

from __future__ import annotations

import json
import re
from typing import Any
from urllib.parse import parse_qs, urlparse


class InvalidUrlPattern(ValueError):
    """A task's ``eval_schema.url_pattern`` is not a valid regular expression."""


def compile_url_pattern(url_pattern: Any) -> re.Pattern[str] | None:
    """Compile a task's ``url_pattern`` once, up front.

    Returns ``None`` for an empty or missing pattern, which means "log requests
    but intercept nothing". Raises :class:`InvalidUrlPattern` for a malformed
    one so the failure surfaces when the schema is loaded, not on the first
    request that happens to arrive.
    """
    if not url_pattern:
        return None
    if not isinstance(url_pattern, str):
        raise InvalidUrlPattern(
            f"url_pattern must be a string, got {type(url_pattern).__name__}"
        )
    try:
        return re.compile(url_pattern)
    except re.error as e:
        raise InvalidUrlPattern(f"invalid url_pattern {url_pattern!r}: {e}") from e


def const_fields_match(expected: Any, actual: Any) -> bool:
    """Every key/value in ``expected`` is present, equal, in ``actual``.

    A list ``actual`` (a batched GraphQL body) matches if any item matches.
    An empty ``expected`` places no constraint and always matches.
    """
    if not expected:
        return True
    if not actual:
        return False
    if isinstance(actual, list):
        return any(const_fields_match(expected, item) for item in actual)
    if not isinstance(actual, dict):
        return False
    return all(actual.get(k) == v for k, v in expected.items())


def parse_body(post_data: Any) -> Any:
    """Structure a raw request body: JSON, then form-encoded, else the raw text."""
    if not post_data:
        return None
    try:
        return json.loads(post_data)
    except (json.JSONDecodeError, TypeError):
        pass
    try:
        parsed = parse_qs(post_data, keep_blank_values=True)
    except (TypeError, ValueError, AttributeError):
        return post_data
    if parsed:
        return {k: v[0] if len(v) == 1 else v for k, v in parsed.items()}
    return post_data


def query_params_from_url(url: str) -> dict[str, Any]:
    """Query parameters of ``url``; a repeated key becomes a list.

    Always derived from the URL itself — never from a caller-supplied
    ``params`` field, which submitted evidence could forge.
    """
    return {
        k: v[0] if len(v) == 1 else v for k, v in parse_qs(urlparse(url).query).items()
    }


def stage1_match(
    *,
    url: str,
    method: str | None,
    body: Any,
    url_pattern: re.Pattern[str] | None,
    required_method: str | None,
    match_body: Any,
    match_params: Any,
) -> bool:
    """The Stage-1 decision: does this request hit the task's target?

    ``url_pattern`` is a compiled pattern (see :func:`compile_url_pattern`);
    ``None`` never matches. ``body`` is the already-structured request body
    (see :func:`parse_body`). Query parameters are read from ``url``.
    """
    if url_pattern is None:
        return False
    if not url_pattern.search(url):
        return False
    if required_method and method != required_method:
        return False
    if not const_fields_match(match_body, body):
        return False
    return const_fields_match(match_params, query_params_from_url(url))


def stage1_match_schema(request: dict[str, Any], eval_schema: Any) -> bool:
    """:func:`stage1_match` driven straight from a task's ``eval_schema``.

    A schema that is missing, has no ``url_pattern``, or has a malformed one
    cannot confirm an interception and returns ``False`` rather than raising —
    this is the offline-judge entry point, where a bad schema must fail closed.
    """
    if not isinstance(eval_schema, dict):
        return False
    try:
        pattern = compile_url_pattern(eval_schema.get("url_pattern"))
    except InvalidUrlPattern:
        return False
    return stage1_match(
        url=str(request.get("url") or ""),
        method=request.get("method"),
        body=request.get("body"),
        url_pattern=pattern,
        required_method=eval_schema.get("method"),
        match_body=eval_schema.get("body"),
        match_params=eval_schema.get("params"),
    )
