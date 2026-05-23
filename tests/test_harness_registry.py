"""Tests for the central harness registry."""

from __future__ import annotations

import json
import re
from pathlib import Path

import pytest
import yaml
from jsonschema import Draft202012Validator

from clawbench.runner.run_support.harness_registry import (
    AgentMessageSource,
    HARNESS_REGISTRY,
    HARNESS_REGISTRY_YAML,
    load_harness_registry,
)

EXPECTED_HARNESSES = (
    "openclaw",
    "opencode",
    "claude-code",
    "claude-code-chrome-extension",
    "codex",
    "browser-use",
    "claw-code",
    "hermes",
    "pi",
)

EXPECTED_SCRIPTS = {
    harness: (
        f"{harness}/setup-{harness}.sh",
        f"{harness}/run-{harness}.sh",
    )
    for harness in EXPECTED_HARNESSES
}

EXPECTED_EXTRA_FILES = {
    "claude-code-chrome-extension": (
        "claude-code-chrome-extension/mock-anthropic-api.py",
    ),
    "browser-use": ("browser-use/run-browser-use-agent.py",),
    "claw-code": ("claw-code/claw-code-ndjson.patch.py",),
    "hermes": ("hermes/hermes-capture.py",),
}

EXPECTED_AGENT_MESSAGE_SOURCES = {
    "openclaw": (
        ("file", "/data/agent-messages.jsonl"),
        ("file", "/root/.openclaw/agents/main/sessions/clawbench.jsonl"),
    ),
    "opencode": (("file", "/data/agent-messages.jsonl"),),
    "claude-code": (("file", "/data/agent-messages.jsonl"),),
    "claude-code-chrome-extension": (("file", "/data/agent-messages.jsonl"),),
    "codex": (
        ("file", "/data/agent-messages.jsonl"),
        ("file", "/tmp/codex-stdout.jsonl"),
        ("find_latest", "/root/.codex/sessions", "rollout-*.jsonl"),
    ),
    "browser-use": (("file", "/data/agent-messages.jsonl"),),
    "claw-code": (
        ("file", "/data/agent-messages.jsonl"),
        ("latest_glob", "/root/workspace/.claw/sessions/*/*.jsonl"),
    ),
    "hermes": (
        ("file", "/data/agent-messages.jsonl"),
        ("file", "/tmp/hermes-live-agent-messages.jsonl"),
    ),
    "pi": (
        ("file", "/data/agent-messages.jsonl"),
        ("file", "/data/agent-messages.raw.jsonl"),
    ),
}


def _agent_source_tuples(
    sources: tuple[AgentMessageSource, ...],
) -> tuple[tuple[str, ...], ...]:
    return tuple(
        tuple(
            part
            for part in (
                source.type,
                source.path,
                source.root,
                source.name,
                source.pattern,
            )
            if part is not None
        )
        for source in sources
    )


def test_harness_registry_matches_current_harness_contract() -> None:
    assert HARNESS_REGISTRY.default == "openclaw"
    assert HARNESS_REGISTRY.base_image == "clawbench-base"
    assert HARNESS_REGISTRY.harnesses == EXPECTED_HARNESSES
    assert _agent_source_tuples(HARNESS_REGISTRY.base_agent_message_sources) == (
        ("file", "/data/agent-messages.jsonl"),
    )

    assert HARNESS_REGISTRY.base_dockerfile.is_file()
    assert HARNESS_REGISTRY.base_entrypoint_script.is_file()
    for harness in EXPECTED_HARNESSES:
        assert HARNESS_REGISTRY.harness_images[harness] == f"clawbench-{harness}"
        assert HARNESS_REGISTRY.harness_dockerfiles[harness].is_file()
        setup_script, run_script = EXPECTED_SCRIPTS[harness]
        assert HARNESS_REGISTRY.harness_setup_scripts[harness].is_file()
        assert HARNESS_REGISTRY.harness_run_scripts[harness].is_file()
        assert (
            HARNESS_REGISTRY.harness_setup_scripts[harness]
            .relative_to(HARNESS_REGISTRY.base_dockerfile.parents[1])
            .as_posix()
            == setup_script
        )
        assert (
            HARNESS_REGISTRY.harness_run_scripts[harness]
            .relative_to(HARNESS_REGISTRY.base_dockerfile.parents[1])
            .as_posix()
            == run_script
        )
        assert all(
            extra_file.is_file()
            for extra_file in HARNESS_REGISTRY.harness_extra_files[harness]
        )
        assert tuple(
            extra_file.relative_to(
                HARNESS_REGISTRY.base_dockerfile.parents[1]
            ).as_posix()
            for extra_file in HARNESS_REGISTRY.harness_extra_files[harness]
        ) == EXPECTED_EXTRA_FILES.get(harness, ())
        assert _agent_source_tuples(
            HARNESS_REGISTRY.harness_agent_message_sources[harness]
        ) == EXPECTED_AGENT_MESSAGE_SOURCES.get(harness, ())


def test_harness_registry_matches_json_schema() -> None:
    schema_path = HARNESS_REGISTRY_YAML.with_name("harness.schema.json")
    schema = json.loads(schema_path.read_text())
    registry = yaml.safe_load(HARNESS_REGISTRY_YAML.read_text())

    validator = Draft202012Validator(schema)
    errors = sorted(validator.iter_errors(registry), key=lambda item: list(item.path))

    assert errors == []


