<p align="center">
  <a href="https://github.com/TIGER-AI-Lab/ClawBench">
    <picture>
      <source media="(prefers-color-scheme: dark)" srcset="assets/clawbench-logo-dark.svg">
      <img src="assets/clawbench-logo.svg" alt="ClawBench" width="500">
    </picture>
  </a>
</p>

<h1 align="center">Can AI agents complete everyday online tasks?</h1>

<p align="center">An open benchmark for browser agents, from booking travel to managing email.<br/>Real websites &nbsp;&middot;&nbsp; Full execution traces &nbsp;&middot;&nbsp; End-to-end task evaluation</p>

<p align="center">
  <a href="#quick-start"><strong>Get started →</strong></a> &nbsp;&middot;&nbsp;
  <a href="https://huggingface.co/spaces/TIGER-Lab/ClawBench">Leaderboard</a> &nbsp;&middot;&nbsp;
  <a href="https://arxiv.org/abs/2604.08523">Paper</a> &nbsp;&middot;&nbsp;
  <a href="https://claw-bench.com">Website</a> &nbsp;&middot;&nbsp;
  <a href="https://huggingface.co/datasets/NAIL-Group/ClawBench">Data</a> &nbsp;&middot;&nbsp;
  <a href="docs/README.zh-CN.md">中文</a>
</p>

<p align="center">
  <a href="https://2026.emnlp.org/"><img alt="EMNLP 2026 Findings" src="https://img.shields.io/badge/EMNLP_2026-Findings-B84A34?style=flat-square&labelColor=252A34"></a>
  <a href="https://pypi.org/project/clawbench-eval/"><img alt="PyPI version" src="https://img.shields.io/pypi/v/clawbench-eval?style=flat-square&logo=pypi&color=49515F&labelColor=252A34&logoColor=white"></a>
  <a href="https://github.com/TIGER-AI-Lab/ClawBench"><img alt="GitHub stars" src="https://img.shields.io/github/stars/TIGER-AI-Lab/ClawBench?style=flat-square&logo=github&color=49515F&labelColor=252A34&cacheSeconds=300"></a>
</p>

<table align="center">
<tr>
<td width="180" align="center"><strong>281</strong><br/><sub>Everyday tasks</sub></td>
<td width="180" align="center"><strong>163</strong><br/><sub>Live websites</sub></td>
<td width="180" align="center"><strong>15</strong><br/><sub>Life categories</sub></td>
</tr>
</table>

<a id="demo"></a>

## A real task, end to end

Claude Opus 4.7 / Hermes answers the first algebra practice question on Khan Academy. ClawBench captures the submission request; the published judge record reports `match: true`.

<p align="center">
  <a href="docs/demo.md">
    <picture>
      <source media="(prefers-reduced-motion: reduce)" srcset="assets/demo/task-1122-poster.png">
      <img src="assets/demo/task-1122.gif" width="840" alt="Real Khan Academy run: select an answer, click Check, capture the POST request, and inspect the saved judge match.">
    </picture>
  </a>
</p>

<sub>15.5-second edit · browser excerpt at 2× speed · evidence panels from saved JSON · [Pauseable MP4](assets/demo/task-1122.mp4) · [Full recording, verdict, and provenance](docs/demo.md)</sub>

<a id="results"></a>

## What it measures

ClawBench evaluates browser agents on **live websites**, with **five layers of recorded evidence**: video, screenshots, HTTP traffic, browser actions, and agent messages.

| Stage | Question | Evidence |
| --- | --- | --- |
| **1. Interception** | Did the agent reach the task's configured final request? | Captured URL, method, and payload |
| **2. LLM judge** | Does that request fulfill the task instruction? | Judge verdict and reason |

