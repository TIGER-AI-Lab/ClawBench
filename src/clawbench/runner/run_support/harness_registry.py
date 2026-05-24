"""Central harness registry loading and validation."""

from dataclasses import dataclass
from pathlib import Path
import re
from typing import Any

import yaml

from clawbench.utils.paths import HARNESS_ROOT


@dataclass(frozen=True)
class AgentMessageSource:
    type: str
    path: str | None = None
    root: str | None = None
    name: str | None = None
    pattern: str | None = None


@dataclass(frozen=True)
class HarnessRegistry:
    default: str
    base_image: str
    base_dockerfile: Path
    base_entrypoint_script: Path
    base_agent_message_sources: tuple[AgentMessageSource, ...]
    harnesses: tuple[str, ...]
    harness_images: dict[str, str]
    harness_dockerfiles: dict[str, Path]
    harness_setup_scripts: dict[str, Path]
    harness_run_scripts: dict[str, Path]
    harness_usage_emitters: dict[str, Path]
    harness_extra_files: dict[str, tuple[Path, ...]]
    harness_agent_message_sources: dict[str, tuple[AgentMessageSource, ...]]


HARNESS_REGISTRY_YAML = HARNESS_ROOT / "harnesses.yaml"
CONTAINER_GLOB_RE = re.compile(r"^[A-Za-z0-9_./*?[\]-]+$")


def _registry_error(path: Path, message: str) -> ValueError:
    return ValueError(f"Invalid harness registry {path}: {message}")


def _required_mapping(
    data: Any,
    key: str,
    path: Path,
) -> dict[str, Any]:
    value = data.get(key) if isinstance(data, dict) else None
    if not isinstance(value, dict):
        raise _registry_error(path, f"'{key}' must be a mapping")
    return value


def _required_str(data: dict[str, Any], key: str, path: Path) -> str:
    value = data.get(key)
    if not isinstance(value, str) or not value.strip():
        raise _registry_error(path, f"'{key}' must be a non-empty string")
    return value.strip()


def _optional_str_list(data: dict[str, Any], key: str, path: Path) -> list[str]:
    value = data.get(key, [])
    if value is None:
        return []
    if not isinstance(value, list):
        raise _registry_error(path, f"'{key}' must be a list of strings")
    result: list[str] = []
    for index, item in enumerate(value):
        if not isinstance(item, str) or not item.strip():
            raise _registry_error(
                path,
                f"'{key}' item {index} must be a non-empty string",
            )
        result.append(item.strip())
    return result


def _optional_agent_message_sources(
    data: dict[str, Any],
    path: Path,
) -> tuple[AgentMessageSource, ...]:
    value = data.get("agent_message_sources", [])
    if value is None:
        return ()
    if not isinstance(value, list):
        raise _registry_error(path, "'agent_message_sources' must be a list")

    sources: list[AgentMessageSource] = []
    for index, item in enumerate(value):
        if not isinstance(item, dict):
            raise _registry_error(
                path,
                f"agent_message_sources[{index}] must be a mapping",
            )
        source_type = _required_str(item, "type", path)
        if source_type == "file":
            sources.append(
                AgentMessageSource(
                    type=source_type,
                    path=_required_str(item, "path", path),
                )
            )
        elif source_type == "find_latest":
            sources.append(
                AgentMessageSource(
                    type=source_type,
                    root=_required_str(item, "root", path),
                    name=_required_str(item, "name", path),
                )
            )
        elif source_type == "latest_glob":
            pattern = _required_str(item, "pattern", path)
            if not CONTAINER_GLOB_RE.fullmatch(pattern):
                raise _registry_error(
                    path,
                    f"unsafe latest_glob pattern: {pattern}",
                )
            sources.append(AgentMessageSource(type=source_type, pattern=pattern))
        else:
            raise _registry_error(
                path,
                f"unsupported agent_message_sources type: {source_type}",
            )
    return tuple(sources)


