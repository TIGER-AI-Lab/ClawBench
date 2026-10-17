"""Offline checks for the shipping-quotes task suite.

Every task's eval_schema is checked against the real request its carrier sent
when the task was run in the ClawBench runtime (tests/fixtures/
shipping_quotes_live_captures.json), against variants a correct agent could
reasonably produce, and against near misses that must not count: the wrong
shape or unit, an intermediate wizard step, a different destination, or a
page-load request to the same endpoint.
"""

from __future__ import annotations

import copy
import json
from pathlib import Path

import pytest
from jsonschema import Draft202012Validator

from clawbench.eval.edgebench_judge import _stage1_match
from clawbench.runner.run_support.task import validate_task_data
from clawbench.utils.paths import asset_path

SUITE = asset_path("test-cases", "shipping-quotes")
CAPTURES = json.loads(
    (
        Path(__file__).parent / "fixtures" / "shipping_quotes_live_captures.json"
    ).read_text(encoding="utf-8")
)


def _load() -> dict[str, dict]:
    if not SUITE.is_dir():
        pytest.skip("shipping-quotes suite not bundled")
    return {
        p.parent.name: json.loads(p.read_text(encoding="utf-8"))
        for p in sorted(SUITE.glob("*/task.json"))
    }


TASKS = _load()
NAMES = sorted(TASKS)


def match(name: str, url: str, method: str = "GET", body: object = None) -> bool:
    return _stage1_match(
        {"url": url, "method": method, "body": body}, TASKS[name]["eval_schema"]
    )


def captured(name: str) -> dict:
    return copy.deepcopy(CAPTURES[name]["request"])


def swap(url: str, old: str, new: str) -> str:
    assert old in url, (old, url)
    return url.replace(old, new, 1)


# --------------------------------------------------------------------------
# Shape
# --------------------------------------------------------------------------


def test_suite_has_twelve_tasks_across_four_carriers() -> None:
    assert len(TASKS) == 12
    carriers = {t["metadata"]["carrier"] for t in TASKS.values()}
    assert carriers == {"USPS", "Canada Post", "UPS", "Purolator"}
    ids = [t["metadata"]["task_id"] for t in TASKS.values()]
    assert len(set(ids)) == 12 and all(630001 <= i <= 630012 for i in ids)


@pytest.mark.parametrize("name", NAMES)
def test_task_validates_against_schema_and_runner(name: str) -> None:
    task = TASKS[name]
    schema = json.loads(
        asset_path("test-cases", "task.schema.json").read_text(encoding="utf-8")
    )
    assert list(Draft202012Validator(schema).iter_errors(task)) == []
    assert validate_task_data(task, Path(name) / "task.json") is task
    assert task["instruction"].startswith("Open https://")


def test_every_task_has_a_live_capture() -> None:
    assert set(CAPTURES) == set(TASKS)
    assert all(c["intercepted"] is True for c in CAPTURES.values())


# --------------------------------------------------------------------------
# The real request each carrier sent is accepted
# --------------------------------------------------------------------------


@pytest.mark.parametrize("name", NAMES)
def test_live_capture_matches(name: str) -> None:
    req = captured(name)
    assert match(name, req["url"], req["method"], req["body"])


@pytest.mark.parametrize("name", NAMES)
def test_live_capture_matches_no_other_task(name: str) -> None:
    """Each task's schema singles out its own request, not a sibling's."""
    req = captured(name)
    for other in NAMES:
        if other != name:
            assert not match(other, req["url"], req["method"], req["body"]), other


@pytest.mark.parametrize("name", NAMES)
def test_wrong_method_is_rejected(name: str) -> None:
    req = captured(name)
    wrong = "POST" if req["method"] == "GET" else "GET"
    assert not match(name, req["url"], wrong, req["body"])


# --------------------------------------------------------------------------
# USPS: GET /Calculator/MailServices with every input in the query
# --------------------------------------------------------------------------


def test_usps_accepts_equivalent_number_formats_and_order() -> None:
    url = captured("usps_domestic_package_pounds_ounces")["url"]
    assert match(
        "usps_domestic_package_pounds_ounces", swap(url, "&p=3&o=4", "&p=3.0&o=4.00")
    )
    reordered = swap(
        url, "?country=0&ccode=US&oz=98101", "?oz=98101&country=0&ccode=US"
    )
    assert match("usps_domestic_package_pounds_ounces", reordered)


def test_usps_rejects_intermediate_steps_and_wrong_inputs() -> None:
    name = "usps_domestic_package_pounds_ounces"
    url = captured(name)["url"]
    for bad in (
        swap(url, "/MailServices?", "/ShapeAndSize?"),  # the step before prices
        swap(url, "&m=6", "&m=7"),  # Large Package instead of Package
        swap(url, "&m=6", "&m=1"),  # Letter
        swap(url, "&o=4", "&o=40"),  # 3 lb 40 oz
        swap(url, "&p=3", "&p=4"),
        swap(url, "dz=10001", "dz=10002"),
        swap(url, "oz=98101", "oz=98109"),
        url + "&p=4",  # a duplicated parameter
    ):
        assert not match(name, bad), bad


