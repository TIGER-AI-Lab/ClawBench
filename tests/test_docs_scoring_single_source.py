"""The scoring spec has one home, carrying the repo's own URLs.

docs/scoring.md and eval/scoring.md were full copies of each other and had
drifted apart on four links, with neither copy right on all of them: the docs/
copy sent the "HF data card table" link at a Space instead of a dataset and
carried a V1 trace link whose label named a different org than its URL, while
the eval/ copy pointed at the superseded leaderboard Space and at V2 traces
under the wrong org. Whichever copy a reader landed on decided which numbers
they tried to reproduce.

eval/scoring.md is canonical -- it sits beside eval/rescore.py, and README.md,
docs/README.zh-CN.md, and docs/harbor.md all already linked to it. Removing a
copy means choosing values as well as a filename, so the link tests below pin
the survivor to what README.md and docs/news.md record.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
CANONICAL = REPO_ROOT / "eval" / "scoring.md"
POINTER = REPO_ROOT / "docs" / "scoring.md"


def test_the_canonical_scoring_doc_exists() -> None:
    assert CANONICAL.is_file()


def test_the_docs_copy_is_a_pointer_not_a_second_spec() -> None:
    pointer = POINTER.read_text(encoding="utf-8")

    assert "../eval/scoring.md" in pointer
    # A stub, not a rival copy. The spec is ~190 lines; this guards the whole
    # document being pasted back in.
    assert len(pointer.splitlines()) < 30


@pytest.mark.parametrize(
    "spec_marker",
    [
        "## Stage 1 — Final-request interception",
        "## Stage 2 — LLM judge",
        "## Reproducibility",
    ],
)
def test_each_spec_section_lives_in_exactly_one_file(spec_marker: str) -> None:
    """The drift happened because both files carried the full spec."""
    assert spec_marker in CANONICAL.read_text(encoding="utf-8")
    assert spec_marker not in POINTER.read_text(encoding="utf-8")


def test_nothing_still_points_at_the_old_copy_as_the_spec() -> None:
    """Internal references should reach the canonical file directly."""
    for md in [
        REPO_ROOT / "docs" / "v1-vs-v2.md",
        REPO_ROOT / "docs" / "news.md",
        REPO_ROOT / "README.md",
    ]:
        text = md.read_text(encoding="utf-8")
        assert "docs/scoring.md" not in text, md.name
        assert "](scoring.md)" not in text, md.name


def test_the_pointers_relative_links_resolve() -> None:
    """A stub whose links 404 is worse than the duplicate it replaced."""
    text = POINTER.read_text(encoding="utf-8")
    targets = re.findall(r"\]\((\.\./[^)#]+)(?:#[^)]*)?\)", text)

    assert targets, "the pointer must link to the canonical document"
    for target in targets:
        assert (POINTER.parent / target).resolve().is_file(), target


def test_the_canonical_doc_anchors_the_pointer_links_exist() -> None:
    """Guard the two anchors the pointer deep-links to."""
    headings = CANONICAL.read_text(encoding="utf-8").splitlines()
    slugs = {
        line.lstrip("#").strip().lower().replace(" ", "-")
        for line in headings
        if line.startswith("#")
    }

    assert "summary" in slugs
    assert "reproducibility" in slugs


# What README.md and docs/news.md record. Deduping toward either copy verbatim
# would have shipped two of these wrong, which is how #293 started.
CANONICAL_URLS = {
    "live leaderboard": "https://huggingface.co/spaces/TIGER-Lab/ClawBench",
    "dataset card": "https://huggingface.co/datasets/NAIL-Group/ClawBench",
    "V1 traces": "https://huggingface.co/datasets/NAIL-Group/ClawBenchV1Trace",
    "V2 traces": "https://huggingface.co/datasets/TIGER-Lab/ClawBenchV2Trace",
}


def _mentions(text: str, url: str) -> bool:
    """Match a whole URL: .../ClawBench must not be satisfied by ClawBenchV1Trace."""
    return re.search(re.escape(url) + r"(?![A-Za-z0-9])", text) is not None


@pytest.mark.parametrize("what, url", sorted(CANONICAL_URLS.items()))
def test_the_canonical_doc_agrees_with_the_readme(what: str, url: str) -> None:
    """The spec and the README must send a reader to the same place."""
    assert _mentions(CANONICAL.read_text(encoding="utf-8"), url), what
    assert _mentions((REPO_ROOT / "README.md").read_text(encoding="utf-8"), url), what


def test_the_superseded_leaderboard_space_is_gone() -> None:
    """docs/news.md records the move to the TIGER-Lab Space; the old NAIL-Group
    mirror must not be what the scoring spec advertises as live."""
    assert "spaces/NAIL-Group/clawbench-leaderboard" not in CANONICAL.read_text(
        encoding="utf-8"
    )