def _resolve_registry_file(root: Path, rel_path: str, path: Path, label: str) -> Path:
    registry_file = (root / rel_path).resolve()
    try:
        registry_file.relative_to(root.resolve())
    except ValueError as e:
        raise _registry_error(
            path,
            f"{label} escapes harness root: {rel_path}",
        ) from e
    if not registry_file.is_file():
        raise _registry_error(path, f"{label} does not exist: {rel_path}")
    return registry_file


def _resolve_registry_dockerfile(root: Path, rel_path: str, path: Path) -> Path:
    return _resolve_registry_file(root, rel_path, path, "dockerfile")


def load_harness_registry(path: Path = HARNESS_REGISTRY_YAML) -> HarnessRegistry:
    """Load and validate the central harness registry."""
    if not path.is_file():
        raise FileNotFoundError(f"Harness registry not found: {path}")
    raw = yaml.safe_load(path.read_text()) or {}
    if not isinstance(raw, dict):
        raise _registry_error(path, "top-level YAML must be a mapping")

    root = path.parent
    default = _required_str(raw, "default", path)

    base = _required_mapping(raw, "base", path)
    base_image = _required_str(base, "image", path)
    base_dockerfile = _resolve_registry_dockerfile(
        root,
        _required_str(base, "dockerfile", path),
        path,
    )
    base_entrypoint_script = _resolve_registry_file(
        root,
        _required_str(base, "entrypoint_script", path),
        path,
        "entrypoint_script",
    )
    base_agent_message_sources = _optional_agent_message_sources(base, path)

    entries = raw.get("harnesses")
    if not isinstance(entries, list) or not entries:
        raise _registry_error(path, "'harnesses' must be a non-empty list")

    names: list[str] = []
    images: dict[str, str] = {}
    dockerfiles: dict[str, Path] = {}
    setup_scripts: dict[str, Path] = {}
    run_scripts: dict[str, Path] = {}
    usage_emitters: dict[str, Path] = {}
    extra_files: dict[str, tuple[Path, ...]] = {}
    agent_message_sources: dict[str, tuple[AgentMessageSource, ...]] = {}
    for index, entry in enumerate(entries):
        if not isinstance(entry, dict):
            raise _registry_error(path, f"harnesses[{index}] must be a mapping")
        name = _required_str(entry, "name", path)
        if name in images:
            raise _registry_error(path, f"duplicate harness name: {name}")
        names.append(name)
        images[name] = _required_str(entry, "image", path)
        dockerfiles[name] = _resolve_registry_dockerfile(
            root,
            _required_str(entry, "dockerfile", path),
            path,
        )
        setup_scripts[name] = _resolve_registry_file(
            root,
            _required_str(entry, "setup_script", path),
            path,
            "setup_script",
        )
        run_scripts[name] = _resolve_registry_file(
            root,
            _required_str(entry, "run_script", path),
            path,
            "run_script",
        )
        usage_emitters[name] = _resolve_registry_file(
            root,
            _required_str(entry, "usage_emitter", path),
            path,
            "usage_emitter",
        )
        extra_files[name] = tuple(
            _resolve_registry_file(root, rel_path, path, "extra_files")
            for rel_path in _optional_str_list(entry, "extra_files", path)
        )
        agent_message_sources[name] = _optional_agent_message_sources(entry, path)

    if default not in images:
        raise _registry_error(path, f"default harness is not listed: {default}")

    return HarnessRegistry(
        default=default,
        base_image=base_image,
        base_dockerfile=base_dockerfile,
        base_entrypoint_script=base_entrypoint_script,
        base_agent_message_sources=base_agent_message_sources,
        harnesses=tuple(names),
        harness_images=images,
        harness_dockerfiles=dockerfiles,
        harness_setup_scripts=setup_scripts,
        harness_run_scripts=run_scripts,
        harness_usage_emitters=usage_emitters,
        harness_extra_files=extra_files,
        harness_agent_message_sources=agent_message_sources,
    )


HARNESS_REGISTRY = load_harness_registry()
