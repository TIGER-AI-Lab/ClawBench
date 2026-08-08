"""Tests for clawbench.utils.update_llms documentation generator script."""

from pathlib import Path
from unittest.mock import MagicMock, patch
import pytest

from clawbench.utils.paths import WORKSPACE_ROOT
from clawbench.utils.update_llms import (
    fetch_leaderboard_data,
    fetch_sitemap_urls,
    generate_llms_txt_content,
    get_canonical_resources_section,
    get_interactive_pages_section,
    get_leaderboard_section,
    get_quick_facts_section,
    main,
    parse_citation_bibtex,
    url_to_title,
)


def test_parse_citation_bibtex_default() -> None:
    """Verify parse_citation_bibtex parses repo CITATION.cff or returns formatted BibTeX."""
    bibtex = parse_citation_bibtex()
    assert "@article{zhang2026clawbench" in bibtex
    assert "author=" in bibtex
    assert "title=" in bibtex


def test_parse_citation_bibtex_custom(tmp_path: Path) -> None:
    """Verify parse_citation_bibtex with a custom CFF file and missing file handling."""
    cff_file = tmp_path / "CITATION.cff"
    cff_file.write_text(
        """cff-version: 1.2.0
title: "Custom ClawBench Title"
authors:
  - family-names: "Doe"
    given-names: "Jane"
year: 2026
journal: "arXiv"
""",
        encoding="utf-8",
    )

    bibtex = parse_citation_bibtex(cff_file)
    assert "@article{zhang2026clawbench" in bibtex
    assert "Custom ClawBench Title" in bibtex
    assert "Doe, Jane" in bibtex
    assert "year={2026}" in bibtex

    missing_cff = tmp_path / "non_existent.cff"
    assert parse_citation_bibtex(missing_cff) == ""


def test_url_to_title() -> None:
    """Verify human-readable titles generated from URLs."""
    assert url_to_title("https://claw-bench.com/") == "Project Home"
    assert url_to_title("https://claw-bench.com") == "Project Home"
    assert url_to_title("https://claw-bench.com/leaderboard") == "Leaderboard"
    assert url_to_title("https://claw-bench.com/tasks") == "Task Detail"
    assert url_to_title("https://claw-bench.com/user_guide") == "User Guide"


def test_fetch_sitemap_urls_fallback_and_mock() -> None:
    """Verify sitemap fetching fallback on network error and XML parsing on success."""
    # Test network failure fallback
    with patch("urllib.request.urlopen", side_effect=Exception("Network Error")):
        urls = fetch_sitemap_urls()
        assert isinstance(urls, list)
        assert len(urls) > 0
        assert "https://claw-bench.com/leaderboard" in urls

    # Test XML parsing
    xml_content = (
        '<?xml version="1.0" encoding="UTF-8"?>'
        '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">'
        "<url><loc>https://claw-bench.com/custom-page</loc></url>"
        "</urlset>"
    ).encode("utf-8")

    mock_resp = MagicMock()
    mock_resp.read.return_value = xml_content
    mock_resp.__enter__.return_value = mock_resp

    with patch("urllib.request.urlopen", return_value=mock_resp):
        urls = fetch_sitemap_urls("https://claw-bench.com/sitemap.xml")
        assert urls == ["https://claw-bench.com/custom-page"]


def test_fetch_leaderboard_data_fallback_and_mock() -> None:
    """Verify leaderboard fetching fallback on network error and JSON parsing on success."""
    with patch("urllib.request.urlopen", side_effect=Exception("Network Error")):
        data = fetch_leaderboard_data()
        assert data == {}

    mock_json = '{"rows_v1_hermes": [{"model": "m1", "reward": 0.5}]}'
    mock_resp = MagicMock()
    mock_resp.read.return_value = mock_json.encode("utf-8")
    mock_resp.__enter__.return_value = mock_resp

    with patch("urllib.request.urlopen", return_value=mock_resp):
        data = fetch_leaderboard_data()
        assert "rows_v1_hermes" in data
        assert data["rows_v1_hermes"][0]["model"] == "m1"


