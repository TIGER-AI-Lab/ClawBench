"""Offline checks for the privacy-rights task suite.

These tasks end in a write: a privacy request that a real company would act on.
The interceptor therefore has to catch every submission the form can make, not
just the correct one, or a wrong choice by the agent leaves the container as a
real request. Each task's ``eval_schema`` is URL + method only, and the request
details (right, jurisdiction, relationship, data minimisation) are graded by the
Stage-2 judge from ``judge_context``. These tests pin both halves.
"""

from __future__ import annotations

import json
import re
from pathlib import Path

import pytest
from jsonschema import Draft202012Validator

from clawbench.eval.edgebench_judge import _stage1_match
from clawbench.runner.judge import _build_user_msg
from clawbench.runner.run_support.task import validate_task_data
from clawbench.utils.paths import SHARED_ROOT, asset_path

SUITE = asset_path("test-cases", "privacy-rights")

RIGHT_UUIDS = {
    "access": "dd77bd74-82c0-4422-9bab-f4e4b9b3b488",
    "deletion": "a36c5aaf-bda3-4209-8b19-52fab1af9644",
    "data_portability": "9f60a409-0dee-4bc7-8574-1ccba1c551f7",
    "pause_processing": "0353ef85-527b-4da0-a89c-1d0ef331f520",
    "rectification": "55a8998a-9540-460a-9cc4-6f1eaf797f13",
    "opt_out": "e1081f5d-3388-4949-8339-841faba8a991",
}

ONETRUST_SUBMIT = "https://privacyportal.onetrust.com/request/v1/dsarrequestqueue"


def _load() -> list[tuple[str, dict]]:
    if not SUITE.is_dir():
        pytest.skip("privacy-rights suite not bundled")
    return [
        (path.parent.name, json.loads(path.read_text(encoding="utf-8")))
        for path in sorted(SUITE.glob("*/task.json"))
    ]


TASKS = _load()
DATAGRAIL = [(n, t) for n, t in TASKS if t["metadata"]["intake_vendor"] == "datagrail"]
ONETRUST = [(n, t) for n, t in TASKS if t["metadata"]["intake_vendor"] == "onetrust"]


def _host(task: dict) -> str:
    return task["metadata"]["sites_involved"][0]


def _intercepts(
    task: dict, url: str, method: str = "POST", body: object = None
) -> bool:
    return _stage1_match(
        {"url": url, "method": method, "body": body}, task["eval_schema"]
    )


def _policy(task: dict) -> str:
    match = re.search(
        r"privacy_request_policy_id is ([0-9a-f-]{36})", task["judge_context"]["rubric"]
    )
    assert match, "rubric does not name a policy id"
    return match.group(1)


def _dg_body(task: dict, *, right: str | None = None, location: str = "CA-ON") -> dict:
    policy = _policy(task)
    return {
        "location": location,
        "h-captcha-response": "P1_token",
        "answers": {"first_name": "Alex", "last_name": "Green"},
        "privacy_right_id": RIGHT_UUIDS[right or task["metadata"]["privacy_right"]],
        "privacy_request_policy_id": policy,
    }


# --------------------------------------------------------------------------
# Shape
# --------------------------------------------------------------------------


def test_suite_has_twelve_tasks_with_unique_ids() -> None:
    assert len(TASKS) == 12
    ids = [t["metadata"]["task_id"] for _, t in TASKS]
    assert len(set(ids)) == 12
    assert all(610001 <= i <= 610012 for i in ids)


def test_suite_covers_every_datagrail_right_and_two_vendors() -> None:
    rights = {t["metadata"]["privacy_right"] for _, t in DATAGRAIL}
    assert rights == set(RIGHT_UUIDS)
    assert len(DATAGRAIL) == 10 and len(ONETRUST) == 2
    # Ten DataGrail tasks, ten different companies.
    assert len({_host(t) for _, t in DATAGRAIL}) == 10


