# Hugging Face Space Metadata Checklist

Use this checklist when updating the `TIGER-Lab/ClawBench` Hugging Face Space
README. The goal is to keep the Space discoverable while making each refresh
easy to audit.

## README Front Matter

Copy this block to the top of the Space `README.md`, then update the placeholder
values when the Space banner and model roster change.

```yaml
---
title: ClawBench
emoji: 🐾
colorFrom: indigo
colorTo: yellow
sdk: gradio
sdk_version: 5.30.0
app_file: app.py
pinned: true
license: apache-2.0
thumbnail: assets/social-card.png
models:
  - TIGER-Lab/ClawBench
datasets:
  - NAIL-Group/ClawBench
  - TIGER-Lab/ClawBench
  - NAIL-Group/ClawBenchV1Trace
  - NAIL-Group/ClawBenchV2Trace
tags:
  - benchmark
  - browser-agents
  - computer-use
  - leaderboard
last_refresh: 2026-06-08
---
```

## Refresh Checklist

- Upload the 1280 x 640 Space banner before setting `thumbnail:`.
- Keep `models:` aligned with the leaderboard model roster shown in the Space.
- Keep `datasets:` aligned with the task and trace datasets linked from this
  repository.
- Update `last_refresh:` whenever the Space README or leaderboard metadata is
  refreshed.
- When a GitHub release changes the leaderboard, mirror the release summary as a
  Space commit so Hugging Face records the same update.

## Weekly Heartbeat

The weekly heartbeat can be a minimal Space README commit that only advances
`last_refresh:`. Keep the commit message explicit, for example:

```text
chore(space): refresh ClawBench metadata for 2026-06-08
```

That gives maintainers a low-risk way to refresh Space metadata without changing
the benchmark code or leaderboard results.
