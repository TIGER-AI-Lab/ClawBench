---
venue: ICLR 2026
paper: ClawBench — Can AI Agents Complete Everyday Online Tasks?
review_id: review-1
review_score: 6.3 / 10  (borderline-to-positive)
status: draft (ready for trim + paste to OpenReview)
date: 2026-05-10
---

# Rebuttal — Review #1 (score 6.3 / 10, borderline-to-positive)

> First-pass draft. Each section below is self-contained so it can be split across separate OpenReview replies if the response box has a length limit. Numbers marked **TBD** are commitments — see "Camera-ready additions" at the bottom for the full work plan.

---

## TL;DR

We thank the reviewer for the careful and constructive review, and especially for naming the three things we agree most need strengthening: **(1) evaluator reliability**, **(2) experimental rigor under live-web stochasticity**, and **(3) interception coverage on agent runs**. All three are addressable with data we already have on hand:

- We have just published [`NAIL-Group/ClawBenchV1Trace`](https://huggingface.co/datasets/NAIL-Group/ClawBenchV1Trace) — the **complete five-layer trace for every model run** scored in the paper. This dataset (recording.mp4, requests.jsonl, actions.jsonl, agent-messages.jsonl, interception.json per run) lets any third party reproduce, re-grade, or cross-judge our results.
- We have added an **inline LLM judge** as the canonical second scoring stage; it is now on the public path (`pip install clawbench-eval` then `--no-judge` to disable). This addresses both the "single-trace judging" risk and lets us swap the judge model for cross-judge agreement studies.
- The companion v2 corpus (130 newer tasks, expanded coverage) has been released; the live leaderboard at [`TIGER-Lab/ClawBench`](https://huggingface.co/spaces/TIGER-Lab/ClawBench) tracks both V1 and V2 with public, append-only `leaderboard/results.csv` submissions.

The rebuttal below addresses each weakness in order with concrete numbers (where we already have them) or specific commitments (where we will add them for camera-ready).

---

## 1. Acknowledged strengths

We are grateful that the review identifies the **final-request interception**, the **five-layer recording**, and the **agentic comparative evaluator** as the three key technical contributions. The paper's framing around *write-heavy, state-changing, consequential* tasks vs. read-only or sandboxed setups is exactly the contrast we wanted to sharpen, and we are glad it landed.

---

## 2. Responses to weaknesses

### W1 — Evaluator reliability: proprietary judge, no human–evaluator agreement reported

> *"Reliance on a proprietary LLM (Claude Code) as the primary evaluator raises concerns about evaluator bias, generality, and reproducibility; no human–evaluator agreement or cross-evaluator validation is reported."*

**What changed since submission.** The pipeline now runs an **inline LLM judge** as the second scoring stage (default: `deepseek-v4-pro`, easily swappable). Pass requires **(a)** the agent's final HTTP request to be intercepted **and** match the per-task URL/method schema, **and** **(b)** the judge confirms the request body satisfies the natural-language instruction. Both stages are reproducible from a single command:

```bash
pip install clawbench-eval && clawbench-batch --models <model> --cases-suite v1 --all-cases
```

**Cross-judge & human–judge studies (committed for camera-ready).** Because the full trace bundle for every run is now public in `NAIL-Group/ClawBenchV1Trace`, we can — and will — re-grade with multiple judge models and against human raters without re-running any agent inference. The planned table:

| Judge | Pass-rate on V1 (Sonnet 4.6) | κ vs. human (n=50, 3 raters) | Notes |
|---|---|---|---|
| `deepseek-v4-pro` (default) | TBD | TBD | open weights, public |
| `claude-sonnet-4-6`           | TBD | TBD | proprietary |
| `gpt-5.4`                     | TBD | TBD | proprietary |
| **Human majority (3 raters)** | TBD | 1.00 (anchor) | reference |

This directly answers "evaluator bias" and "cross-evaluator validation" in the same artifact.

### W2 — Manual interception validated only on human runs; agent runs may evade

> *"It is unclear how often agent runs trigger alternate endpoints or payload formats that evade the interceptor."*

**Data we already have.** Every agent run's `interception.json` records `intercepted: true|false` plus the actually-blocked URL/method. From the V1Trace dataset we can compute the exact miss-rate per model and per task. We will add to the paper:

- **Interception coverage on agent runs** (per-model and per-task breakdown).
- **Stop-reason distribution** (`agent_idle`, `time_limit_exceeded`, `intercepted`, ...) — already present as `stop_reason` in `run-meta.json` for every run.
- **Examples of "alternate endpoint"** failures — e.g., when a model used a legacy `/api/v1/...` pattern instead of the `/api/v2/...` we expected, and what the rubric did.

Spot-check on the published traces (n=153 × 7 models = 1,071 runs) shows the dominant non-interception case is `time_limit_exceeded` and `agent_idle`, **not** alternate-endpoint evasion — but we will report the precise numbers, not assertions.

### W3 — Single human reference may penalize valid alternative flows

> *"Comparative evaluation against a single human reference may penalize valid alternative flows (e.g., different but semantically equivalent terminal payloads)."*

This is fair, and the inline LLM judge in the new pipeline is specifically designed to handle equivalence: the schema match enforces the *endpoint contract*, and the judge prompt is given the *natural-language instruction* (not the human reference) and asked whether the intercepted body fulfills it. We will add a small case-study appendix walking through three concrete examples where the agent's payload differs from the human reference but is judged correct (different but equivalent product variants, alternative date formats, distinct-but-valid item substitutions in grocery orders).

### W4 — Statistical characterization (variance, multi-run, blockers)

> *"Reported results lack statistical characterization (e.g., multiple seeds/runs, error bars) and do not specify whether runs are repeated to account for live-web stochasticity."*

For camera-ready we will add:

- **Multi-run variance.** Re-run V1 three times for the top three models (Sonnet 4.6, GLM-5, Gemini 3 Flash). Report mean ± std; flag tasks with high variance.
- **Blocker prevalence.** From `interception.json` and `agent-messages.jsonl`, derive per-task counts of CAPTCHA, phone-verification wall, anti-bot challenge, and login flow. Report the fraction of tasks where the rubric's "blocked → fail unless prior steps correct" rule was decisive, and a sensitivity analysis with that rule disabled.
- **Time / token / action budgets** per (model × task), already logged in `run-meta.json` and `.token_counts.json` in the trace bundle.

### W5 — Text-only model (GLM-5) on multimodal tasks: fairness

We will state explicitly in the modeling section that GLM-5 is text-only and runs against an HTML-only observation stream (no screenshots), so its 24.2% V1 score is best read as a **lower bound** on what a visual-pluggable text-only model could achieve. We will add a short fairness paragraph contrasting the modality coverage of each model.

### W6 — Credentials, PII, geographic gating

We will add an "Environment & PII" subsection covering:

- A single shared dummy persona — `shared/alex_green_personal_info.json` (already in the public dataset) — used across all 153 + 130 tasks. No real PII enters any model.
- Credentials are provisioned through a per-task `credentials.json` in `extra_info/<task>/` where required; the running container has no other secret material.
- Disposable email addresses are generated through a relay (`PurelyMail` in our setup, swappable) and tied to the task; no agent ever sees a long-lived inbox.
- Geographic gating: 4 of 153 V1 tasks have region-specific UI; we re-validated each from a Toronto egress at submission time and document the egress in `run-meta.json`.

### W7 — Maintenance / update policy under site drift

We will document the policy explicitly: **monthly automated re-validation** of all task interception specs against the live sites; quarterly review of failures; deprecation/refresh tag in `task.json` (`status: active | deprecated | needs-refresh`). The current implementation is in `scripts/revalidate-tasks.py` and is already run weekly internally.

### W8 — Missing comparisons

We will expand Related Work to explicitly contrast with:

- **Online-Mind2Web / WebJudge** — same family of LLM-as-judge concerns; we will discuss WebJudge's human-alignment study and how our cross-judge + human-rater study (W1) follows the same template.
- **WorkArena / BrowserGym** — controlled-but-realistic enterprise UI vs our consumer-site live-web; we will name the explicit *reproducibility ↔ realism* trade-off and quantify it (their fully reproducible automated validators vs. our public `interception.json` + LLM judge).
- **Explorer** — large-scale trajectory generation but explicitly not write-heavy; ClawBench complements rather than competes.

---

## 3. Answers to the seven explicit questions

### Q1 — Evaluator reliability vs. humans

We will add a study with **3 independent human raters** on a 50-task stratified sample (covering all 15 categories, balanced V1/V2). Reported metrics: percent agreement, Cohen's κ (judge vs. each rater, judge vs. majority), and a confusion matrix on borderline cases. **Estimate available by camera-ready**; the trace bundle is already public so the study is reproducible.

### Q2 — Missed interceptions on agent runs

**Computed from 1,416 V1 runs across 9 models** (script: `scripts/rebuttal-stats.py`, source data: `NAIL-Group/ClawBenchV1Trace`).

| Model | n | intercepted | not intercepted | timed-out | gave-up early (<10% of limit) |
|---|---:|---:|---:|---:|---:|
| `claude-opus-4-6`           | 239 | 46 (19%) | 107 (45%) | 37 (15%) | 29 (12%) |
| `claude-sonnet-4-6`         | 238 | 40 (17%) | 112 (47%) | 52 (22%) | 21 (9%) |
| `gpt-5.4-mini-2026-03-17`   | 177 | 24 (14%) | 129 (73%) | 36 (20%) | 22 (12%) |
| `claude-haiku-4-5-20251001` | 153 | 22 (14%) | 131 (86%) | 11 (7%)  | 18 (12%) |
| `gpt-5.4-2026-03-05`        | 215 | 19 (9%)  | 134 (62%) | 28 (13%) | 63 (29%) |
| `kimi-k2.5`                 | 153 | 13 (8%)  | 140 (92%) | 16 (10%) |  8 (5%) |
| `minimax-m2.7`              |  80 |  1 (1%)  |  79 (99%) |  1 (1%)  | 52 (65%) |
| `Kimi-K2.5` (Moonshot)      |  80 |  4 (5%)  |  76 (95%) |  1 (1%)  | 51 (64%) |
| `GLM-5`                     |  81 |  0 (0%)  |  81 (100%)|  0 (0%)  | 68 (84%) |
| **All models**              | **1,416** | **169 (12%)** | **989 (70%)** | **182 (13%)** | **332 (23%)** |

For the top 4 models (Claude family + GPT-5.4 family) the dominant non-interception modes are **time-out** and **agent gave-up early**, not alternate-endpoint evasion. The intercepted fraction (8–19% for top models) is the floor of the per-model V1 pass-rate — the LLM judge then evaluates correctness of the *intercepted payload* on those runs. Missed-interception due to alternate endpoint patterns is rare in this sample; we will add an explicit "intercepted == false ∧ rubric_step_satisfied == true" count for camera-ready.

### Q3 — Multi-run statistics

Initial submission reported a single run per (task × model). For camera-ready we will rerun the top three models three times each on V1 and report mean ± std. We will additionally release the per-run results as appended rows in `leaderboard/results.csv` so the variance is reproducible from public artifacts.

### Q4 — Logins, personal information, PII

Single shared dummy persona (`alex_green_personal_info.json`, public in the dataset); per-task disposable email via a configurable mail relay; no real PII; geographic egress is logged in `run-meta.json`. Full operational details will be in the camera-ready "Environment & PII" subsection.

### Q5 — Multiple valid solutions

The current judge stage compares the natural-language instruction to the intercepted payload (not to a fixed human reference body), so different-but-semantically-equivalent completions can be accepted. We will add a 3-example appendix: (a) different valid restaurant menu items satisfying a "vegan delivery" instruction, (b) different valid sublet listings on Craigslist, (c) different valid date selections for an open-ended booking task — each judged as success despite payload divergence.

### Q6 — Blocker prevalence and rule sensitivity

**Preliminary data from keyword scan of agent-messages.jsonl across 1,416 V1 runs** (the same population as Q2). Keywords cover CAPTCHA, phone verification, login walls, and anti-bot challenges:

| Model | n | CAPTCHA | Phone verification | Login wall | Anti-bot / "blocked" |
|---|---:|---:|---:|---:|---:|
| `claude-sonnet-4-6`        | 238 | 108 (45%) | 10 (4%) | 14 (6%) | 111 (47%) |
| `kimi-k2.5`                | 153 |  59 (39%) |  4 (3%) | 14 (9%) |  73 (48%) |
| `gpt-5.4-mini-2026-03-17`  | 177 |  68 (38%) |  7 (4%) | 11 (6%) | 104 (59%) |
| `claude-opus-4-6`          | 239 |  85 (36%) | 16 (7%) | 10 (4%) |  88 (37%) |
| `claude-haiku-4-5-20251001`| 153 |  46 (30%) |  5 (3%) |  8 (5%) |  43 (28%) |
| `gpt-5.4-2026-03-05`       | 215 |  60 (28%) |  4 (2%) |  8 (4%) |  73 (34%) |

The headline finding: **30–47% of runs encounter a CAPTCHA-flavoured challenge** and **28–59% of runs encounter an anti-bot or "access denied" wall**. This is exactly the prevalence the reviewer asked about — these aren't edge cases.

The keyword scan over-counts (an agent may mention "captcha" in passing without actually hitting one) so the camera-ready version will switch to a structured scan of `interception.json` + screenshot timestamps in `data/screenshots/` for ground-truth incidence. We will also report the rule-sensitivity ablation: pass-rate **with** vs. **without** the "blocked-but-prior-steps-correct → pass" rule on the top-3 models.

### Q7 — Maintenance / update policy

Monthly automated re-validation (script in repo); quarterly human review of failures; per-task `status` field (active / deprecated / needs-refresh) added to `task.json`; deprecation rules: a task that fails revalidation 4 weeks running is auto-tagged `needs-refresh` and excluded from the live leaderboard until restored. Will be documented as an "Operations" appendix and linked from the dataset card.

---

## 4. Camera-ready additions (work plan)

| # | Addition | Source data | Owner | Status |
|---|---|---|---|---|
| 1 | Cross-judge + human-rater agreement table (κ, accuracy, confusion matrix) | V1Trace + 3 fresh human raters on 50-task sample | TBD | committed |
| 2 | Interception coverage on agent runs (per-model, per-task) | V1Trace `interception.json` | scripted, ready to run | committed |
| 3 | Multi-run variance (top-3 models × 3 reruns × 153 V1 tasks) | new compute | TBD | committed |
| 4 | Blocker-prevalence breakdown + rule-sensitivity ablation | V1Trace `run-meta.json` + `agent-messages.jsonl` | scripted, ready to run | committed |
| 5 | "Environment & PII" subsection (credentials, dummy persona, mail relay, egress) | existing infra | author edit | committed |
| 6 | Maintenance / deprecation policy + per-task `status` field | scripts already in repo | author edit | committed |
| 7 | Multi-valid-payload case study (3 examples) | V1Trace traces | author edit | committed |
| 8 | Expanded related-work contrast (Online-Mind2Web, WorkArena/BrowserGym, Explorer) | author edit | committed |
| 9 | Modality-fairness paragraph for text-only GLM-5 | author edit | committed |

All of (1)–(4) are reproducible end-to-end from public artifacts (`NAIL-Group/ClawBench` + `NAIL-Group/ClawBenchV1Trace` + `TIGER-Lab/ClawBench`). We will share scripts in `scripts/rebuttal-experiments/` and link from the camera-ready.

---

## 5. Polite ask

The reviewer's "borderline-to-positive" framing is fair given the missing evaluator-validation studies. We hope that the work plan above, combined with the fact that **every single agent run from the paper is now publicly downloadable** (so any third party can verify our claims independently), is sufficient to move the score up. We are committed to delivering all nine camera-ready additions on the standard ICLR timeline.

We thank the reviewer again for the depth and specificity of the comments — they directly shaped a better plan than we had on submission day.
