"""Script to modularly update llms.txt section by section."""

import argparse
import json
from pathlib import Path
from typing import Callable
import urllib.request
import xml.etree.ElementTree as ET
import yaml

from clawbench.utils.paths import ASSET_ROOT, WORKSPACE_ROOT


# ===========================================================================
# Helper Functions & Data Fetchers
# ===========================================================================

# ---------------------------------------------------------------------------
# Citation BibTeX Parser
# ---------------------------------------------------------------------------
def parse_citation_bibtex(cff_path: Path | None = None) -> str:
    """Parse CITATION.cff and format BibTeX string."""
    if cff_path is None:
        cff_path = (
            WORKSPACE_ROOT / "CITATION.cff"
            if (WORKSPACE_ROOT / "CITATION.cff").exists()
            else ASSET_ROOT / "CITATION.cff"
        )
    if not cff_path.exists():
        return ""

    with open(cff_path, "r", encoding="utf-8") as f:
        data = yaml.safe_load(f)

    pref = data.get("preferred-citation", {})
    authors_raw = pref.get("authors", data.get("authors", []))
    authors = [
        f"{a['family-names']}, {a['given-names']}"
        for a in authors_raw
        if "family-names" in a and "given-names" in a
    ]

    title = pref.get("title", data.get("title", ""))
    journal = pref.get("journal", "")
    year = pref.get("year", 2026)

    return (
        f"@article{{zhang2026clawbench,\n"
        f"  title={{{title}}},\n"
        f"  author={{{' and '.join(authors)}}},\n"
        f"  journal={{{journal}}},\n"
        f"  year={{{year}}}\n"
        f"}}"
    )


# ---------------------------------------------------------------------------
# Sitemap XML Fetcher
# ---------------------------------------------------------------------------
def fetch_sitemap_urls(sitemap_url: str = "https://claw-bench.com/sitemap.xml") -> list[str]:
    """Fetch and parse URLs from sitemap.xml with fallback default URLs."""
    fallback_urls = [
        "https://claw-bench.com/",
        "https://claw-bench.com/leaderboard",
        "https://claw-bench.com/tasks",
        "https://claw-bench.com/traces",
        "https://claw-bench.com/compare",
        "https://claw-bench.com/difficulty",
        "https://claw-bench.com/categories",
        "https://claw-bench.com/gallery",
        "https://claw-bench.com/contribute",
    ]
    try:
        req = urllib.request.Request(sitemap_url, headers={"User-Agent": "Mozilla/5.0"})
        with urllib.request.urlopen(req, timeout=5) as resp:
            content = resp.read().decode("utf-8")
        tree = ET.fromstring(content)
        urls = [elem.text.strip() for elem in tree.iter() if elem.tag.endswith("loc") and elem.text]
        return urls if urls else fallback_urls
    except Exception:
        return fallback_urls


# ---------------------------------------------------------------------------
# Leaderboard Data Fetcher
# ---------------------------------------------------------------------------
def fetch_leaderboard_data(leaderboard_url: str = "https://claw-bench.com/api/leaderboard.json") -> dict:
    """Fetch leaderboard data from API with fallback structure."""
    try:
        req = urllib.request.Request(leaderboard_url, headers={"User-Agent": "Mozilla/5.0"})
        with urllib.request.urlopen(req, timeout=5) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except Exception:
        return {}


# ---------------------------------------------------------------------------
# URL Title Extractor
# ---------------------------------------------------------------------------
def url_to_title(url: str) -> str:
    """Extract a human-readable title directly from a URL path."""
    path_part = url.rstrip("/").split("/")[-1]
    if not path_part or "claw-bench.com" in path_part:
        return "Project Home"
    title = path_part.replace("-", " ").replace("_", " ").title()
    return "Task Detail" if title == "Tasks" else title


# ===========================================================================
# Section Generators
# ===========================================================================

# ---------------------------------------------------------------------------
# Header Section Generator
# ---------------------------------------------------------------------------
def get_header_section() -> str:
    return """# ClawBench

> ClawBench is an open-source benchmark for evaluating browser and computer-use agents on everyday tasks performed on live websites.

ClawBench measures end-to-end task success while preserving replayable evidence from browser actions, screenshots, network requests, agent messages, and session recordings. The benchmark blocks only the final side-effecting submission request so tasks can run on real websites without completing purchases, bookings, or applications."""


# ---------------------------------------------------------------------------
# Canonical Resources Section Generator
# ---------------------------------------------------------------------------
def get_canonical_resources_section() -> str:
    return """## Canonical resources

- [Project page](https://claw-bench.com): overview, task explorer, leaderboard, and evaluation details.
- [GitHub repository](https://github.com/reacher-z/ClawBench): source code, task definitions, harnesses, and documentation.
- [Research paper](https://arxiv.org/abs/2604.08523): *ClawBench: Can AI Agents Complete Everyday Online Tasks?*
- [Citation metadata](https://github.com/reacher-z/ClawBench/blob/main/CITATION.cff): machine-readable citation record.
- [Task and leaderboard Space](https://huggingface.co/spaces/TIGER-Lab/ClawBench): live evaluation results and task explorer.
- [Task dataset](https://huggingface.co/datasets/NAIL-Group/ClawBench): V1/V2 task definitions and evaluation metadata.
- [V1 execution traces](https://huggingface.co/datasets/NAIL-Group/ClawBenchV1Trace): replayable run artifacts.
- [V2 execution traces](https://huggingface.co/datasets/TIGER-Lab/ClawBenchV2Trace): rolling V2 run artifacts."""


