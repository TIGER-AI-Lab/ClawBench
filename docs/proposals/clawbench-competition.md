# Proposal: The ClawBench Challenge (shared task / competition)

*Status: internal draft for maintainer review — not yet submitted anywhere.*

## Why a competition

Benchmarks grow through leaderboard churn. A deadline-driven challenge converts
passive citations into active participants: every team that enters runs our
harness, writes a system paper that cites us, and argues about our metric.
Precedents: WebArena-style community evals, the GAIA leaderboard, Terminal-Bench
inside Harbor. ClawBench's differentiator — live websites — is also its
publicity hook: *"can your agent actually order dinner?"*

## Two venue options

| | Option A — WAB @ COLM 2027 shared task | Option B — NeurIPS 2027 competition track |
| --- | --- | --- |
| Fit | Our paper is already accepted at WAB (COLM 2026); organizers know us | Bigger stage, formal review of proposals |
| Timeline | Propose to organizers ~Q4 2026 | Proposals typically due ~Feb–Mar 2027 |
| Effort | Lower (workshop-scale, ~10–20 teams) | Higher (infra hardening, docs, support) |
| Recommendation | **Do this first** | Apply in parallel if A goes well |

## Task design

- **Corpus:** frozen V2 subset (~60 tasks) + **20 hidden tasks** authored for
  the competition and revealed only at eval time (contamination control — task
  *style* is public, instances are not).
- **Tracks:**
  1. **Open track** — any model/harness combo; submissions are a config for our
     runner (model endpoint + harness choice + prompt pack).
  2. **Efficiency track** — same, but scored as reward per dollar of API cost
     (cost from `agent-messages.jsonl` token usage).
- **Scoring:** the existing two-stage pipeline (interception + LLM judge,
  lenient rubric ranks; strict rubric as tiebreak). Judge model + rubric are
  frozen and published at launch.
- **Execution model:** *organizers run everything.* Teams submit configs, we
  execute on our infra during a fixed 72-hour window, and each team receives
  their full five-layer traces back. This avoids credential-sharing, keeps live
  sites load-managed, and makes cheating structurally hard (we own the
  recordings). Spot re-runs of top-3 entries before announcing winners.
- **Live-site variance:** every submission runs in the same window; each task
  is attempted twice, best-of-2 counts. Site outages are dropped for all teams
  symmetrically.

## Budget envelope (rough)

- 20 teams × 80 tasks × 2 attempts ≈ 3,200 runs; at ~$0.5–2 API cost per run
  → $1.6k–6.4k judge+agent cost if we sponsor the API budget, or near-zero if
  teams bring their own keys (recommended: teams bring keys; we sponsor the
  judge).
- Compute: batch infra already supports `--max-concurrent`; 3,200 runs × ~10
  min ≈ 530 machine-hours over the window → fits 8–10 parallel workers.
- Prizes: leaderboard glory + co-authorship on the competition report is
  standard for workshop-scale; cash prizes only if a sponsor appears (Steel /
  Browserbase / an API vendor are natural fits — the Day-1 outreach channel
  doubles as sponsor pipeline).

## What exists already vs. what's needed

| Ready | Needed |
| --- | --- |
| Runner, harnesses, interceptor, judge, leaderboard site | 20 hidden tasks (2 author-days) |
| Trace delivery pipeline (HF) | Submission portal (Google Form + config schema is enough for v1) |
| Reproducibility protocol (±2 pp) | Competition report template; 2 organizers on rotation during the window |

## Next actions (upon maintainer approval)

1. Email WAB organizers proposing the shared task (draft ready).
2. Freeze the judge config + write the 2-page participant handbook.
3. Author the hidden task set (kept out of the public repo until after the event).
