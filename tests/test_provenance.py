"""Run provenance: which code, corpus, and agent build produced a trace."""

from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

from clawbench.runner.run_support import provenance
from clawbench.utils.paths import ASSET_ROOT


@pytest.fixture(autouse=True)
def _clear_provenance_caches() -> None:
    for fn in (
        provenance.clawbench_version,
        provenance._repo_root,
        provenance.clawbench_commit,
        provenance._corpus_commit,
        provenance.harness_pins,
    ):
        fn.cache_clear()


@pytest.fixture
def built_image(monkeypatch: pytest.MonkeyPatch):
    """Mark a harness image as built from the Dockerfile in this checkout."""

    def mark(harness: str) -> None:
        monkeypatch.setenv(provenance.IMAGE_BUILT_ENV, harness)

    return mark


def _git_repo(path: Path) -> Path:
    """A real git repository — mocking `_git` is what hid the dirty-flag bug."""
    path.mkdir(parents=True, exist_ok=True)
    for args in (
        ["init", "-q", "."],
        [
            "-c",
            "user.email=t@example.test",
            "-c",
            "user.name=t",
            "commit",
            "-q",
            "--allow-empty",
            "-m",
            "init",
        ],
    ):
        result = subprocess.run(
            ["git", "-C", str(path), *args], capture_output=True, text=True
        )
        if result.returncode != 0:
            pytest.skip(f"git unavailable: {result.stderr.strip()}")
    return path


# ---------------------------------------------------------------------------
# Harness pins
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("harness", "package"),
    [
        ("openclaw", "openclaw"),
        ("opencode", "opencode-ai"),
        ("claude-code", "@anthropic-ai/claude-code"),
        ("browser-use", "browser-use"),
    ],
)
def test_bundled_harnesses_report_their_pinned_agent(
    harness: str, package: str, built_image
) -> None:
    built_image(harness)
    pins = provenance.harness_pins(harness)

    assert package in pins, f"{harness} Dockerfile pin not detected: {pins}"
    assert pins[package][0].isdigit()
    assert provenance.harness_meta(harness, None)["agent_version"] == pins[package]


def test_base_image_lines_are_not_mistaken_for_agent_pins() -> None:
    """`FROM node:24-slim` and `COPY --from=...uv:0.11.6` are not agent pins."""
    pins = provenance.harness_pins("opencode")

    assert "node" not in pins
    assert "uv" not in pins
    assert pins["@playwright/mcp"] == "0.0.70"


def test_harness_without_pins_reports_nothing_rather_than_guessing(
    built_image,
) -> None:
    built_image("null")
    meta = provenance.harness_meta("null", "sha256:abc")

    assert meta["pinned_versions"] is None
    assert meta["agent_version"] is None
    assert meta["image_id"] == "sha256:abc"
    # We did look; the Dockerfile simply pins nothing.
    assert meta["pins_source"] == "dockerfile"


def test_reused_image_claims_no_pins(monkeypatch: pytest.MonkeyPatch) -> None:
    """--no-build can run an image far older than the Dockerfile on disk.

    Its pins are then not evidence of what actually ran, so nothing is claimed.
    """
    monkeypatch.delenv(provenance.IMAGE_BUILT_ENV, raising=False)

    meta = provenance.harness_meta("openclaw", "sha256:abc")

    assert meta["pins_source"] == "unverified"
    assert meta["pinned_versions"] is None
    assert meta["agent_version"] is None
    # The image id is still a fact about the run, and is still reported.
    assert meta["image_id"] == "sha256:abc"


