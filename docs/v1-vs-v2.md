# ClawBench V1 → V2: What Changed

Side-by-side comparison of the V1 corpus (the original 2026-04 release) and the V2 corpus (the new default). Numbers in the tables below were verified against the corpus files, the judge code, the website, and the public HF datasets — see "Provenance" at the bottom of each section for the exact files we read.

The short version: **V2 is intercept-only, judge-LLM-only, and self-contained — anyone can reproduce a leaderboard row with `clawbench-reproduce --model deepseek-v4-flash` and one OpenRouter key.**

---

## 1. Task corpus

| Axis | V1 | V2 | Δ |
|---|---:|---:|---|
| Tasks (`task.json` count) | 153 | 130 | -23 |
| Unique sites (`metadata.sites_involved`) | 144 | 64 | -80 |
| Sites in both | 44 | 44 | — |
| Tasks reused from V1 (by ID) | — | 51 | 33% of V1 carried over |
| New V2-only tasks | — | 79 | 60% of V2 is fresh |
| Top metaclass | daily-life (21) | daily-life (12) | smoothed |
| Categories | 15 | 19 | +4 (charity, civic-engagement, fitness …) |

Provenance: `test-cases/v1/**/task.json`, `test-cases/v2/**/task.json`, `task.schema.json`.

---

## 2. Safety design (the headline V2 change)

| Safety axis | V1 | V2 | Result |
|---|---|---|---|
| `eval_schema` filled (interceptable) | 70/153 = **46%** | 130/130 = **100%** | V2 makes interception mandatory |
| Tasks that submit a payment / checkout | 29/153 = 19% | 7/130 = 5% | -76% |
| Job-application tasks | 14 | 7 | halved |
| Newsletter / account signups | 14 | 10 | reduced |
| Irreversible-action coverage | 28+ tasks with placeholder schema (could slip past interceptor) | 0 placeholder schemas | **V2 closes the gap** |
| Real-account requirement | none | none | unchanged |
| Personal info | disposable email + dummy `alex_green` profile | same (mailinator pool planned) | unchanged |

V1's "agentic evaluator" model meant tasks without a regex were judged after the fact from the human-reference trace — fine for offline analysis, but the agent could in principle submit a real request before the eval ran. V2 requires every task to declare a URL+method pattern up front, so the interceptor blocks the request *before* it leaves the container.

Provenance: `eval/agentic_eval.md` (V1 nine-rule rubric); `docs/scoring.md`; sample `task.json` files from both corpora.

---

## 3. Evaluation rubric + judge

| Axis | V1 | V2 |
|---|---|---|
| Judge | Claude Code subagent + paired human-reference trace | LLM-only on intercepted HTTP body |
| Inputs | 5-layer trace (actions + requests + screenshots + recording + agent-messages) + human ref ≈ 100 MB | instruction + intercepted URL/method/body, truncated to ≤6 KB |
| Rubric | 9 semantic rules (payment must be attempted, phone wall = PASS, CAPTCHA must attempt, etc.) | Lenient default: *"no explicit contradiction → match"*. Strict opt-in: *"ambiguous → mismatch"* |
| Cost per batch | 16 parallel Claude Code subagents × ~$0.30/task ≈ $50+ | 1 judge call/task × ~$0.01 ≈ $1 |
| Requires Claude Code installed? | yes | no |
| Requires human-reference trace? | yes | no |
| Per-task artifact | `{model}-eval-results.{csv,json}` (per-batch) | `judge.json` (strict) / `judge_llm.json` (lenient) per task + `rescore-summary.json` per batch + `eval_results/<batch>/{per_task.csv,summary.json}` |

V2's lenient rubric is what the public leaderboard uses; the strict rubric is preserved for ablation. Both are publishable Python modules (`src/clawbench/runner/judge.py`, `src/clawbench/runner/judge_llm.py`).

Provenance: `eval/agentic_eval.md`, `src/clawbench/runner/judge.py`, `src/clawbench/runner/judge_llm.py`, `src/clawbench/eval/rescore.py`.

---

## 4. Interceptor / URL-pattern specificity

| Metric | V1 | V2 |
|---|---:|---:|
| `eval_schema` filled | 46% (70/153) | 100% (130/130) |
| Placeholder reliance | 54% (83/153) | 0% |
| HTTP methods covered | POST 100% | POST 92% / GET 8% / PUT <1% |
| Average pattern length | 53 chars | 40 chars |
| Patterns > 60 chars (complex) | 44% of declared patterns | 5% |

