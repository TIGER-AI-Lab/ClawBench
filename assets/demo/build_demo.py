"""Build the README demo from a verified, published ClawBench recording.

Requires playwright and imageio-ffmpeg. Source files stay outside the repository.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
import tempfile
from pathlib import Path

import imageio_ffmpeg
from playwright.sync_api import sync_playwright

HERE = Path(__file__).resolve().parent
ASSETS = HERE.parent


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source-dir", required=True, type=Path)
    parser.add_argument("--browser-executable")
    args = parser.parse_args()
    manifest = json.loads((HERE / "source.json").read_text(encoding="utf-8"))
    for name, checksum in manifest["files"].items():
        actual = hashlib.sha256((args.source_dir / name).read_bytes()).hexdigest()
        if actual != checksum:
            raise ValueError(f"Source checksum mismatch: {name}")
    interception = json.loads(
        (args.source_dir / "interception.json").read_text(encoding="utf-8")
    )
    judge = json.loads((args.source_dir / "judge.json").read_text(encoding="utf-8"))
    request = interception["request"]
    evidence = manifest["evidence"]
    assert interception["intercepted"] is evidence["intercepted"]
    assert request["method"] == evidence["method"]
    assert request["url"].split("?", 1)[0] == evidence["endpoint"]
    assert request["body"]["operationName"] == evidence["operation_name"]
    assert (
        request["body"]["variables"]["input"]["problemNumber"]
        == evidence["problem_number"]
    )
    assert judge["match"] is evidence["judge_match"]
    assert judge["judge_model"] == evidence["judge_model"]

    ffmpeg = imageio_ffmpeg.get_ffmpeg_exe()
    edit = manifest["edit"]
    fps = edit["fps"]
    with tempfile.TemporaryDirectory(prefix="clawbench-demo-") as scratch:
        scratch = Path(scratch)
        frames = scratch / "source"
        output = scratch / "frames"
        frames.mkdir()
        output.mkdir()
        x, y, w, h = edit["crop_xywh"]
        subprocess.run(
            [
                ffmpeg,
                "-y",
                "-hide_banner",
                "-loglevel",
                "error",
                "-ss",
                str(edit["start_seconds"]),
                "-i",
                str(args.source_dir / "recording.mp4"),
                "-t",
                str(
                    (edit["end_seconds"] - edit["start_seconds"])
                    / edit["playback_speed"]
                ),
                "-vf",
                f"crop={w}:{h}:{x}:{y},setpts=PTS/{edit['playback_speed']},fps={fps},scale=880:-2",
                str(frames / "%04d.png"),
            ],
            check=True,
        )
        html = (
            (HERE / "demo.html")
            .read_text(encoding="utf-8")
            .replace("LOGO_URL", (ASSETS / "clawbench-logo.svg").as_uri())
        )
        (scratch / "demo.html").write_text(html, encoding="utf-8")
        with sync_playwright() as playwright:
            browser = playwright.chromium.launch(
                executable_path=args.browser_executable
            )
            page = browser.new_page(
                viewport={"width": 960, "height": 684}, device_scale_factor=1
            )
            page.goto((scratch / "demo.html").as_uri())
            page.locator("#endpoint").inner_text()
            index = 0
            source_frames = sorted(frames.glob("*.png"))
            for frame in source_frames:
                page.evaluate(
                    "async url => {const img=document.querySelector('#recording');img.src=url;await img.decode();}",
                    frame.as_uri(),
                )
                page.screenshot(path=str(output / f"{index:04d}.png"))
                index += 1
            page.evaluate("document.body.dataset.phase='overview'")
            page.screenshot(path=str(HERE / "task-1122-poster.png"))
            for phase, seconds in [
                ("interception", edit["interception_panel_seconds"]),
                ("judge", edit["judge_panel_seconds"]),
            ]:
                page.evaluate("phase => document.body.dataset.phase=phase", phase)
                page.screenshot(path=str(scratch / f"{phase}.png"))
                content = (scratch / f"{phase}.png").read_bytes()
                for _ in range(round(seconds * fps)):
                    (output / f"{index:04d}.png").write_bytes(content)
                    index += 1
            browser.close()
        subprocess.run(
            [
                ffmpeg,
                "-y",
                "-hide_banner",
                "-loglevel",
                "error",
                "-framerate",
                str(fps),
                "-i",
                str(output / "%04d.png"),
                "-vf",
                "split[s0][s1];[s0]palettegen=max_colors=192:stats_mode=diff[p];[s1][p]paletteuse=dither=bayer:bayer_scale=3",
                "-loop",
                "0",
                str(HERE / "task-1122.gif"),
            ],
            check=True,
        )
        subprocess.run(
            [
                ffmpeg,
                "-y",
                "-hide_banner",
                "-loglevel",
                "error",
                "-framerate",
                str(fps),
                "-i",
                str(output / "%04d.png"),
                "-c:v",
                "libx264",
                "-crf",
                "20",
                "-pix_fmt",
                "yuv420p",
                "-movflags",
                "+faststart",
                str(HERE / "task-1122.mp4"),
            ],
            check=True,
        )
        print(
            f"Rendered {index} frames ({index / fps:.1f}s) from verified source files."
        )


if __name__ == "__main__":
    main()