Compare models using the same **corpus, harness, and rubric** on the **[live leaderboard](https://huggingface.co/spaces/TIGER-Lab/ClawBench)**. The [paper](https://arxiv.org/abs/2604.08523) describes the methodology; [scoring rules](eval/scoring.md), [historical result tables](docs/results.md), and [reproduction instructions](docs/reproduce.md) make the evidence inspectable.

| Corpus | Coverage | Use |
| --- | --- | --- |
| **V2** | 129 tasks · 63 live sites | Current default corpus |
| **V1** | 152 tasks · 143 live sites | Original task collection |
| **V1-Lite** | 20 linked V1 tasks | Smaller iteration runs |

<sub>The combined V1/V2 corpus has 281 tasks across 163 unique websites. The paper reports 153 / 130 tasks; two ASPCA tasks were subsequently removed.</sub>

<div><a id="quick-start"></a><a id="-human-quick-start"></a><a id="human-quick-start"></a></div>

## Quick start

You need Python 3.11+, [uv](https://docs.astral.sh/uv/), and Docker or Podman. [Platform setup and source installation →](docs/getting-started.md)

```bash
uv tool install clawbench-eval
clawbench
```

The first launch creates local templates under `models/`. Add your agent model and API key in `models/models.yaml`, plus a `deepseek-v4-pro` judge entry or your chosen judge configuration. Then launch `clawbench` again to select a model, corpus, and harness. The [setup guide](docs/getting-started.md#1-configure-models) walks through this configuration.

For a scripted run of the demo task:

```bash
clawbench-run test-cases/v2/v2-1122-education-course-khanacademy your-model --harness hermes
```

Replace `your-model` with your configured model key. The default judge runs after a successful interception; `--no-judge` skips it. First use builds the container image. Recordings and results are written to `test-output/`.

<sub>[All CLI commands](docs/cli.md) · [Harnesses and remote browsers](docs/getting-started.md#3-pick-a-harness) · [Human mode](docs/getting-started.md#2-run-your-first-task) · [Coding-agent context](AGENTS.md)</sub>

## How it works

<p align="center">
  <picture>
    <source media="(max-width: 1200px) and (prefers-color-scheme: dark)" srcset="assets/workflow-mobile-dark.svg" width="460">
    <source media="(max-width: 1200px)" srcset="assets/workflow-mobile-light.svg" width="460">
    <source media="(prefers-color-scheme: dark)" srcset="assets/workflow-dark.svg">
    <img src="assets/workflow-light.svg" width="960" alt="Choose a task, prepare a browser runtime, run the agent, and record evidence for evaluation.">
  </picture>
</p>

[Runtime and recording architecture](docs/architecture.md) · [A recorded run, with evidence](docs/demo.md)

<a id="datasets"></a>

## Data and documentation

| Download | Contents |
| --- | --- |
| [ClawBench tasks](https://huggingface.co/datasets/NAIL-Group/ClawBench) | Instructions, interception schemas, rubrics, and metadata |
| [V1 traces](https://huggingface.co/datasets/NAIL-Group/ClawBenchV1Trace) | Published V1 execution recordings and logs |
| [V2 traces](https://huggingface.co/datasets/TIGER-Lab/ClawBenchV2Trace) | Published V2 recordings, requests, and judgments |

<div><a id="documentation"></a><a id="what-are-you-looking-for"></a><a id="cli"></a><a id="-cli"></a><a id="reproduce-the-leaderboard"></a><a id="-reproduce-the-leaderboard"></a><a id="example-walkthrough"></a><a id="develop-from-source"></a></div>

| I want to… | Read |
| --- | --- |
| Set up a model or browser runtime | [Getting started](docs/getting-started.md) · [Remote browsers](docs/browser-runtimes.md) · [Harbor](docs/harbor.md) |
| Understand scores or reproduce a result | [Scoring](eval/scoring.md) · [Result snapshots](docs/results.md) · [Reproduction](docs/reproduce.md) |
| Build on recorded trajectories | [Download guide](docs/data.md) · [Trace cookbook](docs/trace-cookbook.md) · [Demo source and editing notes](docs/demo.md) |
| Compare benchmarks or inspect the original V1 evaluation | [Related work](docs/related-work.md) · [Historical walkthrough](docs/walkthrough.md) · [Human-reference evaluation](eval/README.md) |
| Reuse the visual identity | [Logo, icons, and social sharing assets](assets/brand/README.md) |

<div><a id="faq"></a><a id="frequently-asked-questions"></a></div>

**Questions about setup, scoring, task coverage, or live-site behavior?** See the [FAQ](docs/faq.md) or [open an issue](https://github.com/TIGER-AI-Lab/ClawBench/issues/new/choose).

<a id="news"></a>

## <img src="assets/icons/bullhorn.svg" width="20" height="20"> News
- **[2026.08.20]** — 🏆 Our paper has been accepted to [EMNLP 2026 Findings](https://2026.emnlp.org/).
- **[2026.08.20]** - Added [Kernel](https://www.kernel.sh) as a supported remote browser runtime. Thanks to @[rgarcia](https://github.com/rgarcia).
- **[2026.08.18]** — Added [WebBrain](https://github.com/webbrain-one/webbrain) as a supported harness. Thanks to @[alectimison-maker](https://github.com/alectimison-maker).
- **[2026.08.16]** — Released **[RewardHarness](https://github.com/TIGER-AI-Lab/RewardHarness)**, our self-evolving agentic reward framework: 47.4% on EditReward-Bench from just 100 preference demos, with no reward-model training. [Details →](https://arxiv.org/abs/2605.08703)
- **[2026.08.03]** — Added [Browserbase](https://www.browserbase.com) as a remote browser runtime. [Details →](docs/browser-runtimes.md)

<sub>Earlier updates: [`docs/news.md`](docs/news.md) &middot; full change history: [`CHANGELOG.md`](CHANGELOG.md)</sub>

<a id="contributing"></a>

## Contribute and connect

Add tasks, fix bugs, or submit model results through the [contribution guide](CONTRIBUTING.md). Start with [good first issues](https://github.com/TIGER-AI-Lab/ClawBench/labels/good%20first%20issue).

<a id="awesome-works-using-clawbench"></a>

Built by NAIL Group. Meet the [contributors and advisors](docs/community.md#core-contributors), explore [research using ClawBench](docs/community.md#awesome-works-using-clawbench), or join the [community](docs/community.md#community).

<sub>[Maintainer contact](docs/community.md#contact) · [WeChat group](assets/community/wechat_grp_422.jpg) · [Hugging Face discussions](https://huggingface.co/datasets/NAIL-Group/ClawBench/discussions) · [Star history](docs/community.md#star-history)</sub>

<a id="citation"></a>

## Citation

If you use ClawBench in your research, please cite:

```bibtex
@misc{zhang2026clawbenchaiagentscomplete,
  title         = {ClawBench: Can AI Agents Complete Everyday Online Tasks?},
  author        = {Yuxuan Zhang and Yubo Wang and Yipeng Zhu and Penghui Du and Junwen Miao and Xuan Lu and Wendong Xu and Yunzhuo Hao and Songcheng Cai and Xiaochen Wang and Huaisong Zhang and Xian Wu and Yi Lu and Minyi Lei and Kai Zou and Huifeng Yin and Ping Nie and Liang Chen and Dongfu Jiang and Wenhu Chen and Kelsey R. Allen},
  year          = {2026},
  eprint        = {2604.08523},
  archivePrefix = {arXiv},
  primaryClass  = {cs.CL},
  url           = {https://arxiv.org/abs/2604.08523}
}
```

## License

[Apache 2.0](LICENSE). See [NOTICE](NOTICE) and [acknowledgments](docs/community.md#license--acknowledgments) for third-party components. Demo provenance and attribution are documented [alongside the recording](docs/demo.md).