V2 patterns are shorter and more diverse because the corpus now covers more "navigate-then-confirm" tasks (GET-able resource fetches) rather than V1's near-uniform "POST a form" pattern. None of the sampled patterns matched known third-party telemetry endpoints (no false-positive intercepts in our spot check).

Sample V2 patterns:
- `myrecipes\.com/api/v\d+/review/save`
- `change\.org/api-proxy/graphql.*op=GenerateAiDraft|.*op=CreatePetition`
- `ravelry\.com/discuss/[^/]+/topics`

Provenance: sampled 20 `task.json` files per corpus.

---

## 5. Identity / personal info

| Aspect | V1 (current) | V2 (current + planned) |
|---|---|---|
| Email service | PurelyMail (`clawbench.cc` domain, paid Anthropic account) | same today; mailinator + 100-name pool planned (Task #14) |
| Test personae | single (`alex_green`) | same today; 100-name pool planned |
| PDF resume | hardcoded name + companies + degrees, runtime email injection | same today; placeholder-only template planned |
| Teacher / referee names | hardcoded in personal-info JSON | dynamic generator planned |
| Setup cost | requires Anthropic PurelyMail account | shared mailinator.com domain (~$900/yr; reproducible by anyone with the credential) |

Identity is the one axis where V1 ≈ V2 today; the V2-plan upgrades land in a follow-up PR once the mailinator domain is procured.

Provenance: `src/clawbench/runtime/shared/alex_green_personal_info.json`, `src/clawbench/utils/resume_template.json`, `src/clawbench/runner/run.py` (PurelyMail integration), `docs/superpowers/specs/2026-05-09-claw-bench-v2-update-design.md` (V2 identity plan).

---

## 6. Public surfaces

| Surface | V1 mentioned | V2 mentioned | V2 default? |
|---|---|---|---|
| arXiv `2604.08523` | yes (153 tasks, 144 sites) | no | n/a (paper pre-dates V2) |
| GitHub README | yes | yes | yes (6-tab leaderboard, V2 Hermes first; 2026-05-20 news entry headlines V2) |
| claw-bench.com | yes (V1 153) | yes (V2 130) | yes (hero strapline = V2; default leaderboard tab = V2 Hermes) |
| HF `NAIL-Group/ClawBench` (task definitions) | yes | yes | tie (both shown) |
| HF `TIGER-Lab/ClawBenchV2Trace` | for context | primary | yes (V2-only repo) |
| HF Space `TIGER-Lab/ClawBench` leaderboard | yes (V1 traces link) | yes (V2 traces link) | yes (`gr.Radio(value="v2")` in `app.py`) |

Only the arXiv abstract still describes V1 alone — that requires a paper v2 revision, which is a separate task from this PR.

---

## 7. Saving the eval config per run (small reliability improvement)

Each `judge.json` / `judge_llm.json` written by `clawbench-rescore` already records the run's effective config — the model that judged it, the rubric used, the rubric prompt (via the file name), and the raw judge reply for audit. The per-batch `rescore-summary.json` re-states these at batch level. Concretely, every V2 judge file contains:

```json
{
  "match": true,
  "reason": "…",
  "judge_model": "deepseek-v4-pro",
  "rubric": "lenient",
  "raw": "{\"match\": true, …}"
}
```

The `eval_results/<batch>/summary.json` aggregates: `judge_model`, `rubrics`, and per-rubric percentages formatted as `X.X%`. Anyone re-running the same `clawbench-rescore` command against the same `TIGER-Lab/ClawBenchV2Trace` snapshot can compare their numbers to ours field-by-field. This is the spec for "every eval's config is saved" — V2 already complies; V1 did not (V1's `{model}-eval-results.csv` only stored verdict + brief reason).

---

## TL;DR

V2 takes the parts of V1 that depended on human-curated artefacts (human-reference traces, Claude Code subagents, partially-filled regex schemas) and replaces them with three machine-checkable inputs: a complete `eval_schema`, a stateless LLM judge, and a per-run config receipt. The result is a benchmark that anyone can install, run, and audit end-to-end without infrastructure that only the original team has — which is the actual "release V2" claim.
