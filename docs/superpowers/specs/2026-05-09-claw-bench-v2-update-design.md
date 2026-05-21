---
title: ClawBench v2 + HF Dataset Announcement Update
date: 2026-05-09
status: draft (awaiting user approval)
owner: reacher-z
---

# ClawBench v2 Update + HF Dataset Announcement — Design

## Goal

Three coordinated updates so the public surface (GitHub README, claw-bench.com, both Hugging Face dataset cards) reflects the v2 corpus and the newly-published `ClawBenchV1Trace` dataset.

## Surfaces & current state

| Surface | Current state | Source of truth |
|---|---|---|
| GitHub README | mentions `NAIL-Group/ClawBench` HF dataset; **no** `ClawBenchV1Trace` reference; no dedicated "Datasets" section | `/home/nick/work/ClawBench/README.md` |
| claw-bench.com homepage | Flask app, hardcoded v1 numbers (153 tasks / 144 platforms / 8 categories / 6 models / per-category scores all in `server.py` lines 38–58) | `/opt/claw-bench/website/server.py` + `templates/index.html` (NOT git-tracked) |
| HF `NAIL-Group/ClawBench` | populated card (~870KB rendered HTML) | HF Hub repo |
| HF `NAIL-Group/ClawBenchV1Trace` | barebones default placeholder card | HF Hub repo |

## Data we have right now

- **v1 corpus**: 153 tasks, 144 platforms, 8 categories — already on the live site.
- **v1 eval results**: 6 models in `eval-results/*-eval-results.json` (claude-sonnet-4-6, claude-opus-4-6, claude-haiku-4-5-20251001, gpt-5.4-2026-03-05, gpt-5.4-mini-2026-03-17, kimi-k2.5). 153 entries each. **Identical copies live on the server already.**
- **v2 corpus**: 130 tasks in `test-cases/v2/` (each with `task.json` containing `metadata`, `instruction`, `eval_schema`, `time_limit`). Only 4 task IDs overlap with v1 — v2 is mostly **new** content (IDs 179–521+), not a v1 subset.
- **v2 eval results**: NOT yet aggregated. Raw runs in `claw-output/v2-all-hermes*/` cover only **2 models** so far (`deepseek-v4-flash`, `glm-5.1`). Insufficient for a competitive leaderboard.

## Workstream split

Sequenced low-blast-radius first.

### Workstream 1 — README + HF cross-link (ship today)

**Why first**: pure docs, no server touch, no aggregation work, immediate visibility win.

Concrete edits:

1. **README.md**:
   - Add `ClawBenchV1Trace` HF Dataset badge alongside the existing `ClawBench` badge (line 13 area).
   - Insert a new top-level `## Datasets` section between `## How It Works` (current line 112) and `## How ClawBench compares` (current line 377). Two cards:
     - `NAIL-Group/ClawBench` — task definitions, rubrics, metadata. `hf download NAIL-Group/ClawBench`.
     - `NAIL-Group/ClawBenchV1Trace` — full 5-layer execution traces (DOM, network, screenshots, action trace, console) for every model run. `hf download NAIL-Group/ClawBenchV1Trace`.
   - Add News entry at the top of `## News` (current line 78): `[2026-05-09] Released **ClawBenchV1Trace** — full 5-layer execution traces for all evaluated models.`

2. **HF `NAIL-Group/ClawBench` card** (existing, has content):
   - Append a "Related" section pointing to `ClawBenchV1Trace` for raw traces.

3. **HF `NAIL-Group/ClawBenchV1Trace` card** (currently empty):
   - Write full `README.md` covering: what's in it (5-layer trace per task per model), file layout, model coverage, how to load (Datasets API + raw download), citation block, link back to `ClawBench` task definitions and to the GitHub repo.

4. **Clean up "Built by ZJU-REAL" tagline** (README line 68): user confirmed this is historical legacy, not their attribution. Default action: replace with `Built by NAIL Group` to match the HF org. (Alt: remove the "Built by ..." part entirely, keep just the sister-project + Chrome line. → Q1.2.) The `ZJU-REAL` link in the awesome-lists badges (line 31) is a third-party featured-list reference and stays.

**Open questions for user**:
- Q1.1: Confirm the V1Trace dataset content is the 5-layer recording per task per model (DOM, network, screenshots, action trace, console). If not, give one-line content description so the V1Trace card README is accurate.
- Q1.2: For the line-68 cleanup — `Built by NAIL Group` (default) vs remove the "Built by ..." prefix entirely?

