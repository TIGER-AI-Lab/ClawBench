"""Model-dependent sampling fields for OpenAI Chat Completions calls.

The preflight probe and the judges used to send ``max_tokens`` plus
``temperature: 0`` for every ``openai-completions`` model. Two model
families reject parts of that pair with a 400:

- OpenAI reasoning models (the o-series and GPT-5) do not accept
  ``max_tokens`` — the budget field is ``max_completion_tokens`` — and
  they reject an explicit ``temperature``.
- Kimi K2.x / K3 models reject an explicit ``temperature`` ("do not
  pass temperature explicitly"); ``max_tokens`` stays valid there.

Every other model keeps the historical ``max_tokens`` +
``temperature: 0`` pair unchanged.
"""

from __future__ import annotations

import re
from typing import Any

_O_SERIES_RE = re.compile(r"o\d")


def _bare_model_name(model: str) -> str:
    return model.rsplit("/", 1)[-1].strip().lower()


def uses_completion_tokens(model: str) -> bool:
    """True for models that reject ``max_tokens`` (o-series, GPT-5)."""
    name = _bare_model_name(model)
    return name.startswith("gpt-5") or _O_SERIES_RE.match(name) is not None


def rejects_explicit_temperature(model: str) -> bool:
    """True for models that 400 on an explicit ``temperature``."""
    name = _bare_model_name(model)
    return (
        uses_completion_tokens(model)
        or "kimi-k2" in name
        or "kimi-k3" in name
    )


def chat_sampling_fields(model: str, max_tokens: int) -> dict[str, Any]:
    """Sampling fields for one Chat Completions request to ``model``."""
    fields: dict[str, Any] = {}
    if uses_completion_tokens(model):
        fields["max_completion_tokens"] = max_tokens
    else:
        fields["max_tokens"] = max_tokens
    if not rejects_explicit_temperature(model):
        fields["temperature"] = 0
    return fields
