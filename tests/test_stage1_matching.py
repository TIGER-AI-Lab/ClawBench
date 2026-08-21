"""Stage-1 matching is one predicate, shared by the live and offline paths.

The interceptor decision is the benchmark's deterministic ground truth: it sets
run-meta.intercepted and every published Intercepted number. It used to exist as
two hand-maintained copies -- runtime-server/server.py in-container and a mirror
in eval/edgebench_judge.py -- and only the mirror had tests. They drifted, so
offline re-verification could disagree with what actually happened during a run.
"""

from __future__ import annotations

import inspect
from pathlib import Path
from typing import Any

import pytest

from clawbench.eval import edgebench_judge as ej
from clawbench.utils.paths import RUNTIME_ROOT

matching = ej._matching

SERVER_PY = RUNTIME_ROOT / "runtime-server" / "server.py"
MATCHING_PY = RUNTIME_ROOT / "runtime-server" / "matching.py"


# --- the drift that was actually shipping ------------------------------------


def test_repeated_query_params_do_not_match_a_scalar_constant() -> None:
    """The divergence with teeth.

    The live interceptor keeps a repeated key's values as a list, so
    ?tag=a&tag=b never matched a constant of {"tag": "a"} and the request was
    let through. The offline mirror took v[0] unconditionally, matched, and
    reported the run as intercepted -- a Stage-1 pass for a request that was
    never blocked.
    """
    schema = {"url_pattern": r"/api/cart", "params": {"tag": "a"}}
    request = {"url": "https://shop.test/api/cart?tag=a&tag=b", "method": "GET"}

    assert matching.query_params_from_url(request["url"]) == {"tag": ["a", "b"]}
    assert ej._stage1_match(request, schema) is False


def test_single_valued_query_params_still_collapse_to_a_scalar() -> None:
    schema = {"url_pattern": r"/api/cart", "params": {"tag": "a"}}
    request = {"url": "https://shop.test/api/cart?tag=a", "method": "GET"}

    assert matching.query_params_from_url(request["url"]) == {"tag": "a"}
    assert ej._stage1_match(request, schema) is True


@pytest.mark.parametrize("pattern", ["foo(", "[", "*bad", "(?P<x>a)(?P<x>b)"])
def test_a_malformed_url_pattern_is_a_no_match_and_never_raises(pattern: str) -> None:
    """server.py called re.search unguarded inside the CDP event loop, so a
    malformed pattern raised there and stopped interception for the rest of the
    run -- every later task in that run silently scored Stage-1 zero.
    """
    assert matching.url_pattern_matches(pattern, "https://t.ex/x") is False
    assert (
        ej._stage1_match({"url": "https://t.ex/x"}, {"url_pattern": pattern}) is False
    )


def test_an_empty_url_pattern_matches_nothing() -> None:
    """Live, an empty pattern means the interceptor is never armed. Offline it
    means there is no target to verify against. Both are 'not intercepted'."""
    assert matching.url_pattern_matches("", "https://t.ex/x") is False
    assert ej._stage1_match({"url": "https://t.ex/x"}, {"url_pattern": ""}) is False


# --- fixture matrix ----------------------------------------------------------