def test_usps_large_package_needs_dimensions_and_accepts_width_height_swap() -> None:
    name = "usps_large_package_with_dimensions"
    url = captured(name)["url"]
    assert match(name, swap(url, "&h=12&w=16", "&h=16&w=12"))
    assert match(name, swap(url, "&o=0", "&o="))  # ounces left blank
    for bad in (
        swap(url, "&l=24", "&l=16"),
        swap(url, "&h=12&w=16", "&h=12&w=12"),
        swap(url, "&rect=True", "&rect=False"),
        swap(url, "&m=7", "&m=6"),  # regular Package ignores the size rule
        swap(url, "/MailServices?", "/LargePackageProperties?"),
    ):
        assert not match(name, bad), bad


def test_usps_kilogram_task_accepts_metric_entry_and_sensible_conversions() -> None:
    name = "usps_package_weight_in_kilograms"
    url = captured(name)["url"]
    assert "&p=5&o=8.18" in url  # the calculator's own metric conversion
    for ok in ("&p=5&o=8", "&p=5&o=8.2", "&p=5&o=8.19", "&p=0&o=88.18", "&p=&o=88"):
        assert match(name, swap(url, "&p=5&o=8.185599999999994", ok)), ok
    for bad in (
        "&p=2&o=8",  # 2.5 read as pounds
        "&p=2&o=0",
        "&p=5&o=0",  # ounces dropped
        "&p=1&o=40",
        "&p=0&o=2.5",
    ):
        assert not match(name, swap(url, "&p=5&o=8.185599999999994", bad)), bad


def test_usps_square_envelope_requires_the_nonmachinable_flag() -> None:
    name = "usps_square_envelope_letter"
    url = captured(name)["url"]
    assert not match(name, swap(url, "&ct4=True", ""))  # an ordinary machinable letter
    assert not match(name, swap(url, "&ct4=True", "&ct3=True"))
    assert not match(name, swap(url, "&m=1", "&m=2"))  # large envelope
    assert not match(name, swap(url, "/MailServices?", "/LetterProperties?"))


# --------------------------------------------------------------------------
# Canada Post: GET /find-a-rate/price (and /lm/price for letters)
# --------------------------------------------------------------------------


def test_canada_post_metric_parcel_rejects_wrong_units_and_destinations() -> None:
    name = "canada_post_domestic_parcel_metric"
    url = captured(name)["url"]
    assert match(name, swap(url, "weight=3200", "weight=3200.0"))
    for bad in (
        swap(url, "weight=3200", "weight=3.2"),  # kilograms passed as grams
        swap(url, "weight=3200", "weight=32000"),
        swap(url, "length=40.00", "length=4.00"),
        swap(url, "destnPostalCode=V6B1A1", "destnPostalCode=V6B1A2"),
        swap(url, "originPostalCode=M5S2H7", "originPostalCode=M5S2H8"),
        swap(url, "destnType=DOMESTIC", "destnType=AMERICAN"),
    ):
        assert not match(name, bad), bad


def test_canada_post_imperial_task_tolerates_rounding_but_not_unit_errors() -> None:
    name = "canada_post_parcel_to_us_imperial_units"
    url = captured(name)["url"]
    assert "weight=2041.165665" in url and "length=30.48" in url
    # A manual conversion that rounds to 2.04 kg / 30.5 cm still counts.
    rounded = swap(
        swap(url, "weight=2041.165665", "weight=2040"), "length=30.48", "length=30.50"
    )
    assert match(name, rounded)
    for bad in (
        swap(url, "weight=2041.165665", "weight=4500"),  # 4.5 entered as kg
        swap(url, "weight=2041.165665", "weight=4.5"),
        swap(url, "length=30.48", "length=12.00"),  # inches entered as cm
        swap(url, "height=20.32", "height=8.00"),
        swap(url, "destnZipCode=10001", "destnZipCode=10002"),
        swap(url, "destnType=AMERICAN", "destnType=DOMESTIC"),
    ):
        assert not match(name, bad), bad


def test_canada_post_international_needs_the_right_country() -> None:
    name = "canada_post_international_parcel_to_uk"
    url = captured(name)["url"]
    assert not match(name, swap(url, "destnCountryCode=GB", "destnCountryCode=IE"))
    assert not match(name, swap(url, "destnType=INTERNATIONAL", "destnType=AMERICAN"))
    assert not match(name, swap(url, "weight=1500", "weight=15000"))


