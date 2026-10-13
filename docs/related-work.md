# How ClawBench compares

[← ClawBench](../README.md) · [中文](related-work.zh-CN.md)

## How ClawBench compares

| Benchmark                                                           | Domain               | Environment               | Task count | ClawBench difference                                                         |
| ------------------------------------------------------------------- | -------------------- | ------------------------- | ---------- | ---------------------------------------------------------------------------- |
| [WebArena](https://webarena.dev)                                    | Synthetic web apps   | Self-hosted replicas      | 812        | Live consumer sites, not admin UIs on hosted replicas                        |
| [GAIA](https://huggingface.co/datasets/gaia-benchmark/GAIA)         | General assistants   | Closed-book text + tools  | 466        | Browser-centric; end-to-end task execution                                   |
| [SWE-bench](https://www.swebench.com)                               | Software engineering | GitHub repos              | 2,294      | Non-code; everyday consumer workflows                                        |
| [BrowserGym](https://github.com/ServiceNow/BrowserGym)              | Web agents           | Headless sandbox          | —          | Cloud-parity; records real user journeys                                     |
| [Mind2Web](https://github.com/OSU-NLP-Group/Mind2Web)               | Web navigation       | Static traces             | 2,350      | Dynamic live websites, not replayed traces                                   |
| [Online-Mind2Web](https://github.com/OSU-NLP-Group/Online-Mind2Web) | Live web navigation  | Real websites             | 300        | 4× more tasks (V1+V2: 281 vs 300 — comparable), with full 5-layer recordings |
| [VisualWebArena](https://jykoh.com/vwa)                             | Visual web tasks     | Self-hosted (3 sites)     | 910        | Real websites with full visual layer (vs 3 hosted apps)                      |
| [WebVoyager](https://github.com/MinorJerry/WebVoyager)              | Real-website nav     | Real websites (15)        | 643        | Interception-graded vs LLM-judge-only, 143 sites covered                     |
| [TheAgentCompany](https://the-agent-company.com)                    | Office workflows     | Self-hosted (6 platforms) | 175        | Consumer everyday tasks instead of enterprise sandbox                        |

ClawBench's niche: **live consumer websites, everyday tasks, end-to-end recording**. If you want a controlled sandbox or replayed traces, the projects above are excellent. If you want to know whether your agent can actually order food or book a flight *today*, this is the benchmark for that.