CASES: list[tuple[str, dict[str, Any], Any, bool]] = [
    (
        "url+method hit",
        {"url": "https://t.ex/checkout", "method": "POST"},
        {"url_pattern": r"/checkout", "method": "POST"},
        True,
    ),
    (
        "method mismatch",
        {"url": "https://t.ex/checkout", "method": "GET"},
        {"url_pattern": r"/checkout", "method": "POST"},
        False,
    ),
    (
        "method unconstrained",
        {"url": "https://t.ex/checkout", "method": "DELETE"},
        {"url_pattern": r"/checkout"},
        True,
    ),
    (
        "url miss",
        {"url": "https://t.ex/browse", "method": "POST"},
        {"url_pattern": r"/checkout", "method": "POST"},
        False,
    ),
    (
        "const body hit",
        {"url": "https://t.ex/c", "method": "POST", "body": {"sku": "A1", "qty": 2}},
        {"url_pattern": r"/c", "body": {"sku": "A1"}},
        True,
    ),
    (
        "const body wrong value",
        {"url": "https://t.ex/c", "method": "POST", "body": {"sku": "B2"}},
        {"url_pattern": r"/c", "body": {"sku": "A1"}},
        False,
    ),
    (
        "const body missing on empty body",
        {"url": "https://t.ex/c", "method": "POST", "body": None},
        {"url_pattern": r"/c", "body": {"sku": "A1"}},
        False,
    ),
    (
        "batched graphql list body - any item matches",
        {
            "url": "https://t.ex/gql",
            "method": "POST",
            "body": [{"op": "noise"}, {"op": "checkout"}],
        },
        {"url_pattern": r"/gql", "body": {"op": "checkout"}},
        True,
    ),
    (
        "list body with no matching item",
        {"url": "https://t.ex/gql", "method": "POST", "body": [{"op": "noise"}]},
        {"url_pattern": r"/gql", "body": {"op": "checkout"}},
        False,
    ),
    (
        "scalar body cannot satisfy a const constraint",
        {"url": "https://t.ex/c", "method": "POST", "body": "raw-text"},
        {"url_pattern": r"/c", "body": {"sku": "A1"}},
        False,
    ),
    (
        "params derived from the url, not the request",
        {"url": "https://t.ex/s?id=7", "method": "GET", "params": {"id": "forged"}},
        {"url_pattern": r"/s", "params": {"id": "7"}},
        True,
    ),
    (
        "forged params field cannot fake a match",
        {"url": "https://t.ex/s?id=1", "method": "GET", "params": {"id": "7"}},
        {"url_pattern": r"/s", "params": {"id": "7"}},
        False,
    ),
    (
        "empty constraints constrain nothing",
        {"url": "https://t.ex/c", "method": "POST", "body": {}},
        {"url_pattern": r"/c", "body": {}, "params": {}},
        True,
    ),
    (
        "non-dict schema",
        {"url": "https://t.ex/c", "method": "POST"},
        None,
        False,
    ),
]


@pytest.mark.parametrize(
    ("name", "request_obj", "schema", "expected"),
    CASES,
    ids=[c[0] for c in CASES],
)
def test_stage1_matrix(
    name: str, request_obj: dict[str, Any], schema: Any, expected: bool
) -> None:
    assert matching.stage1_match(request_obj, schema) is expected
    assert ej._stage1_match(request_obj, schema) is expected


# --- the duplication itself --------------------------------------------------


def test_the_offline_verifier_does_not_reimplement_the_predicate() -> None:
    src = Path(ej.__file__).read_text(encoding="utf-8")

    assert "def _const_fields_match" not in src
    assert "re.search" not in src
    assert inspect.getsource(ej._stage1_match).count("_matching.stage1_match") == 1


def test_the_live_interceptor_does_not_reimplement_the_predicate() -> None:
    src = SERVER_PY.read_text(encoding="utf-8")

    assert "def _const_fields_match" not in src
    assert "re.search" not in src
    assert "from matching import" in src


def test_the_matcher_has_no_runtime_server_dependencies() -> None:
    """edgebench_judge loads this module on the host, where the runtime-server's
    own dependencies (fastapi, websocket) are not installed."""
    src = MATCHING_PY.read_text(encoding="utf-8")

    for third_party in ("fastapi", "websocket", "uvicorn"):
        assert f"import {third_party}" not in src


# --- the module has to reach the container -----------------------------------


@pytest.mark.parametrize(
    "dockerfile", ["harbor/Dockerfile", "harnesses/base/Dockerfile.base"]
)
def test_every_image_that_ships_server_py_also_ships_matching_py(
    dockerfile: str,
) -> None:
    """server.py imports matching.py at startup. An image with one and not the
    other fails to boot the runtime-server, which is the whole benchmark.
    """
    text = (RUNTIME_ROOT / dockerfile).read_text(encoding="utf-8")

    assert "COPY runtime-server/server.py" in text
    assert "COPY runtime-server/matching.py" in text