@pytest.mark.parametrize("name,task", TASKS, ids=[n for n, _ in TASKS])
def test_task_validates_against_schema_and_runner(name: str, task: dict) -> None:
    schema = json.loads(
        asset_path("test-cases", "task.schema.json").read_text(encoding="utf-8")
    )
    errors = list(Draft202012Validator(schema).iter_errors(task))
    assert errors == [], [e.message for e in errors]
    assert validate_task_data(task, Path(name) / "task.json") is task
    assert task["metadata"]["metaclass"] == "privacy-rights"


# --------------------------------------------------------------------------
# Leak safety: every submission is intercepted
# --------------------------------------------------------------------------


@pytest.mark.parametrize("name,task", TASKS, ids=[n for n, _ in TASKS])
def test_interception_has_no_body_or_param_filters(name: str, task: dict) -> None:
    """A body filter would let a wrong request type through to the company."""
    assert set(task["eval_schema"]) == {"url_pattern", "method"}
    assert task["eval_schema"]["method"] == "POST"


@pytest.mark.parametrize("name,task", DATAGRAIL, ids=[n for n, _ in DATAGRAIL])
def test_datagrail_every_submission_is_intercepted(name: str, task: dict) -> None:
    host = _host(task)
    for path in ("/api/v2/privacy_requests", "/api/v2/opt_outs"):
        for suffix in ("", "?locale=en", "#x"):
            url = f"https://{host}{path}{suffix}"
            for right in RIGHT_UUIDS:
                for location in ("CA-ON", "US-CA", "GB"):
                    body = _dg_body(task, right=right, location=location)
                    assert _intercepts(task, url, body=body), (url, right, location)
            assert _intercepts(task, url, body=None)


@pytest.mark.parametrize("name,task", DATAGRAIL, ids=[n for n, _ in DATAGRAIL])
def test_datagrail_page_traffic_is_not_intercepted(name: str, task: dict) -> None:
    """Page-load calls must pass, or the run would end before the form renders."""
    host = _host(task)
    passes = [
        ("POST", f"https://{host}/api/v2/tokens"),
        ("GET", f"https://{host}/api/v2/privacy_requests"),
        ("GET", f"https://{host}/api/v2/captcha"),
        (
            "GET",
            f"https://{host}/api/v2/privacy_request_center_content?page=landing_page",
        ),
        ("POST", "https://api.hcaptcha.com/checkcaptcha/c0e4e5ba/abc"),
        ("POST", f"https://{host}.evil.test/api/v2/privacy_requests"),
        ("POST", f"https://evil.test/{host}/api/v2/privacy_requests"),
        ("POST", f"https://{host}/api/v2/privacy_requests_archive"),
    ]
    for method, url in passes:
        assert not _intercepts(task, url, method=method), (method, url)


def test_datagrail_tasks_do_not_intercept_each_other() -> None:
    for name, task in DATAGRAIL:
        for other_name, other in DATAGRAIL:
            if other_name == name:
                continue
            url = f"https://{_host(other)}/api/v2/privacy_requests"
            assert not _intercepts(task, url), (name, other_name)


@pytest.mark.parametrize("name,task", ONETRUST, ids=[n for n, _ in ONETRUST])
def test_onetrust_submission_and_attachment_upload_are_intercepted(
    name: str, task: dict
) -> None:
    for url in (
        ONETRUST_SUBMIT,
        ONETRUST_SUBMIT + "?x=1",
        "https://privacyportal-eu.onetrust.com/request/v1/dsarrequestqueue",
        "https://privacyportal.onetrust.com/dsdocument/v1/documents",
    ):
        assert _intercepts(task, url, body={"requestTypes": ["anything"]}), url


@pytest.mark.parametrize("name,task", ONETRUST, ids=[n for n, _ in ONETRUST])
def test_onetrust_page_traffic_is_not_intercepted(name: str, task: dict) -> None:
    for method, url in (
        ("GET", task["instruction"].split()[1].rstrip(",")),
        (
            "GET",
            "https://privacyportal-cdn.onetrust.com/dsarwebform/x/y-locations.json",
        ),
        ("POST", "https://captcha.onetrust.com/bc/botdetectcaptcha?get=html"),
        ("GET", ONETRUST_SUBMIT),
        (
            "POST",
            "https://privacyportal.onetrust.com.evil.test/request/v1/dsarrequestqueue",
        ),
    ):
        assert not _intercepts(task, url, method=method), (method, url)


