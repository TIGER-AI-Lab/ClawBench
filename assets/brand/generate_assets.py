"""Generate monochrome logos, a small icon, and a social card from the SVG identity."""

from __future__ import annotations

import argparse
import copy
import hashlib
import json
import re
import tempfile
from pathlib import Path
from xml.etree import ElementTree as ET

ASSETS = Path(__file__).resolve().parent.parent
NS = "http://www.w3.org/2000/svg"
ET.register_namespace("", NS)


def mono(source: str, color: str) -> str:
    source = re.sub(r'fill="#[0-9A-Fa-f]{6}"', f'fill="{color}"', source)
    return source.replace("A coral paw", "A monochrome paw").replace(
        "A coral", "A monochrome"
    )


def vector_assets() -> dict[str, str]:
    logo = (ASSETS / "clawbench-logo.svg").read_text(encoding="utf-8")
    mark = (ASSETS / "clawbench-mark.svg").read_text(encoding="utf-8")
    icon = """<svg xmlns="http://www.w3.org/2000/svg" width="32" height="32" viewBox="0 0 32 32" role="img" aria-labelledby="title">
  <title id="title">ClawBench</title>
  <rect width="32" height="32" rx="7" fill="#EB6449"/>
  <g fill="#fff">
    <ellipse cx="7.7" cy="10.2" rx="2.2" ry="3.1" transform="rotate(-25 7.7 10.2)"/>
    <ellipse cx="13.1" cy="6.9" rx="2.4" ry="3.3" transform="rotate(-10 13.1 6.9)"/>
    <ellipse cx="18.9" cy="6.9" rx="2.4" ry="3.3" transform="rotate(10 18.9 6.9)"/>
    <ellipse cx="24.3" cy="10.2" rx="2.2" ry="3.1" transform="rotate(25 24.3 10.2)"/>
    <path fill-rule="evenodd" d="M11.5 13.3C13 11.2 14 11 16 11s3 .2 4.5 2.3c1.1 1.6 1.7 2.6 3.1 4 2.1 2.2 1.8 4.7-.2 5.7-2.2 1.1-4.1-.8-7.4-.8S10.8 24.1 8.6 23c-2-1-2.3-3.5-.2-5.7 1.4-1.4 2-2.4 3.1-4Zm2.5 1.1v6.1l1.9-1.8 1.5 3.1 1.6-.8-1.6-3.1H20Z"/>
    <path d="M7.5 25h17a1 1 0 0 1 0 2H22l1.1 2a1 1 0 0 1-1.8.9L19.7 27h-7.4l-1.6 2.9a1 1 0 0 1-1.8-.9l1.1-2H7.5a1 1 0 0 1 0-2Z"/>
  </g>
</svg>
"""
    card = ET.Element(
        f"{{{NS}}}svg",
        {
            "width": "1200",
            "height": "630",
            "viewBox": "0 0 1200 630",
            "role": "img",
            "aria-labelledby": "title description",
            "font-family": "Arial, Helvetica, sans-serif",
        },
    )
    ET.SubElement(
        card, f"{{{NS}}}title", id="title"
    ).text = "ClawBench — real-world browser agent benchmark"
    ET.SubElement(
        card, f"{{{NS}}}desc", id="description"
    ).text = "Can AI agents complete everyday online tasks? Real websites, full execution traces, and two-stage scoring. claw-bench.com."
    ET.SubElement(card, f"{{{NS}}}rect", width="1200", height="630", fill="#F7F5F0")
    ET.SubElement(
        card, f"{{{NS}}}rect", x="0", y="0", width="1200", height="9", fill="#EB6449"
    )

    def lettering(
        value: str,
        x: int,
        y: int,
        size: int,
        weight: int,
        color: str,
        **attributes: str,
    ) -> None:
        attributes.update(
            {
                "x": str(x),
                "y": str(y),
                "font-size": str(size),
                "font-weight": str(weight),
                "fill": color,
            }
        )
        ET.SubElement(card, f"{{{NS}}}text", attributes).text = value

    lettering(
        "OPEN-SOURCE  /  LIVE-WEBSITE AGENT EVALUATION",
        80,
        55,
        13,
        600,
        "#646B74",
        **{"letter-spacing": "1.8"},
    )
    lockup = ET.SubElement(card, f"{{{NS}}}g", transform="translate(59 74) scale(.73)")
    for child in ET.fromstring(logo):
        if child.tag == f"{{{NS}}}g":
            lockup.append(copy.deepcopy(child))
    ghost = ET.SubElement(
        card, f"{{{NS}}}g", transform="translate(929 208) scale(.72)", opacity=".12"
    )
    for child in ET.fromstring(mark):
        if child.tag == f"{{{NS}}}g":
            ghost.append(copy.deepcopy(child))
    lettering(
        "Can AI agents complete",
        80,
        306,
        58,
        700,
        "#20242C",
        **{"letter-spacing": "-1.5"},
    )
    lettering(
        "everyday online tasks?",
        80,
        376,
        58,
        700,
        "#20242C",
        **{"letter-spacing": "-1.5"},
    )
    lettering("REAL TASKS", 80, 456, 14, 700, "#B84A34", **{"letter-spacing": "1.5"})
    lettering(
        "FULL EXECUTION TRACES",
        355,
        456,
        14,
        700,
        "#B84A34",
        **{"letter-spacing": "1.5"},
    )
    lettering(
        "TWO-STAGE SCORING", 782, 456, 14, 700, "#B84A34", **{"letter-spacing": "1.5"}
    )
    ET.SubElement(card, f"{{{NS}}}path", d="M80 508h1040", stroke="#D4D8DD")
    lettering("claw-bench.com", 80, 567, 22, 700, "#20242C")
    lettering("NAIL Group", 1120, 567, 16, 500, "#646B74", **{"text-anchor": "end"})
    ET.indent(card, space="  ")
    return {
        "clawbench-logo-mono.svg": mono(logo, "#111111"),
        "clawbench-logo-white.svg": mono(logo, "#FFFFFF"),
        "clawbench-mark-mono.svg": mono(mark, "#111111"),
        "clawbench-mark-white.svg": mono(mark, "#FFFFFF"),
        "favicon.svg": icon,
        "social-card.svg": ET.tostring(card, encoding="unicode") + "\n",
    }


