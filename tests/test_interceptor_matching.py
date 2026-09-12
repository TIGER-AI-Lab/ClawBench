"""Stage-1 interception matching has one implementation, and both users agree.

The live interceptor (``runtime-server/server.py``) and the offline judge
(``eval/edgebench_judge.py``) used to carry hand-maintained copies of the
matching predicate — the benchmark's deterministic ground truth — and only the
copy that never ran in production had tests (#301). Both now import
``runtime/shared/matching.py``; these tests pin the predicate's behaviour and
the wiring on both sides.
"""

from __future__ import annotations

import importlib.util
import re
import sys
from pathlib import Path
from typing import Any

import pytest

from clawbench.eval import edgebench_judge
from clawbench.runner.run_support.task import validate_task_data
from clawbench.runtime.shared import matching
from clawbench.runtime.shared.matching import (
    InvalidUrlPattern,
    compile_url_pattern,
    const_fields_match,
    parse_body,
    query_params_from_url,
    stage1_match,
    stage1_match_schema,
)
from clawbench.utils.paths import RUNTIME_ROOT

SERVER_PY = RUNTIME_ROOT / "runtime-server" / "server.py"
MATCHING_PY = RUNTIME_ROOT / "shared" / "matching.py"


def _schema(**overrides: Any) -> dict[str, Any]:
    schema: dict[str, Any] = {
        "url_pattern": r"example\.com/api/submit",
        "method": "POST",
    }
    schema.update(overrides)
    return schema


def _request(**overrides: Any) -> dict[str, Any]:
    request: dict[str, Any] = {
        "url": "https://example.com/api/submit",
        "method": "POST",
        "body": {"action": "book"},
    }
    request.update(overrides)
    return request


# ---------------------------------------------------------------------------
# The fixture matrix: url_pattern / method / body / params, plus the regex
# edge cases from #258.
# ---------------------------------------------------------------------------

MATRIX: list[tuple[str, Any, dict[str, Any], bool]] = [
    ("plain hit", _schema(), _request(), True),
    ("url miss", _schema(), _request(url="https://example.com/api/other"), False),
    (
        "regex is a search, not a full match",
        _schema(url_pattern="submit"),
        _request(),
        True,
    ),
    ("method mismatch", _schema(), _request(method="GET"), False),
    ("method unconstrained", _schema(method=None), _request(method="GET"), True),
    (
        "body subset matches",
        _schema(body={"action": "book"}),
        _request(body={"action": "book", "extra": 1}),
        True,
    ),
    ("body value differs", _schema(body={"action": "cancel"}), _request(), False),
    (
        "body required but absent",
        _schema(body={"action": "book"}),
        _request(body=None),
        False,
    ),
    ("body constraint empty", _schema(body={}), _request(body=None), True),
    (
        "batched graphql: any item matches",
        _schema(body={"operationName": "Submit"}),
        _request(body=[{"operationName": "Other"}, {"operationName": "Submit"}]),
        True,
    ),
    (
        "string body cannot satisfy a dict constraint",
        _schema(body={"a": 1}),
        _request(body="raw"),
        False,
    ),
    (
        "params from url",
        _schema(params={"id": "5"}),
        _request(url="https://example.com/api/submit?id=5"),
        True,
    ),
    (
        "params value differs",
        _schema(params={"id": "6"}),
        _request(url="https://example.com/api/submit?id=5"),
        False,
    ),
    (
        "params: a submitted params field is ignored",
        _schema(params={"id": "5"}),
        _request(url="https://example.com/api/submit", params={"id": "5"}),
        False,
    ),
    (
        "repeated query key is a list",
        _schema(params={"tag": ["a", "b"]}),
        _request(url="https://example.com/api/submit?tag=a&tag=b"),
        True,
    ),
    (
        "repeated query key does not collapse to its first value",
        _schema(params={"tag": "a"}),
        _request(url="https://example.com/api/submit?tag=a&tag=b"),
        False,
    ),
    # #258 edge cases.
    ("empty pattern intercepts nothing", _schema(url_pattern=""), _request(), False),
    ("missing pattern intercepts nothing", {"method": "POST"}, _request(), False),
    (
        "malformed pattern fails closed, does not raise",
        _schema(url_pattern="submit("),
        _request(),
        False,
    ),
    ("schema is not an object", "nope", _request(), False),
]


@pytest.mark.parametrize(
    ("schema", "req", "expected"),
    [case[1:] for case in MATRIX],
    ids=[case[0] for case in MATRIX],
)
def test_stage1_decision(schema: Any, req: dict[str, Any], expected: bool) -> None:
    assert stage1_match_schema(req, schema) is expected