# --------------------------------------------------------------------------
# The judge gets what it needs to grade
# --------------------------------------------------------------------------


@pytest.mark.parametrize("name,task", DATAGRAIL, ids=[n for n, _ in DATAGRAIL])
def test_datagrail_rubric_names_the_right_and_the_ontario_policy(
    name: str, task: dict
) -> None:
    rubric = task["judge_context"]["rubric"]
    right = task["metadata"]["privacy_right"]
    assert f"privacy_right_id is {RIGHT_UUIDS[right]}" in rubric
    assert '"CA-ON"' in rubric
    assert task["instruction"].startswith(f"Open https://{_host(task)}/")
    reference = task["judge_context"]["reference_solution"]
    body = json.loads(reference[reference.index("{") :])
    assert body["privacy_right_id"] == RIGHT_UUIDS[right]
    assert body["location"] == "CA-ON"
    assert body["privacy_request_policy_id"] in rubric


def test_datagrail_policy_ids_are_per_company() -> None:
    policies = [_policy(t) for _, t in DATAGRAIL]
    assert len(set(policies)) == len(policies)


def test_opt_out_task_points_the_judge_at_the_opt_out_endpoint() -> None:
    (task,) = [t for _, t in DATAGRAIL if t["metadata"]["privacy_right"] == "opt_out"]
    rubric = task["judge_context"]["rubric"]
    assert "/api/v2/opt_outs" in rubric
    # The opt-out client sends no country or state codes, so requiring them
    # would fail every correct run.
    assert 'country_code is "CA"' not in rubric
    assert 'state_code is "ON"' not in rubric
    others = [t for _, t in DATAGRAIL if t["metadata"]["privacy_right"] != "opt_out"]
    assert all('country_code is "CA"' in t["judge_context"]["rubric"] for t in others)


@pytest.mark.parametrize("name,task", TASKS, ids=[n for n, _ in TASKS])
def test_minimisation_identifiers_match_the_persona(name: str, task: dict) -> None:
    """The rubric quotes the persona's identifiers; keep them in step with the file."""
    persona = json.loads(
        (SHARED_ROOT / "alex_green_personal_info.json").read_text(encoding="utf-8")
    )
    ids = persona["government_ids"]
    rubric = task["judge_context"]["rubric"]
    for value in (
        ids["sin"],
        ids["health_card"]["number"],
        ids["passport"]["number"],
        ids["drivers_license"]["number"],
    ):
        assert value in rubric
    assert "Toronto, Ontario, Canada" in task["instruction"]


def test_correction_tasks_quote_the_persona_address() -> None:
    persona = json.loads(
        (SHARED_ROOT / "alex_green_personal_info.json").read_text(encoding="utf-8")
    )
    home = persona["address"]["home"]
    (task,) = [t for n, t in DATAGRAIL if n == "harrys_correct_home_address"]
    rubric = task["judge_context"]["rubric"]
    for part in (home["unit"], home["street"], home["city"], home["postal_code"]):
        assert part in rubric


def test_judge_sees_the_discriminating_fields_past_a_captcha_token() -> None:
    """DataGrail puts the h-captcha-response token before privacy_right_id.

    The judge truncates the body at 6000 characters. A 4000-character token
    still leaves the request type and policy id visible; past roughly 5000 they
    fall off the end. Pinned so a lower cap would be caught here.
    """
    _, task = DATAGRAIL[0]
    body = _dg_body(task)
    body = {
        "location": body["location"],
        "h-captcha-response": "P1_" + "x" * 4000,
        "answers": body["answers"],
        "privacy_right_id": body["privacy_right_id"],
        "privacy_request_policy_id": body["privacy_request_policy_id"],
    }
    msg = _build_user_msg(
        task["instruction"], {"request": {"url": "u", "method": "POST", "body": body}}
    )
    assert body["privacy_right_id"] in msg
    assert body["privacy_request_policy_id"] in msg


def test_readme_lists_every_task() -> None:
    readme = (SUITE / "README.md").read_text(encoding="utf-8")
    for name, _ in TASKS:
        assert f"`{name}`" in readme