def render(browser_executable: str | None) -> None:
    from PIL import Image
    from playwright.sync_api import sync_playwright

    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(executable_path=browser_executable)
        page = browser.new_page(
            viewport={"width": 1200, "height": 630}, device_scale_factor=1
        )
        page.goto((ASSETS / "social-card.svg").as_uri())
        page.screenshot(path=str(ASSETS / "social-card.png"))
        with tempfile.TemporaryDirectory(prefix="clawbench-brand-") as tmp:
            page.set_viewport_size({"width": 64, "height": 64})
            html = Path(tmp) / "icon.html"
            html.write_text(
                f'<style>body{{margin:0}}img{{display:block}}</style><img src="{(ASSETS / "favicon.svg").as_uri()}" width="64" height="64">'
            )
            page.goto(html.as_uri())
            page.locator("img").evaluate("async img => {await img.decode()}")
            page.screenshot(path=str(Path(tmp) / "icon.png"), omit_background=True)
            with Image.open(Path(tmp) / "icon.png") as icon:
                for size in (16, 32):
                    icon.resize((size, size), Image.Resampling.LANCZOS).save(
                        ASSETS / f"favicon-{size}.png"
                    )
                icon.save(
                    ASSETS / "favicon.ico",
                    sizes=[(16, 16), (32, 32), (48, 48), (64, 64)],
                )
        browser.close()
    sources = {}
    for raster, vector in {
        "social-card.png": "social-card.svg",
        "favicon-16.png": "favicon.svg",
        "favicon-32.png": "favicon.svg",
        "favicon.ico": "favicon.svg",
    }.items():
        sources[raster] = {
            "source": vector,
            "source_sha256": hashlib.sha256((ASSETS / vector).read_bytes()).hexdigest(),
            "sha256": hashlib.sha256((ASSETS / raster).read_bytes()).hexdigest(),
        }
    (ASSETS / "brand/raster-sources.json").write_text(
        json.dumps(sources, indent=2) + "\n", encoding="utf-8"
    )


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", action="store_true")
    parser.add_argument(
        "--render",
        action="store_true",
        help="Export PNG/ICO files; requires Playwright and Pillow.",
    )
    parser.add_argument("--browser-executable")
    args = parser.parse_args()
    assets = vector_assets()
    if args.check:
        stale = [
            name
            for name, content in assets.items()
            if not (ASSETS / name).exists()
            or (ASSETS / name).read_text(encoding="utf-8") != content
        ]
        for name, record in json.loads(
            (ASSETS / "brand/raster-sources.json").read_text(encoding="utf-8")
        ).items():
            if (
                hashlib.sha256((ASSETS / record["source"]).read_bytes()).hexdigest()
                != record["source_sha256"]
                or hashlib.sha256((ASSETS / name).read_bytes()).hexdigest()
                != record["sha256"]
            ):
                stale.append(name)
        if stale:
            print("Regenerate brand assets: " + ", ".join(stale))
            return 1
        print("Brand SVGs and raster source hashes are current.")
        return 0
    for name, content in assets.items():
        (ASSETS / name).write_text(content, encoding="utf-8")
    if args.render:
        render(args.browser_executable)
    print("Generated brand assets.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