def test_get_canonical_resources_section() -> None:
    """Verify canonical resources section contains project links and all dataset targets."""
    section = get_canonical_resources_section()
    assert "## Canonical resources" in section
    assert "https://claw-bench.com" in section
    assert "https://github.com/reacher-z/ClawBench" in section
    assert "https://huggingface.co/datasets/NAIL-Group/ClawBench" in section
    assert "https://huggingface.co/datasets/NAIL-Group/ClawBenchV1Trace" in section
    assert "https://huggingface.co/datasets/TIGER-Lab/ClawBenchV2Trace" in section


def test_get_quick_facts_section() -> None:
    """Verify quick facts reports current V1 and V2 corpus counts and harnesses."""
    section = get_quick_facts_section()
    assert "V1: 153 tasks across 144 live websites" in section
    assert "V2: 130 tasks with six first-class agent harnesses" in section
    assert "OpenClaw" in section
    assert "Claude Code" in section
    assert "Hermes" in section


def test_get_leaderboard_section_formatting() -> None:
    """Verify leaderboard section generates formatted markdown tables for V1 and V2."""
    mock_data = {
        "rows_v1_hermes": [
            {"model": "model-a", "reward": 0.8, "matched": 122, "n": 153},
            {"model": "model-b", "reward": 0.7, "matched": 107, "n": 153},
        ],
        "rows_v2_hermes": [
            {"model": "model-x", "reward": 0.5, "int_rate": 0.6, "matched": 65, "n": 130},
        ],
    }

    with patch("clawbench.utils.update_llms.fetch_leaderboard_data", return_value=mock_data):
        section = get_leaderboard_section()

    assert "## Leaderboard" in section
    assert "### V1 Hermes (Top 5)" in section
    assert "| 1 | model-a | 80.0% | 122 / 153 |" in section
    assert "### V2 Hermes (Top 5)" in section
    assert "| 1 | model-x | 60.0% | 50.0% | 65 / 130 |" in section


def test_get_interactive_pages_section() -> None:
    """Verify interactive pages list is generated from sitemap URLs."""
    with patch("clawbench.utils.update_llms.fetch_sitemap_urls", return_value=["https://claw-bench.com/leaderboard"]):
        section = get_interactive_pages_section()
    assert "## Interactive pages" in section
    assert "- [Leaderboard](https://claw-bench.com/leaderboard)" in section


def test_generate_llms_txt_content() -> None:
    """Verify generate_llms_txt_content combines all section generators."""
    content = generate_llms_txt_content()
    assert "# ClawBench" in content
    assert "## Canonical resources" in content
    assert "## Leaderboard" in content
    assert "## Interactive pages" in content
    assert "## Quick facts" in content
    assert "## Citations" in content


def test_llms_txt_regression_check() -> None:
    """Regression test ensuring workspace llms.txt matches expected dynamically generated sections."""
    llms_path = WORKSPACE_ROOT / "llms.txt"
    assert llms_path.exists(), "llms.txt must exist at workspace root"
    file_content = llms_path.read_text(encoding="utf-8")

    # Core metadata regression checks
    assert "V1: 153 tasks across 144 live websites" in file_content
    assert "V2: 130 tasks" in file_content
    assert "https://huggingface.co/datasets/NAIL-Group/ClawBench" in file_content
    assert "https://huggingface.co/datasets/NAIL-Group/ClawBenchV1Trace" in file_content
    assert "https://huggingface.co/datasets/TIGER-Lab/ClawBenchV2Trace" in file_content
    assert "## Leaderboard" in file_content
    assert "### V1 Hermes (Top 5)" in file_content
    assert "### V2 Hermes (Top 5)" in file_content
    assert "@article{zhang2026clawbench" in file_content


def test_main_dry_run(capsys: pytest.CaptureFixture[str]) -> None:
    """Verify CLI main --dry-run prints generated content to stdout without changing files."""
    with patch("sys.argv", ["update_llms", "--dry-run"]):
        main()

    captured = capsys.readouterr()
    assert "# ClawBench" in captured.out
    assert "## Canonical resources" in captured.out


def test_main_output_file(tmp_path: Path) -> None:
    """Verify CLI main --output writes content to specified destination file."""
    output_file = tmp_path / "llms.txt"
    with patch("sys.argv", ["update_llms", "-o", str(output_file)]):
        main()

    assert output_file.exists()
    content = output_file.read_text(encoding="utf-8")
    assert "# ClawBench" in content
    assert "## Canonical resources" in content
