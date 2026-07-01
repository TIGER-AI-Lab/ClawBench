"""Tests for the CLAWBENCH-LITE selector (scripts/select_lite.py).

Determinism and axis-coverage are the properties a released benchmark subset
must guarantee, so we assert them directly against the real v2 task pool
(130 tiny JSON files -> fast). Pure-logic helpers are unit-tested in isolation.
"""

from __future__ import annotations

import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT / "scripts"))

import select_lite as sl  # noqa: E402


def test_reach_band_boundaries() -> None:
    assert sl._reach_band(0.0) == "unreached"
    assert sl._reach_band(0.1) == "hard"
    assert sl._reach_band(1 / 3) == "hard"
    assert sl._reach_band(0.5) == "mixed"
    assert sl._reach_band(2 / 3) == "mixed"
    assert sl._reach_band(0.9) == "reachable"


def test_provisional_exec_mode() -> None:
    assert sl._provisional_exec_mode("Please register a new account") == "reset-required"
    assert sl._provisional_exec_mode("complete the payment at checkout") == "offline-only"
    assert sl._provisional_exec_mode("add three books to a shelf") == "repeatable-online"


def test_selection_is_deterministic() -> None:
    feats = sl.load_features()
    a = [f.task_dir for f in sl.select_lite(feats)]
    b = [f.task_dir for f in sl.select_lite(feats)]
    assert a == b
    assert len(a) == len(set(a)), "no duplicate tasks in LITE"


def test_one_representative_per_scenario_class() -> None:
    feats = sl.load_features()
    lite = sl.select_lite(feats)
    full_classes = {f.metaclass for f in feats}
    lite_classes = {f.metaclass for f in lite}
    assert lite_classes == full_classes
    assert len(lite) == len(full_classes) == sl.LITE_TARGET


def test_all_outcome_methods_and_graphql_covered() -> None:
    feats = sl.load_features()
    lite = sl.select_lite(feats)
    methods = {f.method for f in lite}
    assert {"POST", "GET", "PUT"} <= methods, f"missing method(s): {methods}"
    assert any(f.is_graphql for f in lite), "no GraphQL-constraint task selected"


def test_failure_regimes_are_represented() -> None:
    feats = sl.load_features()
    lite = sl.select_lite(feats)
    bands = {f.reach_band for f in lite}
    # The pilot has no fully-reachable tasks; LITE must still span the hard end.
    assert {"unreached", "hard", "mixed"} <= bands, f"thin regime coverage: {bands}"


def test_manifest_check_passes() -> None:
    # The packaged --check gate must succeed on the current pool.
    assert sl.main(["--check"]) == 0
