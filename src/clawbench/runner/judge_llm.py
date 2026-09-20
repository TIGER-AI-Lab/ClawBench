"""lenient LLM judge for ClawBench V2.

Difference from src/clawbench/runner/judge.py:
- Original rubric: "ambiguous or partially correct → mismatch" (strict)
- lenient rubric:    "no explicit contradiction → match" (lenient on missing info)

Rule (lenient spec):
  match = True  iff the intercepted request does NOT explicitly contradict
                    any explicit field in the instruction.
  match = False iff the request explicitly contradicts an explicit field
                    (wrong item, wrong color when color was specified,
                     wrong quantity when quantity was specified, ...).
  Unspecified fields, missing info, partial coverage → match = True.

Why: V2 reward signal is "minimal alignment" — we only penalize when
the agent did the WRONG thing, not when the agent omitted a detail not
constrained by the instruction. This pulls reported scores up by ~10-30pp
and matches the public Sonnet 4.6 reference (Intercepted 58% / Reward 44%).

The rubric prompt below is the only thing this module owns. Transport,
api_type dispatch, retries, and verdict parsing are judge.py's, so the two
rubrics cannot drift in the ways they had: this module used to lack
judge_context, route openai-responses at /chat/completions, reject
google-generative-ai outright, and cap max_tokens at 800.

Usage (same interface as judge.py for drop-in replacement):
    from judge_llm import judge_request
    verdict = judge_request(model_cfg, judge_model, instruction, intercept)
"""

from __future__ import annotations

from typing import Any

from clawbench.runner.judge import (
    _build_user_msg,
    _parse_verdict,  # noqa: F401  — re-export: keeps the lenient path under test
    _run_judge,
)

__all__ = ["JUDGE_SYSTEM", "judge_request"]


JUDGE_SYSTEM = """You are a lenient evaluator for a web-agent benchmark.

A user gave a natural-language INSTRUCTION to an autonomous browser agent.
The agent navigated a real website and finally produced a single HTTP request
(URL + method + body) that we INTERCEPTED before it was sent to the server.

You decide whether this intercepted request ALIGNS with the user's instruction.

# Rubric (CRITICAL — read carefully)

match = TRUE if there is NO EXPLICIT CONTRADICTION between the request and
the instruction. The default verdict is TRUE.

match = FALSE only if the request EXPLICITLY contradicts a field the user
EXPLICITLY specified in the instruction. Examples of contradiction:
- Instruction says "red shirt", request body shows "color: blue"
- Instruction says "quantity 2", request body shows "qty: 5"
- Instruction says "deliver to home", request body shows "deliver to work"
- Instruction asks to enroll in CS50, request enrolls in CS61

# What is NOT a contradiction (default to match = TRUE)

- Instruction did not specify a field, request omits or has any value for it
  → MATCH (the user did not constrain it)
- Instruction said "3pm", request body has no time field at all
  → MATCH (info absent, not contradicted)
- PDF resume left blank where instruction did not require content
  → MATCH
- Cosmetic differences (timestamps, session IDs, affiliate codes, currency
  symbols, formatting) → MATCH
- Ambiguous wording where multiple interpretations work → MATCH
- Agent picked a reasonable default for unspecified options → MATCH
- Color, size, time, quantity not mentioned in instruction → MATCH

# Output

Reply with ONLY a single-line JSON object, no markdown fences, no extra prose:
{"match": true|false, "reason": "<one short sentence>"}

Default is true. Only return false when you can name a SPECIFIC explicit
field from the instruction that the request EXPLICITLY contradicts.
"""


def judge_request(
    model_cfg: dict,
    judge_model_name: str,
    instruction: str,
    intercept: dict[str, Any],
    *,
    judge_context: dict[str, Any] | None = None,
    retries: int = 2,
) -> dict[str, Any]:
    """Judge an intercepted HTTP request under the lenient rubric.

    Same call signature and return shape as judge.judge_request, plus a
    ``rubric`` key naming which rubric produced the verdict.
    """
    user = _build_user_msg(instruction, intercept, judge_context)
    verdict = _run_judge(model_cfg, judge_model_name, JUDGE_SYSTEM, user, retries)
    return {**verdict, "rubric": "lenient"}
