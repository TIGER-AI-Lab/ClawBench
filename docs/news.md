# News archive

The five most recent items live in the [README](../README.md#news). Everything else is here; the full engineering change history is in [`CHANGELOG.md`](../CHANGELOG.md).

## 2026

- **[2026.08.20]** — 🏆 Our paper has been accepted to [EMNLP 2026 Findings](https://2026.emnlp.org/).
- **[2026.08.16]** — Released **[RewardHarness](https://github.com/TIGER-AI-Lab/RewardHarness)**, our self-evolving agentic reward framework: 47.4% on EditReward-Bench from just 100 preference demos, with no reward-model training. [Details →](https://arxiv.org/abs/2605.08703)
- **[2026.08.03]** — Added [Browserbase](https://www.browserbase.com) as a remote browser runtime for ClawBench. [Details →](browser-runtimes.md)
- **[2026.07.30]** — v0.8.0 released: Gemini-as-judge, random-click baseline harness, EdgeBench/SForge adapter, remote-browser CDP support. [Details →](../CHANGELOG.md)
- **[2026.07.25]** — 🏆 Our paper has been accepted by [COLM 2026 WAB](https://www.aiagentbehavior.com/).
- **[2026.06.22]** — v0.7.0 released: Harbor-adapter task export; action recording moved into the CDP server. [Details →](../CHANGELOG.md)
- **[2026.05.20]** — V2 is now the default corpus + lenient judge + 6 first-class harnesses. [Details →](v1-vs-v2.md)
- **[2026.05.16]** — Added Claw-Eval suite: 19 browser-research tasks with final-answer submission. [Details →](../test-cases/claw-eval/)
- **[2026.05.12]** — Canonical leaderboard moved to the TIGER-Lab/ClawBench Gradio Space. [Details →](https://huggingface.co/spaces/TIGER-Lab/ClawBench)
- **[2026.05.11]** — V2 leaderboard ships: top so far `glm-5.1 / hermes` at 18.5% reward / 48.5% intercepted. [Details →](https://claw-bench.com/leaderboard)
- **[2026.05.09]** — Inline LLM judge added as a second scoring stage; runs now auto-produce pass/fail. [Details →](../eval/scoring.md)
- **[2026.05.09]** — `clawbench-eval` published to PyPI for one-command install. [Details →](https://pypi.org/project/clawbench-eval/)
- **[2026.05.09]** — Released ClawBenchV1Trace: full 5-layer execution trace for every V1 run. [Details →](https://huggingface.co/datasets/NAIL-Group/ClawBenchV1Trace)
- **[2026.04.25]** — Added support for the hermes harness. [Details →](../src/clawbench/runtime/harnesses/hermes/)
- **[2026.04.18]** — Added support for the browser-use harness. [Details →](../src/clawbench/runtime/harnesses/browser-use/)
- **[2026.04.11]** — Paper released on arXiv (2604.08523); #3 HuggingFace Paper of the Day. [Details →](https://arxiv.org/abs/2604.08523)