def test_canada_post_letter_must_use_the_lettermail_endpoint() -> None:
    name = "canada_post_domestic_lettermail"
    url = captured(name)["url"]
    assert "/find-a-rate/lm/price?" in url
    parcel = swap(url, "/find-a-rate/lm/price?", "/find-a-rate/price?")
    assert not match(name, parcel)  # priced as a package instead of a letter
    assert not match(name, swap(url, "weight=80", "weight=800"))
    assert not match(
        name, swap(url, "depositPostalCode=M5S2H7", "depositPostalCode=M5S2H8")
    )


# --------------------------------------------------------------------------
# UPS: form POST to /ctc/results
# --------------------------------------------------------------------------


@pytest.mark.parametrize(
    "name,field,bad",
    [
        ("ups_toronto_to_new_york_package", "weight1", "16"),
        ("ups_toronto_to_new_york_package", "shipWeightUnit", "KGS"),
        ("ups_toronto_to_new_york_package", "destPostalCode", "10002"),
        ("ups_toronto_to_new_york_package", "currencyScalar", "8"),
        ("ups_toronto_to_new_york_package", "container", "01"),  # UPS Envelope
        ("ups_toronto_to_new_york_package", "length1", "10"),
        ("ups_domestic_canada_kilograms", "shipWeightUnit", "LBS"),
        ("ups_domestic_canada_kilograms", "weight1", "4.4"),
        ("ups_domestic_canada_kilograms", "destCountry", "US"),
    ],
)
def test_ups_rejects_wrong_package_details(name: str, field: str, bad: str) -> None:
    req = captured(name)
    req["body"][field] = bad
    assert not match(name, req["url"], req["method"], req["body"])


@pytest.mark.parametrize(
    "name", ["ups_toronto_to_new_york_package", "ups_domestic_canada_kilograms"]
)
def test_ups_first_step_post_to_the_same_url_does_not_count(name: str) -> None:
    """The address step also POSTs to /ctc/results, before any weight exists."""
    req = captured(name)
    for field in ("weight1", "shipWeightUnit", "length1", "width1", "height1"):
        req["body"].pop(field, None)
    assert not match(name, req["url"], req["method"], req["body"])


# --------------------------------------------------------------------------
# Purolator: JSON POST to /estimate/api/estimate
# --------------------------------------------------------------------------

PUROLATOR_WARMUP = {
    "language": "en",
    "requestReference": "warmup-call",
    "lineOfBusiness": "Courier",
    "sourceName": "PMA",
    "shipmentDate": "2026-10-17",
    "senderInformation": {
        "city": "Toronto",
        "provinceCode": "ON",
        "postalCode": "M9V3Y1",
        "countryCode": "CA",
    },
    "receiverInformation": {
        "city": "Toronto",
        "provinceStateCode": "ON",
        "postalZipCode": "M9V3Y1",
        "countryCode": "CA",
    },
    "shipmentInformation": {
        "packageType": "3",
        "unitOfMeasurement": "Imperial",
        "totalWeight": 1,
        "totalPackages": 1,
        "shipmentLevelOptions": [{"productCode": "RES"}],
        "packageInformation": [
            {
                "packageWeight": 1,
                "packageLength": 0,
                "packageWidth": 0,
                "packageHeight": 0,
            }
        ],
    },
}


@pytest.mark.parametrize(
    "name",
    [
        "purolator_toronto_to_montreal_pounds",
        "purolator_toronto_to_vancouver_kilograms",
    ],
)
def test_purolator_page_load_warmup_does_not_count(name: str) -> None:
    """The page fires this request to the same endpoint before the user acts."""
    url = captured(name)["url"]
    assert not match(name, url, "POST", PUROLATOR_WARMUP)


def test_purolator_shipment_date_does_not_matter() -> None:
    req = captured("purolator_toronto_to_montreal_pounds")
    req["body"]["shipmentDate"] = "2027-01-05"
    assert match(
        "purolator_toronto_to_montreal_pounds", req["url"], "POST", req["body"]
    )


def test_purolator_rejects_wrong_unit_weight_or_receiver() -> None:
    name = "purolator_toronto_to_vancouver_kilograms"
    base = captured(name)
    pounds = copy.deepcopy(base)
    pounds["body"]["shipmentInformation"]["unitOfMeasurement"] = (
        "Imperial"  # unit left at the default
    )
    heavier = copy.deepcopy(base)
    heavier["body"]["shipmentInformation"]["totalWeight"] = 4
    heavier["body"]["shipmentInformation"]["packageInformation"][0]["packageWeight"] = 4
    elsewhere = copy.deepcopy(base)
    elsewhere["body"]["receiverInformation"]["postalZipCode"] = "V6B1A2"
    for bad in (pounds, heavier, elsewhere):
        assert not match(name, bad["url"], "POST", bad["body"])
