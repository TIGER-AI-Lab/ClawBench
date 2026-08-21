# ClawBench — Scoring Logic

**This document has moved to [`eval/scoring.md`](../eval/scoring.md).**

It lives next to the code that implements it — `eval/rescore.py` and the
`runner/judge*.py` modules — so the spec and the scorer are edited together.

This page is kept so existing links keep working. The canonical document covers
the same ground: the [summary](../eval/scoring.md#summary), Stage 1
(final-request interception), Stage 2 (LLM judge), the final score, why the
benchmark uses two stages, how runs aggregate into a leaderboard row, and
[reproducing every published number](../eval/scoring.md#reproducibility) from
the public traces with `clawbench-rescore`.
