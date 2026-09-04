"""Stage-1 interceptor matching — the benchmark's deterministic ground truth.

Stage 1 asks one question: does this HTTP request hit the task's target
(``url_pattern`` regex + ``method`` + constant ``body``/``params`` fields)?
Every published Intercepted number is that answer.

It is computed in two places — live, in-container, by ``server.py`` next to
this file, and offline by ``clawbench.eval.edgebench_judge`` when it
re-verifies a submitted evidence archive. Those were hand-maintained copies
and they drifted, so offline judging could disagree with what actually
happened during a run. This module is the single copy both import.

Kept to the standard library on purpose: it is imported by the offline
verifier on the host, where the runtime-server's dependencies are absent.
"""

from __future__ import annotations

import re
from typing import Any
from urllib.parse import parse_qs, urlparse


def const_fields_match(expected: Any, actual: Any) -> bool:
    """All key/value pairs in ``expected`` are present in ``actual``.

    For list bodies (batched GraphQL) any single item matching is enough.
    An empty or absent ``expected`` constrains nothing and matches.
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


def query_params_from_url(url: str) -> dict[str, Any]:
    """Query string as a dict, collapsing single-valued keys to a scalar.

    A repeated key keeps its list of values, so ``?tag=a&tag=b`` is
    ``{"tag": ["a", "b"]}`` and does not match a constant of ``{"tag": "a"}``.
    The offline verifier used to take ``v[0]`` unconditionally and so called
    that request intercepted when the live interceptor had let it through.
    """
    parsed = urlparse(str(url or ""))
    return {k: v[0] if len(v) == 1 else v for k, v in parse_qs(parsed.query).items()}


def url_pattern_matches(url_pattern: str, url: str) -> bool:
    """Whether ``url`` matches the task's target regex.

    A malformed pattern is a task-authoring error, not a request that should
    be intercepted, so it is reported as no-match. It must never raise: this
    runs inside the CDP event loop, where an exception stops interception for
    the remainder of the run and silently zeroes the task's Stage-1 score.
    """
    if not url_pattern:
        return False
    try:
        return re.search(url_pattern, str(url or "")) is not None
    except re.error:
        return False


def stage1_match(request: dict[str, Any], eval_schema: Any) -> bool:
    """Whether ``request`` hits the target described by ``eval_schema``.

    ``request`` carries ``url``, ``method``, and a parsed ``body``. Query
    params are always derived from the URL rather than read off the request:
    offline, a submitted ``params`` field is agent-controlled and could be
    forged.

    An absent or empty ``url_pattern`` means there is no target to verify
    against and returns False. Live, that case is handled earlier — the
    interceptor is simply never armed and no request is ever blocked.
    """
    if not isinstance(eval_schema, dict):
        return False

    url = str(request.get("url") or "")
    if not url_pattern_matches(eval_schema.get("url_pattern") or "", url):
        return False

    method = eval_schema.get("method")
    if method and request.get("method") != method:
        return False

    if not const_fields_match(eval_schema.get("body"), request.get("body")):
        return False

    return const_fields_match(eval_schema.get("params"), query_params_from_url(url))
