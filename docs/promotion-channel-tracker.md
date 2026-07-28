# ClawBench Outreach Submission Tracker

Last audited: 2026-07-28

This file tracks outreach that is not a direct pull request. It separates GitHub proposal issues from genuinely non-GitHub submissions so the two goals are not conflated. Existing third-party coverage does not count as a new submission.

## Counts

| Scope | Submitted |
|---|---:|
| GitHub issue-first proposals | 2 |
| ClawBench discovery-infrastructure issues | 2 |
| Official benchmark-registration PRs | 1 |
| ClawBench metadata PRs | 1 |
| Non-GitHub destinations audited | 75 |
| Non-GitHub submissions or posts | 10 |
| Non-GitHub attempts without a verifiable receipt | 3 |
| Audited non-GitHub destinations pending a supported submit path | 11 |
| Existing non-GitHub coverage pages, not counted as new | 11 |

## GitHub Issue-First Proposals

| # | Destination | Submission | Purpose | Status |
|---:|---|---|---|---|
| 1 | `vnageshwaran-de/Awesome-LLM-Agent-Evaluation` | [Issue #2 — New Benchmark: ClawBench](https://github.com/vnageshwaran-de/Awesome-LLM-Agent-Evaluation/issues/2) | Supplies eligibility evidence, taxonomy codes, metrics, limitations, primary sources, and honest preprint status before the required CSV PR | Open |
| 2 | `wgwang/awesome-LLM-benchmarks` | [Issue #7 — Add ClawBench benchmark metadata](https://github.com/wgwang/awesome-LLM-benchmarks/issues/7) | 167-star benchmark list explicitly requests new benchmark leads through Issues; provides canonical code, project, paper, current 283-task/163-site scope, categories, and evidence layers | Open |
| 3 | `Dan-Cleary/benchdirectory` | [Issue #10 — Bench submission](https://github.com/Dan-Cleary/benchdirectory/issues/10) | Public benchmark-directory intake; maintainer-disclosed submission supplies canonical code, paper, project, task/site scope, and evidence-layer description | Open |

## Discovery Infrastructure

| # | Destination | Submission | Purpose | Status |
|---:|---|---|---|---|
| 1 | `TIGER-AI-Lab/ClawBench` | [Issue #264 — Keep llms.txt synchronized](https://github.com/TIGER-AI-Lab/ClawBench/issues/264) | Documents stale machine-readable corpus, leaderboard, route, dataset, and citation fields and proposes generation from canonical live sources for connected-agent discovery | Open |
| 2 | `huggingface/huggingface.js` | [PR #2315 — Add ClawBench evaluation framework](https://github.com/huggingface/huggingface.js/pull/2315) | Registers `clawbench-eval` in Hugging Face's supported evaluation-framework enum, removing one blocker from the existing dataset's native Benchmark and leaderboard registration path | Open |
| 3 | `TIGER-AI-Lab/ClawBench` | [Issue #265 — Complete native Hugging Face Benchmark registration](https://github.com/TIGER-AI-Lab/ClawBench/issues/265) | Defines the remaining config, task-ID, canonical-mode, validation, allow-list, and sourced-result work needed after framework registration | Open |
| 4 | `TIGER-AI-Lab/ClawBench` | [PR #266 — Refresh citation metadata for v0.7.0](https://github.com/TIGER-AI-Lab/ClawBench/pull/266) | Corrects the canonical code repository, records the current release metadata, and exposes the successful Software Heritage snapshot through schema-valid `CITATION.cff` metadata | Open |

## Non-GitHub Submissions

| # | Destination | Submission | Purpose | Status |
|---:|---|---|---|---|
| 1 | Software Heritage | [Save Code Now request #2400187](https://archive.softwareheritage.org/api/1/origin/save/2400187/) | Requests preservation and machine-indexing of the canonical ClawBench Git repository in the universal software source archive | Succeeded; full snapshot `swh:1:snp:4baa3fe53cbce2b1abfae44a21170ab079e351a3` |
| 2 | Software Heritage | [Save Code Now request #2400196](https://archive.softwareheritage.org/api/1/origin/save/2400196/) | Requests a separate long-term snapshot of the public `TIGER-Lab/ClawBench` Hugging Face dataset Git repository and its benchmark metadata | Succeeded; full snapshot `swh:1:snp:88c729f68cc08883339e0baed8f6c68f1949cf1c` |
| 3 | Hugging Face Dataset | [Discussion #2 — ClawBench release and benchmark metadata](https://huggingface.co/datasets/TIGER-Lab/ClawBench/discussions/2) | Maintainer-disclosed release note with canonical paper, repository, project/leaderboard links, current V1+V2 scope, interception, and trace/judge methodology | Public discussion posted |
| 4 | Hugging Face Space | [Discussion #1 — Reproducing ClawBench V2 scores](https://huggingface.co/spaces/TIGER-Lab/ClawBench/discussions/1) | Maintainer-disclosed technical note on V2 corpus identification, interception plus judge reporting, exact harness/commit metadata, and independent reruns; informational only and does not alter leaderboard rows | Public discussion posted |
| 5 | Hugging Face Dataset | [Discussion #1 — Trace schema and V2 reproducibility](https://huggingface.co/datasets/TIGER-Lab/ClawBenchV2Trace/discussions/1) | Maintainer-disclosed technical note documenting the published V2 trace bundle fields and the metadata needed for independent replay; does not add or alter benchmark results | Public discussion posted |
| 6 | Software Heritage | [Save Code Now request #2401070](https://archive.softwareheritage.org/api/1/origin/save/2401070/) | Requests independent archival and machine indexing of the public `TIGER-Lab/ClawBenchV2Trace` Git repository, a distinct origin from the previously archived code and task-data repositories | Succeeded; full snapshot `swh:1:snp:e61d647d5dd310da3001bf814bfee29ecba56c99` |
| 7 | CodeSOTA | [Submit a paper, benchmark, or correction](https://www.codesota.com/submit) | Maintainer-disclosed request to track ClawBench in the agent benchmark/evaluation registry, with canonical paper, code, project links, and factual task/site/evidence scope | Submitted 2026-07-28 22:24 CST; on-site confirmation: “Got it. A real human reads every submission — expect a reply within 48 hours.” |
| 8 | clawRxiv | [Evidence brief 2607.02850](https://clawrxiv.io/abs/2607.02850) | Transparent AI-agent research-archive brief linking ClawBench's canonical paper, repository, project page, and related benchmarks; explicitly marked AI-generated and non-authoritative, with no author impersonation or endorsement claim | Public record created 2026-07-28; API receipt `id=2850`, `paper_id=2607.02850` |
| 9 | intuitivepapers.ai | [Public explanation queue](https://intuitivepapers.ai/queue/) | Requested an explainer for arXiv:2604.08523 through the public no-account queue; the request references the canonical paper only and does not claim that an explainer is already published | API receipt `slug=arxiv-2604-08523`, confirmed in the public queue |
| 10 | Lukta | [Project proposal](https://www.lukta.ai/sponsors) | Maintainer-disclosed proposal for an agent challenge around running the published ClawBench corpus and submitting reproducible traces and scores; uses factual scope and does not claim sponsorship or certification | Submitted 2026-07-28; on-site receipt: “Thanks — we've saved your project proposal.” Saved for Lukta review; not public and no challenge was created automatically |

## Attempts Not Counted

| Destination | Attempt | Result |
|---|---|---|
| Agent Almanac | Official `POST /api/v1/entries` at 2026-07-27 00:46:57 CST, with a maintainer-disclosed ClawBench benchmark record and no email, key-person, or credential fields | Timed out after 30 seconds with zero response bytes; no ID, URL, or status was returned. Outcome is unknown, so it is not counted and will not be retried. |
| OpenAlex | Official duplicate-work correction form for `W7153165172` (DOI-backed canonical record) and `W7153669743` (duplicate arXiv record), using the maintainer email and the official merge path | The multi-step form reached the merge branch and fields were bound, but no trustworthy confirmation receipt was captured. It is not counted as a submission. |
| ListAi.cc | [Submit a tool](https://listai.cc/submit) was accepted by the form, but subsequent audit found no public ClawBench listing and the directory is specifically for AI tools rather than research benchmarks | Removed from the valid count to avoid miscategorizing ClawBench; no public publication was verified. |
| Latent Scholar | Public “From idea to article” intake was audited, but it requires a verified `.edu` email; no submission was sent because the available maintainer email does not satisfy that requirement | Not counted; no truthful access path was available. |

## Audited Pending Destinations

| Destination | Reason pending |
|---|---|
| Benchmark Registry | Its public missing-record form was audited and accepts an optional-email submission, but the supported browser-control entrypoint is unavailable in this session. No fields were sent. |
| SupraBench | The benchmark and 33.3% Claude Sonnet 4.6 result are format-compatible, but submission requires Google sign-in. No fields were sent. |
| MarkTechPost | Its research-summary form fits ClawBench and a maintainer-disclosed payload is prepared, but the submission surface is a Google Form and browser control is unavailable. |
| The Rundown | Its free Recommend a Tool form fits the project, but submission requires a resource-thumbnail upload; the browser upload flow did not expose a usable file chooser, so no form was counted. |
| AI Tool Lab | The public form is currently paused; the page directs submitters to email for urgent requests. No email was sent and no submission was counted. |
| toollist.ai | The directory requires account creation and a paid plan (starting at $29); no purchase or account creation was authorized, so no submission was counted. |
| Benchlist | Public intake is for AI services and replayable score submissions, not benchmark registration; ClawBench is a benchmark, so no miscategorized listing was sent. |
| LocalAlternative | Submission requires a local-first/self-hosted AI tool; ClawBench is a web-agent benchmark rather than a local AI application, so no submission was sent. |
| MyFreeAISource | Submission is for consumer AI tools with pricing/privacy/terms metadata; ClawBench is a research benchmark, so no miscategorized submission was sent. |
| AgentPub | Public paper publishing requires account creation and email verification; no account was created or submission sent without verified identity access. |
| Stanford BetterBench | Its public new-benchmark form accepts directory additions, but requires a truthful completed 46-criteria assessment Google Doc; no such assessment exists yet, so no fields were sent. |

## Existing Coverage

These placements predate this outreach counter and are recorded as evidence, not as new submissions.

| Destination | Evidence |
|---|---|
| arXiv | [Paper record](https://arxiv.org/abs/2604.08523) |
| Hugging Face Daily Papers | [#3 Paper of the Day](https://huggingface.co/papers/2604.08523) |
| CatalyzeX | [Paper and code record](https://www.catalyzex.com/paper/clawbench-can-ai-agents-complete-everyday) |
| alphaXiv | [Paper discussion page](https://www.alphaxiv.org/abs/2604.08523) |
| SciRate | [Paper record](https://scirate.com/arxiv/2604.08523) |
| Emergent Mind | [Paper summary](https://www.emergentmind.com/papers/2604.08523) |
| Papers Cool | [Paper record](https://papers.cool/arxiv/2604.08523) |
| arXivLens | [Paper analysis page](https://arxivlens.com/PaperView/Details/clawbench-can-ai-agents-complete-everyday-online-tasks-8483-34ae9a7b) |
| DBLP | [CoRR record](https://dblp.org/rec/journals/corr/abs-2604-08523) |
| ResearchGate | [Publication record](https://www.researchgate.net/publication/403683295_ClawBench_Can_AI_Agents_Complete_Everyday_Online_Tasks) |
| UniPat AI | [Benchmark page](https://unipat.ai/benchmarks/ClawBench) |

## Submission Rules

- Disclose that the submitter helps maintain ClawBench.
- Use only destinations whose audience and rules match agent benchmarks, evaluation, browser or computer-use agents, or AI research.
- Do not impersonate independent users, manufacture endorsements, or post repetitive comments.
- Do not count discovery, automatic indexing, an unsubmitted draft, or pre-existing coverage.
- Record a public URL or platform receipt for every counted submission.
