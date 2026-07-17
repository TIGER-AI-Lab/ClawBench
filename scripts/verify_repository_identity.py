#!/usr/bin/env python3
"""Keep public repository links aligned with the canonical ClawBench home."""

from __future__ import annotations

import tomllib
from pathlib import Path


CANONICAL_REPOSITORY = "https://github.com/TIGER-AI-Lab/ClawBench"
LEGACY_SLUG = "reacher-z/ClawBench"
ROOT = Path(__file__).resolve().parents[1]
DOCUMENTS = (
    ROOT / "README.md",
    ROOT / "docs" / "README.zh-CN.md",
    ROOT / "CONTRIBUTING.md",
    ROOT / "CITATION.cff",
)


def require(condition: bool, message: str) -> None:
    if not condition:
        raise SystemExit(f"repository identity check failed: {message}")


def main() -> None:
    with (ROOT / "pyproject.toml").open("rb") as handle:
        project_urls = tomllib.load(handle)["project"]["urls"]

    require(
        project_urls.get("Repository") == CANONICAL_REPOSITORY,
        "project.urls.Repository must name the canonical repository",
    )
    require(
        project_urls.get("Issues") == f"{CANONICAL_REPOSITORY}/issues",
        "project.urls.Issues must name the canonical issue tracker",
    )

    citation = (ROOT / "CITATION.cff").read_text(encoding="utf-8")
    require(
        f'repository-code: "{CANONICAL_REPOSITORY}"' in citation,
        "CITATION.cff must name the canonical repository",
    )

    for document in DOCUMENTS:
        require(
            document.is_file(),
            f"missing tracked document: {document.relative_to(ROOT)}",
        )
        require(
            LEGACY_SLUG not in document.read_text(encoding="utf-8"),
            f"legacy repository link remains in {document.relative_to(ROOT)}",
        )

    print("Repository identity contract passed.")


if __name__ == "__main__":
    main()