### Workstream 2 — Homepage v1/v2 tab switcher (ship within the week)

**Approved layout** (from clarifying Q): single page, v1/v2 tab switcher at the top of the leaderboard/corpus section. URL shape: `/?corpus=v2` or hash `#v2` — **no route changes**, all current links keep working.

Two phases:

**Phase 2a — Refactor server to data-driven (no UI change)**:
- Move hardcoded `MODELS`, `_PER_CATEGORY`, total-task counts out of `server.py` into versioned JSON: `data/v1/leaderboard.json` + `data/v1/corpus.json`. Default behavior unchanged.
- Add a `CORPUS_VERSIONS = ["v1"]` registry. Site renders the same as today.

**Phase 2b — Add v2 tab**:
- Build `data/v2/corpus.json` from `test-cases/v2/*/task.json` files (script: `scripts/build-corpus-manifest.py v2`). Fields surfaced: task_id, metaclass, class, description, platform, sites_involved, time_limit.
- Add `data/v2/leaderboard.json` — initially empty / "Evaluations in progress" placeholder. No scores until Workstream 3 ships.
- Add v1/v2 tab UI in `templates/index.html`. v2 tab shows: 130-task corpus, category breakdown, "Leaderboard coming soon" banner.

Deployment:
- Server code is **NOT git-tracked**. Add it to git: clone `/opt/claw-bench/website/` → new repo `reacher-z/claw-bench-site` (private or public, your call), keep prod box pulling from that. Backup `server.py.bak.<ts>` is the existing pattern, keep it.
- Deploy = `git pull && systemctl restart clawbench` on Vultr. Rollback = `git revert && restart`.

**Open questions for user**:
- Q2.1: Where should the new `claw-bench-site` repo live — public under `reacher-z/`, private, or another org?
- Q2.2: Per-task detail page on v2 — same layout as v1 (model trace links etc.), or a simpler "task only, no model traces" view since v2 traces aren't published yet?

### Workstream 3 — v2 leaderboard (deferred until data is ready)

**Blocking on data, not on us.**

Tasks:
1. Aggregate `claw-output/v2-all-hermes*/` raw runs into `eval-results/v2/<model>-eval-results.json`. Script: `scripts/aggregate-v2-eval.py`. Same JSON schema as v1.
2. Run more models on v2 (current 2 isn't enough for a leaderboard — v1 has 6).
3. Once ≥4 models done, populate `data/v2/leaderboard.json` and flip the v2 tab from "coming soon" to scores.

Out of scope for this spec — captured for sequencing.

## Risks & mitigations

| Risk | Mitigation |
|---|---|
| Live site breaks during refactor | Keep `server.py.bak.<timestamp>` backup pattern (already in use). Deploy in 2 steps: refactor (Phase 2a, no UI change) → tab UI (Phase 2b). Verify each step against `curl https://claw-bench.com/` before next. |
| Cloudflare cache stale | Bust by changing `?v=` query string on `style.css`/`app.js` (already a cache-bust pattern in the HTML). |
| v2 tab shows empty leaderboard for weeks | Add "Evaluations in progress — see GitHub for v2 corpus details" message linking to repo, so empty state has clear context. |
| HF V1Trace card content I write is inaccurate | Q1.1 above — confirm content with user before publishing. |
| Server-code git split makes future contributors confused | New repo README explicitly says "this is the website code only — for the benchmark itself see reacher-z/ClawBench". Add a `Build / Deploy` note. |

## Out of scope

- Designing a v2 corpus expansion / curation process (corpus already exists in `test-cases/v2/`).
- Migrating away from Cloudflare Tunnel.
- Auth on the data viewer (already removed per `server.py` comment).
- Re-running v1 evals on new models.

## Acceptance criteria

WS1 done when:
- README PR merged with badge, Datasets section, News entry.
- Both HF data cards updated and visible at the URLs.

WS2 done when:
- Site renders identically pre/post refactor (Phase 2a).
- v1/v2 tab switcher works on https://claw-bench.com/.
- v2 tab shows 130 tasks with category/platform breakdown + "leaderboard coming soon".
- Existing `/api/recent-runs` endpoint untouched and still returns 200.

WS3 done when (separate spec / future work):
- v2 eval JSON exists for ≥4 models.
- v2 tab shows real scores.