def test_harness_registry_tracks_all_dockerfile_harness_copies() -> None:
    harness_root = HARNESS_REGISTRY.base_dockerfile.parents[1]
    copied_sources = {
        HARNESS_REGISTRY.base_dockerfile: {
            HARNESS_REGISTRY.base_entrypoint_script,
        }
    }
    for harness in EXPECTED_HARNESSES:
        copied_sources[HARNESS_REGISTRY.harness_dockerfiles[harness]] = {
            HARNESS_REGISTRY.harness_setup_scripts[harness],
            HARNESS_REGISTRY.harness_run_scripts[harness],
            *HARNESS_REGISTRY.harness_extra_files[harness],
        }

    copy_re = re.compile(r"^\s*COPY\s+harnesses/(\S+)")
    for dockerfile, expected_sources in copied_sources.items():
        actual_sources = {
            (harness_root / match.group(1)).resolve()
            for line in dockerfile.read_text().splitlines()
            if (match := copy_re.match(line))
        }
        assert actual_sources == expected_sources


def _write_registry_fixture(tmp_path: Path, harnesses_yaml: str) -> Path:
    for rel_path in (
        "base/Dockerfile.base",
        "base/entrypoint.sh",
        "alpha/Dockerfile.alpha",
        "alpha/setup-alpha.sh",
        "alpha/run-alpha.sh",
        "beta/Dockerfile.beta",
        "beta/setup-beta.sh",
        "beta/run-beta.sh",
    ):
        path = tmp_path / rel_path
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("FROM scratch\n")
    registry_path = tmp_path / "harnesses.yaml"
    registry_path.write_text(harnesses_yaml)
    return registry_path


def test_load_harness_registry_validates_duplicate_names(tmp_path: Path) -> None:
    registry_path = _write_registry_fixture(
        tmp_path,
        """
default: alpha
base:
  image: clawbench-base
  dockerfile: base/Dockerfile.base
  entrypoint_script: base/entrypoint.sh
  agent_message_sources:
    - type: file
      path: /data/agent-messages.jsonl
harnesses:
  - name: alpha
    image: clawbench-alpha
    dockerfile: alpha/Dockerfile.alpha
    setup_script: alpha/setup-alpha.sh
    run_script: alpha/run-alpha.sh
  - name: alpha
    image: clawbench-alpha-2
    dockerfile: beta/Dockerfile.beta
    setup_script: beta/setup-beta.sh
    run_script: beta/run-beta.sh
""",
    )

    with pytest.raises(ValueError, match="duplicate harness name: alpha"):
        load_harness_registry(registry_path)


def test_load_harness_registry_validates_default_is_listed(tmp_path: Path) -> None:
    registry_path = _write_registry_fixture(
        tmp_path,
        """
default: gamma
base:
  image: clawbench-base
  dockerfile: base/Dockerfile.base
  entrypoint_script: base/entrypoint.sh
harnesses:
  - name: alpha
    image: clawbench-alpha
    dockerfile: alpha/Dockerfile.alpha
    setup_script: alpha/setup-alpha.sh
    run_script: alpha/run-alpha.sh
  - name: beta
    image: clawbench-beta
    dockerfile: beta/Dockerfile.beta
    setup_script: beta/setup-beta.sh
    run_script: beta/run-beta.sh
""",
    )

    with pytest.raises(ValueError, match="default harness is not listed: gamma"):
        load_harness_registry(registry_path)


def test_load_harness_registry_validates_extra_files_exist(tmp_path: Path) -> None:
    registry_path = _write_registry_fixture(
        tmp_path,
        """
default: alpha
base:
  image: clawbench-base
  dockerfile: base/Dockerfile.base
  entrypoint_script: base/entrypoint.sh
harnesses:
  - name: alpha
    image: clawbench-alpha
    dockerfile: alpha/Dockerfile.alpha
    setup_script: alpha/setup-alpha.sh
    run_script: alpha/run-alpha.sh
    extra_files:
      - alpha/missing-helper.py
""",
    )

    with pytest.raises(ValueError, match="extra_files does not exist"):
        load_harness_registry(registry_path)


def test_load_harness_registry_validates_setup_and_run_scripts(tmp_path: Path) -> None:
    registry_path = _write_registry_fixture(
        tmp_path,
        """
default: alpha
base:
  image: clawbench-base
  dockerfile: base/Dockerfile.base
  entrypoint_script: base/entrypoint.sh
harnesses:
  - name: alpha
    image: clawbench-alpha
    dockerfile: alpha/Dockerfile.alpha
    setup_script: alpha/missing-setup.sh
    run_script: alpha/run-alpha.sh
""",
    )

    with pytest.raises(ValueError, match="setup_script does not exist"):
        load_harness_registry(registry_path)


def test_load_harness_registry_validates_agent_message_sources(
    tmp_path: Path,
) -> None:
    registry_path = _write_registry_fixture(
        tmp_path,
        """
default: alpha
base:
  image: clawbench-base
  dockerfile: base/Dockerfile.base
  entrypoint_script: base/entrypoint.sh
harnesses:
  - name: alpha
    image: clawbench-alpha
    dockerfile: alpha/Dockerfile.alpha
    setup_script: alpha/setup-alpha.sh
    run_script: alpha/run-alpha.sh
    agent_message_sources:
      - type: latest_glob
        pattern: /tmp/safe/*.jsonl;rm
""",
    )

    with pytest.raises(ValueError, match="unsafe latest_glob pattern"):
        load_harness_registry(registry_path)