@pytest.mark.parametrize(
    ("schema", "req"),
    [case[1:3] for case in MATRIX],
    ids=[case[0] for case in MATRIX],
)
def test_offline_judge_agrees_with_the_shared_predicate(
    schema: Any, req: dict[str, Any]
) -> None:
    """The judge's entry point is the shared function, not a mirror of it."""
    assert edgebench_judge._stage1_match(req, schema) is stage1_match_schema(
        req, schema
    )


# ---------------------------------------------------------------------------
# Building blocks
# ---------------------------------------------------------------------------


def test_compile_url_pattern_distinguishes_empty_from_malformed() -> None:
    assert compile_url_pattern("") is None
    assert compile_url_pattern(None) is None
    assert isinstance(compile_url_pattern(r"a\.b"), re.Pattern)
    with pytest.raises(InvalidUrlPattern, match="invalid url_pattern"):
        compile_url_pattern("submit(")
    with pytest.raises(InvalidUrlPattern, match="must be a string"):
        compile_url_pattern(["not", "a", "pattern"])


def test_stage1_match_never_matches_without_a_pattern() -> None:
    assert (
        stage1_match(
            url="https://example.com/x",
            method="POST",
            body=None,
            url_pattern=None,
            required_method=None,
            match_body=None,
            match_params=None,
        )
        is False
    )


def test_parse_body_prefers_json_then_form_then_raw() -> None:
    assert parse_body(None) is None
    assert parse_body("") is None
    assert parse_body('{"a": 1}') == {"a": 1}
    assert parse_body("a=1&b=2&b=3") == {"a": "1", "b": ["2", "3"]}
    assert parse_body("a=") == {"a": ""}
    # Bare text is form-parsed as a blank-valued key — long-standing interceptor
    # behaviour, pinned here so the judge cannot quietly diverge from it.
    assert parse_body("just text") == {"just text": ""}
    assert parse_body("&") == "&"


def test_query_params_keep_repeated_keys() -> None:
    assert query_params_from_url("https://x/?a=1&b=2&b=3") == {
        "a": "1",
        "b": ["2", "3"],
    }
    assert query_params_from_url("https://x/") == {}


def test_const_fields_match_semantics() -> None:
    assert const_fields_match(None, None) is True
    assert const_fields_match({}, None) is True
    assert const_fields_match({"a": 1}, None) is False
    assert const_fields_match({"a": 1}, {"a": 1, "b": 2}) is True
    assert const_fields_match({"a": 1}, [{"a": 2}, {"a": 1}]) is True
    assert const_fields_match({"a": 1}, "a=1") is False


# ---------------------------------------------------------------------------
# A malformed pattern is caught before a container is paid for.
# ---------------------------------------------------------------------------


def test_task_validation_rejects_a_malformed_url_pattern(tmp_path: Path) -> None:
    task = {
        "instruction": "do it",
        "eval_schema": {"url_pattern": "submit(", "method": "POST"},
        "time_limit": 5,
    }
    with pytest.raises(ValueError, match="not a valid regex"):
        validate_task_data(task, tmp_path / "task.json")


# ---------------------------------------------------------------------------
# Wiring: the live interceptor really does use the shared module.
# ---------------------------------------------------------------------------


def test_server_imports_the_shared_matcher_and_keeps_no_copy() -> None:
    source = SERVER_PY.read_text(encoding="utf-8")

    assert "from matching import" in source
    assert "stage1_match(" in source
    assert "compile_url_pattern(" in source
    # No second implementation, and no per-request re.search that can raise
    # inside the CDP loop.
    assert "def _const_fields_match" not in source
    assert "def _parse_body" not in source
    assert "re.search(" not in source


@pytest.mark.parametrize(
    "dockerfile",
    [
        RUNTIME_ROOT / "harnesses" / "base" / "Dockerfile.base",
        RUNTIME_ROOT / "harbor" / "Dockerfile",
    ],
    ids=["base", "harbor"],
)
def test_runtime_images_ship_the_shared_matcher_next_to_server(
    dockerfile: Path,
) -> None:
    source = dockerfile.read_text(encoding="utf-8")

    assert "COPY shared/matching.py ./src/runtime-server/matching.py" in source


def test_shared_matcher_is_stdlib_only_and_loads_as_a_top_level_module() -> None:
    """Inside the container it is imported as bare `matching`, with no package."""
    source = MATCHING_PY.read_text(encoding="utf-8")
    imported = re.findall(r"^(?:from|import)\s+([\w.]+)", source, re.MULTILINE)
    assert all(name.split(".")[0] in sys.stdlib_module_names for name in imported), (
        imported
    )

    spec = importlib.util.spec_from_file_location("matching", MATCHING_PY)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)

    request = _request(url="https://example.com/api/submit?id=5")
    assert module.stage1_match_schema(request, _schema(params={"id": "5"})) is True
    # And it is byte-for-byte the module the host side imports.
    assert module.stage1_match_schema.__code__.co_code == (
        matching.stage1_match_schema.__code__.co_code
    )