def test_pins_are_claimed_for_the_built_harness_only(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv(provenance.IMAGE_BUILT_ENV, "openclaw")

    assert provenance.harness_meta("openclaw", None)["pins_source"] == "dockerfile"
    assert provenance.harness_meta("codex", None)["pins_source"] == "unverified"


def test_human_and_unknown_harnesses_are_safe() -> None:
    assert provenance.harness_pins("human") == {}
    assert provenance.harness_pins("not-a-harness") == {}


def _demo_harness(tmp_path: Path, monkeypatch: pytest.MonkeyPatch, body: str) -> None:
    harness_dir = tmp_path / "demo"
    harness_dir.mkdir(exist_ok=True)
    (harness_dir / "Dockerfile.demo").write_text(body, encoding="utf-8")
    monkeypatch.setattr(provenance, "HARNESS_ROOT", tmp_path)
    monkeypatch.setenv(provenance.IMAGE_BUILT_ENV, "demo")
    provenance.harness_pins.cache_clear()


def test_pip_pins_are_detected(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    _demo_harness(
        tmp_path,
        monkeypatch,
        "FROM python:3.11-slim\nRUN pip install demo-agent==2.4.1 helper-plugin==0.9\n",
    )

    pins = provenance.harness_pins("demo")

    assert pins == {"demo-agent": "2.4.1", "helper-plugin": "0.9"}
    assert provenance.harness_meta("demo", None)["agent_version"] == "2.4.1"


def test_pip_extras_do_not_drop_the_pin(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """`litellm[proxy]==1.77.3` used to match nothing, losing the pin silently."""
    _demo_harness(
        tmp_path,
        monkeypatch,
        'FROM python:3.11-slim\nRUN pip install "litellm[proxy,extra]==1.77.3"\n',
    )

    assert provenance.harness_pins("demo") == {"litellm[proxy,extra]": "1.77.3"}


@pytest.mark.parametrize(
    ("line", "expected"),
    [
        (
            "RUN npm install -g demo@github:acme/demo#a1b2c3d4e5f6a7b8",
            {"demo": "github:acme/demo#a1b2c3d4e5f6a7b8"},
        ),
        (
            "RUN npm install -g demo@git+https://github.com/acme/demo.git#v1.2.3",
            {"demo": "git+https://github.com/acme/demo.git#v1.2.3"},
        ),
        (
            'RUN pip install "demo @ git+https://github.com/acme/demo@abc1234"',
            {"demo": "git+https://github.com/acme/demo@abc1234"},
        ),
    ],
)
def test_revision_pins_are_detected(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    line: str,
    expected: dict[str, str],
) -> None:
    """A preview-stage agent is pinned to a commit, not a released version."""
    _demo_harness(tmp_path, monkeypatch, f"FROM python:3.11-slim\n{line}\n")

    assert provenance.harness_pins("demo") == expected


def test_floating_dist_tags_are_not_recorded_as_pins(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """`@next` names a moving target; calling it a pin would be a false claim."""
    _demo_harness(
        tmp_path, monkeypatch, "FROM node:24-slim\nRUN npm install -g demo@next\n"
    )

    assert provenance.harness_pins("demo") == {}
    assert provenance.harness_meta("demo", None)["agent_version"] is None


def test_url_userinfo_is_not_mistaken_for_a_pin(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _demo_harness(
        tmp_path,
        monkeypatch,
        "FROM python:3.11-slim\nRUN curl -sf https://user@host.example/x\n",
    )

    assert provenance.harness_pins("demo") == {}


# ---------------------------------------------------------------------------
# Corpus revision
# ---------------------------------------------------------------------------


def test_bundled_task_reports_its_suite_and_path() -> None:
    task_dir = ASSET_ROOT / "test-cases" / "v2" / "example-task"

    corpus = provenance.corpus_meta(task_dir)

    assert corpus["suite"] == "v2"
    assert corpus["path"] == "test-cases/v2"


def test_external_cases_dir_claims_no_revision(tmp_path: Path) -> None:
    """An explicit --cases-dir has a history that is not ClawBench's to claim."""
    corpus = provenance.corpus_meta(tmp_path / "my-suite" / "task-1")

    assert corpus["suite"] == "my-suite"
    assert corpus["path"] is None
    assert corpus["revision"] is None


def test_missing_task_dir_is_all_null() -> None:
    assert provenance.corpus_meta(None) == {
        "suite": None,
        "path": None,
        "revision": None,
    }


# ---------------------------------------------------------------------------
# ClawBench revision
# ---------------------------------------------------------------------------


def test_commit_lookup_outside_a_checkout_is_null_not_a_failure(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A PyPI install has no git repository; that must not fail a run."""
    monkeypatch.setattr(provenance, "SOURCE_ROOT", None)
    provenance._repo_root.cache_clear()
    provenance.clawbench_commit.cache_clear()

    assert provenance.clawbench_commit() == {
        "commit": None,
        "branch": None,
        "dirty": None,
    }


def test_missing_git_binary_is_null_not_a_failure(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def no_git(*args: object, **kwargs: object) -> None:
        raise FileNotFoundError("git")

    monkeypatch.setattr(subprocess, "run", no_git)

    assert provenance._git(Path("."), "rev-parse", "HEAD") is None


def test_dirty_is_null_when_the_lookup_itself_failed(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """Unknown is not the same claim as clean."""
    monkeypatch.setattr(provenance, "_repo_root", lambda: tmp_path)
    monkeypatch.setattr(provenance, "_git", lambda *args: None)
    provenance.clawbench_commit.cache_clear()

    assert provenance.clawbench_commit()["dirty"] is None


def test_git_distinguishes_empty_output_from_failure(tmp_path: Path) -> None:
    """A clean `git status` succeeds with no output; that is an answer.

    Folding "" into None here is what made `dirty` unable to ever be False.
    """
    repo = _git_repo(tmp_path / "repo")

    assert provenance._git(repo, "status", "--porcelain") == ""
    assert provenance._git(repo, "rev-parse", "HEAD")
    assert provenance._git(repo, "not-a-git-command") is None


def test_clean_and_dirty_trees_are_distinguished(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    repo = _git_repo(tmp_path / "repo")
    monkeypatch.setattr(provenance, "_repo_root", lambda: repo)

    provenance.clawbench_commit.cache_clear()
    clean = provenance.clawbench_commit()
    assert clean["dirty"] is False
    assert clean["commit"]

    (repo / "changed.txt").write_text("edited", encoding="utf-8")
    provenance.clawbench_commit.cache_clear()
    assert provenance.clawbench_commit()["dirty"] is True


# ---------------------------------------------------------------------------
# The assembled block
# ---------------------------------------------------------------------------


def test_provenance_block_has_a_stable_shape(built_image) -> None:
    built_image("openclaw")
    block = provenance.make_provenance(
        harness="openclaw",
        harness_image_id="sha256:abc",
        task_dir=ASSET_ROOT / "test-cases" / "v2" / "example-task",
    )

    assert set(block) == {
        "clawbench_version",
        "commit",
        "branch",
        "dirty",
        "corpus",
        "harness",
    }
    assert set(block["corpus"]) == {"suite", "path", "revision"}
    assert set(block["harness"]) == {
        "name",
        "image_id",
        "pinned_versions",
        "agent_version",
        "pins_source",
    }
    assert block["harness"]["name"] == "openclaw"
