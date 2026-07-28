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
| Non-GitHub destinations audited | 99 |
| Non-GitHub submissions or posts | 12 |
| Non-GitHub attempts without a verifiable receipt | 3 |
| Audited non-GitHub destinations pending a supported submit path | 28 |
| Existing non-GitHub coverage pages, not counted as new | 17 |

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
| 11 | Open Source Startups | [ClawBench project listing](https://www.opensourcestartups.com/project/clawbench) | Maintainer-disclosed open-source project submission in the directory's AI & ML category, using the canonical GitHub repository and project page; description identifies ClawBench as a benchmark framework rather than a hosted product | API receipt `id=cms4s5j1w002bwavd4ttwic44`, status `pending`; public project URL resolves HTTP 200 |
| 12 | ForgeIndex | [ForgeIndex submission form](https://docs.google.com/forms/d/e/1FAIpQLSeB39gVawXep0o0WRjck8ESaJ96ZLloUIgqspMfjEYOcd-IDg/viewform) | Factual project submission to the open-source AI index's “LLM Safety & Evaluations” / local AI research audience, with canonical GitHub, Hugging Face, and project links | Submitted 2026-07-28; Google Forms receipt: “Your response has been recorded.” No public listing claimed yet |

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
| ClawdReview | The public API accepts AI-agent reviews of arXiv papers, but requires registering an agent and obtaining an API key; no account or credentials were created without explicit account-creation authorization. |
| PaperLake | The service is in private alpha and paper ingestion requires membership/contributor access to an isolated lake; its public request-access form does not publish a paper entry, so no request was sent. |
| Openbenchmarks for Agents | The public hub publishes its own verified benchmark suites; its only listed contact path is for corrections to already benchmarked results, with no public benchmark-submission form. |
| Bench Protocol | The service is pre-beta; benchmark proposals and harness submission are announced for waitlist members, while the public forms only collect email access requests and do not publish a proposal. |
| OASB | The open agent security benchmark welcomes scenario and control proposals, but its documented contribution path is GitHub issue/PR rather than a non-GitHub publication surface. |
| Exgentic Open Agent Leaderboard | The public site advertises benchmark integration through its unified protocol, but the available contribution route requires the platform/GitHub workflow; no standalone public ClawBench submission form was found. |
| Semantic Scholar | The ClawBench arXiv record is automatically indexed; adding or correcting author-page metadata requires a logged-in author claim, so no account action was taken. |
| Archivara | Its research-archive submission is relevant but requires an account and automatically names that account as first author; no account was created and no authorship was misrepresented. |
| Public Interest AI Project Map | The HIIG survey publishes submitted project metadata under CC BY 4.0 and requires detailed location, team, gender-ratio, funding, and project-use answers; no submission was sent because those fields cannot be completed truthfully from the authorized project facts. |
| OSS AI Hub | Its public form explicitly accepts open-source AI tools, frameworks, agents, and evals, making ClawBench semantically relevant; however, the form's Supabase submission endpoint did not resolve during audit, so no data was sent and no receipt was counted. |
| PyTorch Foundation | The Foundation explicitly welcomes open-source AI projects, but its “Host Your Project” submission route is a GitHub contribution workflow and would imply a substantial hosted-project relationship; no non-GitHub submission was sent. |
| Eclipse Foundation | Its project-proposal process is for moving a project into Foundation governance, including community review and IP/provenance review; this is materially broader than a directory listing, so no proposal was submitted without explicit governance authorization. |
| Researka | Its public intake is for agent builders submitting research-agent benchmark artifacts or manuscripts; ClawBench is the benchmark framework, not an evaluated research agent, so no mismatched artifact was submitted. |
| Snorkel AI Open Benchmarks Grant | The program is a grant application with selection and collaboration commitments, not a directory listing; no funding proposal was submitted without explicit authorization for grant commitments. |
| AgenticDataBench | Its public submission instructions accept agent prediction files or code archives by email for evaluation, not benchmark/framework listings; ClawBench is the benchmark framework rather than an evaluated agent result, so no mismatched email submission was sent. |
| Frontier AI Cybersecurity Observatory | The public benchmark form targets a narrowly scoped cybersecurity-capability leaderboard and requests cybersecurity benchmark results/metadata; ClawBench is a general real-world web-agent benchmark, so no off-topic entry was submitted. |
| Codabench | Codabench supports organizing full benchmark competitions, but its public path requires creating and operating a competition with datasets, scoring code, and an account; it is not a lightweight project-listing submission, so no competition was created. |
| BenchHub | BenchHub publishes user-created datasets and leaderboards, but its workflow requires an authenticated workspace and uploading benchmark assets/results; no account or leaderboard was created without explicit hosting authorization. |
| OECD.AI Catalogue of Tools & Metrics | The OECD.AI catalogue has a semantically relevant public submission form for AI tools and metrics, but it requires reCAPTCHA, email, and agreement to submission terms; no browser-verifiable receipt was obtained, so no submission was counted. |
| AgentBench.app | Its public submit flow accepts an AgentBench `results.json` leaderboard result plus an agent repository URL, not a benchmark/project listing; no ClawBench result was submitted. |
| Benchlist.ai | Its submit flow is for verified AI-service runs and attested scores, not adding an external benchmark to a catalog; no fabricated run or score was sent. |
| AgenticDataBench | Its documented route accepts prediction `.jsonl` files or executable agent archives for evaluation, not benchmark-framework listings; no mismatched artifact was submitted. |
| Researka | Its submission route requires a registered agent identifier and manuscript/experiment artifact; ClawBench is a benchmark framework, so no off-scope submission was made. |
| PaperScore | Its external-paper suggestion route is relevant to ClawBench's published paper, but the site requires account registration before submission; no account was created and no unverified receipt was counted. |

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
| EthicalML agentic engineering resources | [Benchmarks & Leaderboards section](https://github.com/EthicalML/awesome-agentic-engineering-resources#benchmarks) — current README contains two ClawBench entries; this is pre-existing coverage and is not counted as a new submission. |
| REAL-Lab-NU Awesome OpenClaw Papers | [Benchmark table](https://github.com/REAL-Lab-NU/Awesome-OpenClaw-Papers#benchmarks) — lists ClawBench-153 as a production-web benchmark; pre-existing coverage, not a new submission. |
| shuolucs Awesome OpenClaw Research | [Research table](https://github.com/shuolucs/Awesome-OpenClaw-Research#papers) — lists “ClawBench: Can AI Agents Complete Everyday Online Tasks?” with the arXiv link; pre-existing coverage, not a new submission. |
| OSU-NLP-Group GUI-Agents-Paper-List | [Generated GUI-agent paper list](https://github.com/OSU-NLP-Group/GUI-Agents-Paper-List#browse-by-keyword) — includes the ClawBench paper with Web, benchmark, and realistic-website tags; pre-existing coverage, not a new submission. |
| Jenqyang Awesome-AI-Agents | [Benchmark/Evaluator section](https://github.com/Jenqyang/Awesome-AI-Agents#benchmarkevaluator) — includes ClawBench as a browser-agent benchmark; pre-existing coverage, not a new submission. |
| Arnon-hs open-source index | [AI/ML project record](https://github.com/Arnon-hs/open-source/blob/main/aiml/reacher-z-clawbench.md) — indexes the canonical repository with scope, topics, and benchmark summary; pre-existing coverage, not a new submission. |

## Submission Rules

- Disclose that the submitter helps maintain ClawBench.
- Use only destinations whose audience and rules match agent benchmarks, evaluation, browser or computer-use agents, or AI research.
- Do not impersonate independent users, manufacture endorsements, or post repetitive comments.
- Do not count discovery, automatic indexing, an unsubmitted draft, or pre-existing coverage.
- Record a public URL or platform receipt for every counted submission.
