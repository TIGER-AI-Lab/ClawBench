"""Shared rendering for intercepted request bodies sent to LLM judges."""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any


DEFAULT_BODY_LIMIT = 6000


@dataclass(frozen=True)
class RenderedBody:
    """The prompt text and provenance for one intercepted request body."""

    text: str
    original_length: int
    truncated: bool
    omitted_length: int
    limit: int
    empty_placeholder: bool

    def prompt_text(self) -> str:
        """Return the body text, including an explicit truncation warning."""
        if not self.truncated:
            return "(empty)" if self.empty_placeholder else self.text
        return (
            f"{self.text}\n\n"
            "BODY TRUNCATION NOTICE:\n"
            f"The body was truncated to {self.limit} characters. "
            f"The original body length was {self.original_length} characters, "
            f"and {self.omitted_length} characters were omitted. "
            "A truncated body is insufficient evidence for a positive lenient "
            "match; do not treat unseen fields as absent.\n"
        )

    def verdict_metadata(self) -> dict[str, bool | int]:
        """Return stable metadata that lets rescores distinguish sliced bodies."""
        return {
            "body_truncated": self.truncated,
            "body_length": self.original_length,
        }


def render_body(body: Any, *, limit: int = DEFAULT_BODY_LIMIT) -> RenderedBody:
    """Serialize and cap a request body using the judges' shared representation."""
    if limit < 1:
        raise ValueError("body render limit must be positive")
    if isinstance(body, (dict, list)):
        source = json.dumps(body, ensure_ascii=False, indent=2)
    elif body is None:
        source = ""
    else:
        source = str(body)

    original_length = len(source)
    truncated = original_length > limit
    text = source[:limit]
    return RenderedBody(
        text=text,
        original_length=original_length,
        truncated=truncated,
        omitted_length=max(0, original_length - limit),
        limit=limit,
        empty_placeholder=body is None,
    )
