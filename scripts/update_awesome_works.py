#!/usr/bin/env python3
"""Scan Semantic Scholar for new papers citing ClawBench and emit candidates.

Weekly companion to the "Awesome Works using ClawBench" README section.
Fetches every paper that cites arXiv:2604.08523 via the free Semantic Scholar
Graph API, drops anything already listed in the README or already reported in
a previous scan (--seen-file), and writes the remainder to --out as a
ready-to-review Markdown checklist. The GitHub Actions workflow opens an
issue from that file; a maintainer curates which entries actually land in the
README. This script never edits the README itself.

Exit code is always 0; an empty/absent --out file means "nothing new".
"""

from __future__ import annotations

import argparse
import json
import re
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

CLAWBENCH_PAPER_ID = "arXiv:2604.08523"
API = (
    "https://api.semanticscholar.org/graph/v1/paper/{pid}/citations"
    "?fields=title,externalIds,year,venue,authors&limit=100&offset={offset}"
)
ARXIV_ID_RE = re.compile(r"arxiv\.org/(?:abs|pdf)/(\d{4}\.\d{4,5})", re.I)


def fetch_citations(api_key: str | None) -> list[dict]:
    papers, offset = [], 0
    while True:
        req = urllib.request.Request(API.format(pid=CLAWBENCH_PAPER_ID, offset=offset))
        req.add_header("User-Agent", "clawbench-awesome-works-scan")
        if api_key:
            req.add_header("x-api-key", api_key)
        try:
            with urllib.request.urlopen(req, timeout=30) as resp:
                page = json.load(resp)
        except urllib.error.HTTPError as e:
            if e.code == 429:  # rate limited: back off once, then give up quietly
                time.sleep(30)
                continue
            print(
                f"warning: S2 API HTTP {e.code}, stopping at offset {offset}",
                file=sys.stderr,
            )
            break
        batch = [
            row["citingPaper"] for row in page.get("data", []) if row.get("citingPaper")
        ]
        papers.extend(batch)
        if "next" not in page or not batch:
            break
        offset = page["next"]
    return papers


def normalize(title: str) -> str:
    return re.sub(r"[^a-z0-9]+", "", title.lower())


def known_keys(readme: str, seen: str) -> tuple[set[str], set[str]]:
    """arXiv IDs and normalized titles already in the README or prior issues."""
    corpus = readme + "\n" + seen
    ids = set(ARXIV_ID_RE.findall(corpus))
    titles = {
        normalize(m) for m in re.findall(r"\[([^\]]+)\]\(", corpus) if len(m) > 20
    }
    return ids, titles


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--readme", default="README.md")
    ap.add_argument("--out", default="candidates.md")
    ap.add_argument(
        "--seen-file", default=None, help="text dump of previous scan issues"
    )
    ap.add_argument(
        "--api-key", default=None, help="optional S2_API_KEY for higher rate limits"
    )
    args = ap.parse_args()

    readme = Path(args.readme).read_text(encoding="utf-8")
    seen = (
        Path(args.seen_file).read_text(encoding="utf-8")
        if args.seen_file and Path(args.seen_file).exists()
        else ""
    )
    known_ids, known_titles = known_keys(readme, seen)

    fresh = []
    for p in fetch_citations(args.api_key):
        ext = p.get("externalIds") or {}
        arxiv_id = ext.get("ArXiv")
        title = p.get("title") or ""
        if not title:
            continue
        if arxiv_id and arxiv_id in known_ids:
            continue
        if normalize(title) in known_titles:
            continue
        fresh.append((p, arxiv_id))

    if not fresh:
        print("no new citing papers")
        return 0

    lines = [
        "New papers citing ClawBench were found by the weekly Semantic Scholar scan.",
        "Please review and add curated entries to the *Awesome Works using ClawBench*",
        "section of README.md (apply the maintainers' inclusion criteria before adding).",
        "",
        "S2 misses some works Google Scholar catches (ResearchGate/OSF/OpenReview items,",
        "and slow-linked arXiv refs) — worth an occasional manual [Scholar cited-by check]"
        "(https://scholar.google.com/scholar?q=ClawBench) alongside this list.",
        "",
        "cc @Perry2004",
        "",
    ]
    for p, arxiv_id in fresh:
        authors = ", ".join(a.get("name", "?") for a in (p.get("authors") or [])[:3])
        more = " et al." if len(p.get("authors") or []) > 3 else ""
        link = (
            f"https://arxiv.org/abs/{arxiv_id}"
            if arxiv_id
            else f"https://www.semanticscholar.org/paper/{p.get('paperId', '')}"
        )
        venue = p.get("venue") or "arXiv"
        lines.append(
            f"- [ ] [{p['title']}]({link}) — {authors}{more} ({venue} {p.get('year', '?')})"
        )
    Path(args.out).write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(f"{len(fresh)} candidate(s) written to {args.out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