# ---------------------------------------------------------------------------
# Leaderboard Section Generator
# ---------------------------------------------------------------------------
def get_leaderboard_section() -> str:
    """Fetch live leaderboard scores and return formatted V1 Hermes and V2 Hermes top 5 sections."""
    data = fetch_leaderboard_data()
    v1_rows = data.get("rows_v1_hermes", [])
    v2_rows = data.get("rows_v2_hermes", [])

    if v1_rows:
        v1_top5 = sorted(v1_rows, key=lambda x: x.get("reward", 0), reverse=True)[:5]
    else:
        v1_top5 = [
            {"model": "claude-opus-4-6", "reward": 0.6144, "matched": 94, "n": 153},
            {"model": "claude-sonnet-4-6", "reward": 0.5686, "matched": 87, "n": 153},
            {"model": "claude-haiku-4-5-20251001", "reward": 0.3007, "matched": 46, "n": 153},
            {"model": "gpt-5.4-2026-03-05", "reward": 0.2549, "matched": 39, "n": 153},
            {"model": "gpt-5.4-mini-2026-03-17", "reward": 0.2484, "matched": 38, "n": 153},
        ]

    if v2_rows:
        v2_top5 = sorted(v2_rows, key=lambda x: x.get("reward", 0), reverse=True)[:5]
    else:
        v2_top5 = [
            {"model": "claude-opus-4-7", "reward": 0.4462, "int_rate": 0.5462, "matched": 58, "n": 130},
            {"model": "gpt-5.5", "reward": 0.3538, "int_rate": 0.4538, "matched": 46, "n": 130},
            {"model": "glm-5.1", "reward": 0.3462, "int_rate": 0.4846, "matched": 45, "n": 130},
            {"model": "deepseek-v4-pro", "reward": 0.3385, "int_rate": 0.4385, "matched": 44, "n": 130},
            {"model": "deepseek-v4-flash:free", "reward": 0.0233, "int_rate": 0.0310, "matched": 3, "n": 130},
        ]

    lines = [
        "## Leaderboard",
        "",
        "### V1 Hermes (Top 5)",
        "",
        "| Rank | Model | Pass Rate | Pass / Total |",
        "| :---: | :--- | :---: | :---: |",
    ]
    for i, r in enumerate(v1_top5, 1):
        model = r.get("model", "")
        reward = r.get("reward", 0) * 100
        matched = r.get("matched", 0)
        n = r.get("n", 153)
        lines.append(f"| {i} | {model} | {reward:.1f}% | {matched} / {n} |")

    lines.extend([
        "",
        "### V2 Hermes (Top 5)",
        "",
        "| Rank | Model | Intercepted | Reward (Lenient) | Pass / Total |",
        "| :---: | :--- | :---: | :---: | :---: |",
    ])
    for i, r in enumerate(v2_top5, 1):
        model = r.get("model", "")
        int_rate = r.get("int_rate", 0) * 100
        reward = r.get("reward", 0) * 100
        matched = r.get("matched", 0)
        n = r.get("n", 130)
        lines.append(f"| {i} | {model} | {int_rate:.1f}% | {reward:.1f}% | {matched} / {n} |")

    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Interactive Pages Section Generator
# ---------------------------------------------------------------------------
def get_interactive_pages_section() -> str:
    """Fetch sitemap.xml dynamically and extract links with dynamic titles."""
    urls = fetch_sitemap_urls()
    lines = ["## Interactive pages", ""]
    for url in urls:
        title = url_to_title(url)
        lines.append(f"- [{title}]({url})")

    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Quick Facts Section Generator
# ---------------------------------------------------------------------------
def get_quick_facts_section() -> str:
    return """## Quick facts

- V1: 153 tasks across 144 live websites and 15 life categories.
- V2: 130 tasks with six first-class agent harnesses.
- Evidence layers: session replay, screenshots, HTTP traffic, browser actions, and agent messages.
- Supported harnesses include OpenClaw, OpenCode, Claude Code, Codex, Browser-Use, Hermes, Pi, and other compatible browser agents."""


# ---------------------------------------------------------------------------
# Citations Section Generator
# ---------------------------------------------------------------------------
def get_citations_section() -> str:
    bibtex = parse_citation_bibtex()
    return f"""## Citations

```bibtex
{bibtex}
```"""


# ===========================================================================
# Section Registry & Assembly
# ===========================================================================

# Registry of section functions — add new section functions here
SECTIONS: list[Callable[[], str]] = [
    get_header_section,
    get_canonical_resources_section,
    get_leaderboard_section,
    get_interactive_pages_section,
    get_quick_facts_section,
    get_citations_section,
]


def generate_llms_txt_content() -> str:
    """Combine all registered section functions into the final llms.txt content."""
    return "\n\n".join(section().strip() for section in SECTIONS) + "\n"


# ===========================================================================
# CLI Main Entry Point
# ===========================================================================

def main() -> None:
    parser = argparse.ArgumentParser(description="Update llms.txt dynamically.")
    parser.add_argument("--output", "-o", type=Path, default=WORKSPACE_ROOT / "llms.txt")
    parser.add_argument("--dry-run", action="store_true", help="Print content to stdout.")
    args = parser.parse_args()

    content = generate_llms_txt_content()
    if args.dry_run:
        print(content)
        return

    args.output.write_text(content, encoding="utf-8")
    print(f"Successfully updated {args.output}")


if __name__ == "__main__":
    main()
