"""Model definitions from models/models.yaml.

Kept in `utils` rather than `runner.run_support.config` so that tools which
only score existing runs — `clawbench-rescore`, for one — can resolve a judge
model without importing the runner, which probes for a container engine at
import time and exits when Docker and Podman are both absent.
"""

from pathlib import Path

import yaml

from clawbench.utils.paths import WORKSPACE_ROOT

MODELS_YAML = WORKSPACE_ROOT / "models" / "models.yaml"


class ModelConfigError(Exception):
    """Raised when a model config in models/models.yaml is missing or invalid.

    A plain Exception (not SystemExit) so callers that load a model mid-run
    (e.g. the judge stage, after the agent has already produced results) can
    catch it and continue instead of the process dying before run-meta.json
    is written.
    """


def load_models_yaml(models_yaml: Path | None = None) -> dict:
    """Load all model definitions from models/models.yaml.

    `models_yaml` overrides the workspace-resolved default, for callers that
    expose an explicit --models-yaml flag.

    Raises ModelConfigError rather than exiting, for the same reason
    load_model_config does: this runs inside the judge stage too, where a
    SystemExit would escape the handlers and lose the run's metadata.
    """
    path = models_yaml or MODELS_YAML
    if not path.exists():
        raise ModelConfigError(
            f"{path} not found (copy models.example.yaml and fill in your keys)"
        )
    return yaml.safe_load(path.read_text()) or {}


def load_model_config(model: str, models_yaml: Path | None = None) -> dict:
    """Load a model config by name from models/models.yaml.

    The YAML key is the model name (passed as MODEL_NAME to the container).
    `models_yaml` overrides the workspace-resolved default.
    """
    path = models_yaml or MODELS_YAML
    all_models = load_models_yaml(models_yaml)
    if model not in all_models:
        raise ModelConfigError(
            f"model '{model}' not found in {path}. "
            f"Available models: {', '.join(sorted(all_models))}"
        )

    # Validate model name characters. Note: '/' and ':' are valid in
    # vendor-prefixed ids like 'anthropic/claude-sonnet-4-6' or
    # 'arcee-ai/trinity-large-preview:free' — they get sanitized to
    # '--' before being used as path components. We only reject characters
    # that could cause real trouble in shell/filesystem paths even after
    # that sanitization.
    bad = [c for c in ' \\*?"<>|' if c in model]
    if bad:
        raise ModelConfigError(
            f"model name '{model}' contains illegal character(s): "
            f"{' '.join(repr(c) for c in bad)}"
        )

    config = dict(all_models[model])
    config["model"] = model  # the YAML key IS the model name

    required = ["base_url", "api_type"]
    missing = [k for k in required if not config.get(k)]
    if missing:
        raise ModelConfigError(
            f"required field(s) missing for model '{model}': {', '.join(missing)}"
        )

    # Normalize API keys: api_keys list wins, else wrap api_key into list.
    if config.get("api_keys"):
        config["api_key"] = config["api_keys"][0]
    elif config.get("api_key"):
        config["api_keys"] = [config["api_key"]]

    if not config.get("api_keys"):
        raise ModelConfigError(f"no api_key or api_keys for model '{model}'")

    return config
