<div align="center">

<a href="https://github.com/reacher-z/ClawBench">
  <picture>
    <source media="(prefers-color-scheme: dark)" srcset="static/hero-dark.svg">
    <img alt="ClawBench" src="static/hero-light.svg" width="820">
  </picture>
</a>

[![Star this repo](https://img.shields.io/badge/%E2%98%85%20Star%20this%20repo-181717?style=flat-square&logo=github&logoColor=white)](https://github.com/reacher-z/ClawBench)
[![arXiv](https://img.shields.io/badge/arXiv-2604.08523-B31B1B?style=flat-square&logo=arxiv&logoColor=white)](https://arxiv.org/abs/2604.08523)
[![HF Daily Paper](https://img.shields.io/badge/Daily_Paper-FFD21E?style=flat-square&logo=huggingface&logoColor=000)](https://huggingface.co/papers/2604.08523)
[![HF Dataset](https://img.shields.io/badge/Dataset-FFD21E?style=flat-square&logo=huggingface&logoColor=000)](https://huggingface.co/datasets/NAIL-Group/ClawBench)
[![HF Trace Dataset](https://img.shields.io/badge/Trace_Dataset-FFD21E?style=flat-square&logo=huggingface&logoColor=000)](https://huggingface.co/datasets/NAIL-Group/ClawBenchV1Trace)
[![Project Page](https://img.shields.io/badge/claw--bench.com-4F46E5?style=flat-square&logo=googlechrome&logoColor=white)](https://claw-bench.com)
[![GitHub stars](https://img.shields.io/github/stars/reacher-z/ClawBench?style=flat-square&logo=github&color=181717&cacheSeconds=300)](https://github.com/reacher-z/ClawBench)
[![Discord](https://img.shields.io/badge/Discord-%E5%8A%A0%E5%85%A5-5865F2?style=flat-square&logo=discord&logoColor=white)](https://discord.gg/clawbench)
[![Codespaces](https://img.shields.io/badge/Codespaces-%E4%B8%80%E9%94%AE%E6%89%93%E5%BC%80-181717?style=flat-square&logo=github&logoColor=white)](https://codespaces.new/reacher-z/ClawBench?quickstart=1)

[![PyPI downloads](https://img.shields.io/pypi/dm/clawbench-eval?style=flat-square&logo=pypi&color=3775A9&logoColor=white&label=PyPI%20downloads)](https://pypi.org/project/clawbench-eval/)
[![PyPI version](https://img.shields.io/pypi/v/clawbench-eval?style=flat-square&logo=pypi&color=3775A9&logoColor=white)](https://pypi.org/project/clawbench-eval/)
[![Last commit](https://img.shields.io/github/last-commit/reacher-z/ClawBench?style=flat-square&logo=github&logoColor=white)](https://github.com/reacher-z/ClawBench/commits/main)
[![Contributors](https://img.shields.io/github/contributors/reacher-z/ClawBench?style=flat-square&logo=github&logoColor=white)](https://github.com/reacher-z/ClawBench/graphs/contributors)
[![Commit activity](https://img.shields.io/github/commit-activity/m/reacher-z/ClawBench?style=flat-square&logo=github&logoColor=white)](https://github.com/reacher-z/ClawBench/graphs/commit-activity)
[![License](https://img.shields.io/github/license/reacher-z/ClawBench?style=flat-square&color=A42E2B)](https://github.com/reacher-z/ClawBench/blob/main/LICENSE)

<p align="center"><sub><i>已被收录于</i></sub></p>
<p align="center">
  <a href="https://github.com/walkinglabs/awesome-harness-engineering"><img alt="awesome-harness-engineering" src="https://img.shields.io/badge/Featured-awesome--harness--engineering-7C3AED?style=flat-square&logo=awesomelists&logoColor=white"></a>
  <a href="https://github.com/Jenqyang/Awesome-AI-Agents"><img alt="Awesome-AI-Agents" src="https://img.shields.io/badge/Featured-Awesome--AI--Agents-7C3AED?style=flat-square&logo=awesomelists&logoColor=white"></a>
  <a href="https://github.com/ranpox/awesome-computer-use"><img alt="awesome-computer-use" src="https://img.shields.io/badge/Featured-awesome--computer--use-7C3AED?style=flat-square&logo=awesomelists&logoColor=white"></a>
  <a href="https://github.com/ZJU-REAL/Awesome-GUI-Agents"><img alt="Awesome-GUI-Agents" src="https://img.shields.io/badge/Featured-Awesome--GUI--Agents-7C3AED?style=flat-square&logo=awesomelists&logoColor=white"></a>
  <a href="https://github.com/zhangxjohn/LLM-Agent-Benchmark-List"><img alt="LLM-Agent-Benchmark-List" src="https://img.shields.io/badge/Featured-LLM--Agent--Benchmark--List-7C3AED?style=flat-square&logo=awesomelists&logoColor=white"></a>
</p>

<p align="center">
  <a href="https://huggingface.co/papers/2604.08523"><img src="https://img.shields.io/badge/%233_Paper_of_the_Day-FFD21E?style=for-the-badge&logo=huggingface&logoColor=000" alt="#3 Paper of the Day"></a>
</p>

<p align="center">
  <a href="https://deepwiki.com/reacher-z/ClawBench"><img alt="Ask DeepWiki" src="https://deepwiki.com/badge.svg" /></a>
</p>

</div>

<div align="center">

<p align="center">
  <b>新项目：</b> 欢迎关注我们的姊妹项目 <a href="https://github.com/reacher-z/HarnessBench"><b>HarnessBench</b></a> &mdash;
  固定基础模型，比较不同 Harness。同一套评测流水线，正交维度。
</p>

<a href="#-手动快速开始"><img src="https://img.shields.io/badge/%E4%B8%80%E9%94%AE%E5%90%AF%E5%8A%A8-4F46E5?style=for-the-badge&labelColor=4F46E5&logoColor=white&logo=data:image/svg%2Bxml;base64,PHN2ZyB4bWxucz0iaHR0cDovL3d3dy53My5vcmcvMjAwMC9zdmciIHZpZXdCb3g9IjAgMCA1NzYgNTEyIj48cGF0aCBmaWxsPSIjZmZmZmZmIiBkPSJNMjYzLjQtMjdMMjc4LjIgOS44IDMxNSAyNC42YzMgMS4yIDUgNC4yIDUgNy40cy0yIDYuMi01IDcuNEwyNzguMiA1NC4yIDI2My40IDkxYy0xLjIgMy00LjIgNS03LjQgNXMtNi4yLTItNy40LTVMMjMzLjggNTQuMiAxOTcgMzkuNGMtMy0xLjItNS00LjItNS03LjRzMi02LjIgNS03LjRMMjMzLjggOS44IDI0OC42LTI3YzEuMi0zIDQuMi01IDcuNC01czYuMiAyIDcuNCA1ek0xMTAuNyA0MS43bDIxLjUgNTAuMSA1MC4xIDIxLjVjNS45IDIuNSA5LjcgOC4zIDkuNyAxNC43cy0zLjggMTIuMi05LjcgMTQuN2wtNTAuMSAyMS41LTIxLjUgNTAuMWMtMi41IDUuOS04LjMgOS43LTE0LjcgOS43cy0xMi4yLTMuOC0xNC43LTkuN0w1OS44IDE2NC4yIDkuNyAxNDIuN0MzLjggMTQwLjIgMCAxMzQuNCAwIDEyOHMzLjgtMTIuMiA5LjctMTQuN0w1OS44IDkxLjggODEuMyA0MS43QzgzLjggMzUuOCA4OS42IDMyIDk2IDMyczEyLjIgMy44IDE0LjcgOS43ek00NjQgMzA0YzYuNCAwIDEyLjIgMy44IDE0LjcgOS43bDIxLjUgNTAuMSA1MC4xIDIxLjVjNS45IDIuNSA5LjcgOC4zIDkuNyAxNC43cy0zLjggMTIuMi05LjcgMTQuN2wtNTAuMSAyMS41LTIxLjUgNTAuMWMtMi41IDUuOS04LjMgOS43LTE0LjcgOS43cy0xMi4yLTMuOC0xNC43LTkuN2wtMjEuNS01MC4xLTUwLjEtMjEuNWMtNS45LTIuNS05LjctOC4zLTkuNy0xNC43czMuOC0xMi4yIDkuNy0xNC43bDUwLjEtMjEuNSAyMS41LTUwLjFjMi41LTUuOSA4LjMtOS43IDE0LjctOS43ek00NjAgMGMxMSAwIDIxLjYgNC40IDI5LjUgMTIuMmw0Mi4zIDQyLjNDNTM5LjYgNjIuNCA1NDQgNzMgNTQ0IDg0cy00LjQgMjEuNi0xMi4yIDI5LjVsLTg4LjIgODguMi0xMDEuMy0xMDEuMyA4OC4yLTg4LjJDNDM4LjQgNC40IDQ0OSAwIDQ2MCAwek00NC4yIDM5OC41TDMwOC40IDEzNC4zIDQwOS43IDIzNS42IDE0NS41IDQ5OS44QzEzNy42IDUwNy42IDEyNyA1MTIgMTE2IDUxMnMtMjEuNi00LjQtMjkuNS0xMi4yTDQ0LjIgNDU3LjVDMzYuNCA0NDkuNiAzMiA0MzkgMzIgNDI4czQuNC0yMS42IDEyLjItMjkuNXoiLz48L3N2Zz4=" alt="一键启动"></a>

```bash
git clone https://github.com/reacher-z/ClawBench.git && cd ClawBench && ./run.sh
```

<sub><i>克隆 → 配置 → 运行。&nbsp; 根目录 uv 包。&nbsp; Docker 隔离 harness。</i></sub>

### AI 智能体能完成日常在线任务吗?

**ClawBench 是一个开源基准，用于评测 AI browser agent 在日常在线任务上的表现 —— 订酒店、点外卖、投简历、管理邮件 —— 覆盖真实网站。V1 位于 `test-cases/v1/`，包含 153 个任务、覆盖 144 个网站；V2 位于 `test-cases/v2/`，包含 130 个任务。它通过 5 层录制管线和对照人工参考轨迹的 agentic evaluator 衡量端到端任务完成率。目前最高分：33.3%。**

<img src="static/clawbench_logo.png" alt="ClawBench logo" width="320">

我们让前沿 AI 智能体去做人们每天都在做的事 --<br/>
点外卖、订酒店、投简历、写评价、管理项目。<br/>
**即使最强的模型，也只能完成其中约三分之一。**

<sub><i>由 NAIL Group 出品 &nbsp;·&nbsp; 姊妹项目：<a href="https://github.com/reacher-z/HarnessBench">HarnessBench</a> &nbsp;·&nbsp; 任意 Chrome 上即可运行。</i></sub>

---

**V1: 153** 个日常任务 &nbsp;&middot;&nbsp; **V2: 130** 个任务 &nbsp;&middot;&nbsp; **144** 个真实网站 &nbsp;&middot;&nbsp; **15** 个生活类别

<a href="README.md"><img src="static/icons/language.svg" width="16" height="16"> English</a>

</div>

## <img src="static/icons/circle-question.svg" width="20" height="20"> 你想找什么？

<table>
<tr>
<td width="25%" align="center" valign="top">

🏆 **查看分数**<br/>
[实时排行榜](https://huggingface.co/spaces/TIGER-Lab/ClawBench)<br/>
<sub>选择语料 (v1 / v2)</sub>

</td>
<td width="25%" align="center" valign="top">

🚀 **在你的模型上运行**<br/>
[快速开始 ↓](#-手动快速开始)<br/>
<sub><code>pip install clawbench-eval</code></sub>

</td>
<td width="25%" align="center" valign="top">

📊 **浏览 283 个任务**<br/>
[任务浏览器](https://claw-bench.com/tasks)<br/>
<sub>搜索 · 筛选 · 分类</sub>

</td>
<td width="25%" align="center" valign="top">

📄 **阅读论文**<br/>
[arXiv:2604.08523](https://arxiv.org/abs/2604.08523)<br/>
<sub>方法 · 评测器 · 结果</sub>

</td>
</tr>
<tr>
<td align="center" valign="top">

🎬 **重新评分旧运行**<br/>
[V1](https://huggingface.co/datasets/NAIL-Group/ClawBenchV1Trace) · [V2](https://huggingface.co/datasets/TIGER-Lab/ClawBenchV2Trace) 原始轨迹<br/>
<sub>每个 (任务 × 模型) 都有 5 层数据</sub>

</td>
<td align="center" valign="top">

📦 **下载数据**<br/>
[`hf download NAIL-Group/ClawBench`](https://huggingface.co/datasets/NAIL-Group/ClawBench)<br/>
<sub>任务 · rubric · 元数据</sub>

</td>
<td align="center" valign="top">

🌱 **添加任务 / 模型**<br/>
[贡献指南](#贡献)<br/>
<sub>YAML 规范 + rubric</sub>

</td>
<td align="center" valign="top">

❓ **有问题**<br/>
[FAQ](#常见问题) · [Discord](https://discord.gg/clawbench)<br/>
<sub>也欢迎开 issue</sub>

</td>
</tr>
</table>

## <img src="static/icons/bullhorn.svg" width="20" height="20"> 动态

- **[2026.05.12]** <img src="static/icons/rocket.svg" width="14" height="14"> &nbsp;权威排行榜迁移至 **[`TIGER-Lab/ClawBench`](https://huggingface.co/spaces/TIGER-Lab/ClawBench)** —— 仿 [`TIGER-Lab/MMLU-Pro`](https://huggingface.co/spaces/TIGER-Lab/MMLU-Pro) 风格的 Gradio 三标签 Space（Leaderboard / About / Submit）。全部 HF 资产统一收纳于 **[ClawBench Collection](https://huggingface.co/collections/TIGER-Lab/clawbench-6a0247d04680f475038797d4)** —— 论文 + V1/V2 数据集 + V1Trace + V2Trace + Space 一站直达。排名口径修正：未完成批次的 partial 结果不再压制完整批次较低 reward 的模型。（[`NAIL-Group/clawbench-leaderboard`](https://huggingface.co/spaces/NAIL-Group/clawbench-leaderboard) 保留作为历史镜像。）
- **[2026.05.11]** <img src="static/icons/chart-bar.svg" width="14" height="14"> &nbsp;V2 排行榜上线 —— 首批 6 个模型完成端到端评分，采用两阶段 rubric（拦截 + LLM judge）。目前最高：`glm-5.1 / hermes`，**18.5% reward / 48.5% intercepted**。见 [`claw-bench.com/leaderboard`](https://claw-bench.com/leaderboard)，评分细节见 [`eval/scoring.md`](eval/scoring.md)，实时数据见 [HF Space](https://huggingface.co/spaces/TIGER-Lab/ClawBench)。
- **[2026.05.11]** <img src="static/icons/layer-group.svg" width="14" height="14"> &nbsp;配套 trace 数据集 **[ClawBenchV2Trace](https://huggingface.co/datasets/NAIL-Group/ClawBenchV2Trace)** 即将上线 —— 与 V1Trace 一样，每次运行都包含 5 层 trace bundle，并会随新的 V2 评测持续更新。
- **[2026.05.09]** <img src="static/icons/globe.svg" width="14" height="14"> 新增对 **pi** harness 的支持 —— Pi coding agent + `pi-browser-harness`。
- **[2026.05.09]** <img src="static/icons/layer-group.svg" width="14" height="14"> &nbsp;发布 **[ClawBenchV1Trace](https://huggingface.co/datasets/NAIL-Group/ClawBenchV1Trace)** —— V1 全部已评测模型运行的完整执行 trace：屏幕录制（`recording.mp4`）、网络请求（`requests.jsonl`）、浏览器操作（`actions.jsonl`）、智能体推理（`agent-messages.jsonl`）、被拦截的最终请求（`interception.json`）。任何人都可基于此复现、重新评分或事后分析我们的结果。与既有的 [任务定义数据集](https://huggingface.co/datasets/NAIL-Group/ClawBench) 配套使用。
- **[2026.05.09]** <img src="static/icons/robot.svg" width="14" height="14"> &nbsp;新增 **inline LLM judge** 作为第二阶段评分。Pass = (1) 智能体最终 HTTP 请求被拦截并匹配任务的 URL/method schema，且 (2) LLM judge 确认请求 body 实际满足自然语言指令。默认 judge：`deepseek-v4-pro`。可用 `--no-judge` 关闭。这意味着**运行现在会自动产出最终 pass/fail 分数**，不再需要单独检查轨迹。
- **[2026.05.09]** <img src="static/icons/rocket.svg" width="14" height="14"> &nbsp;我们更新了发布流水线，并将包以 [**clawbench-eval**](https://pypi.org/project/clawbench-eval/) 的名称发布到 PyPI，便于安装和使用。
- **[2026.05.04]** <img src="static/icons/screwdriver-wrench.svg" width="14" height="14"> &nbsp;重构了代码库，以优化项目结构、提升 CI/CD 流水线效率、增强对更多测试套件的扩展能力，并为 **V1**、**V1-Lite** 和 **V2** 提供更稳定的构建行为；同时根据用户反馈更新了常见问题部分。
- **[2026.05.01]** <img src="static/icons/rocket.svg" width="14" height="14"> &nbsp;加入完整 **V2** 130-task 语料和一行 Hermes 启动命令：
  `uv run clawbench-batch --models deepseek/deepseek-v4-flash --cases-suite v2 --all-cases --harness hermes --max-concurrent 3 --no-upload`
- **[2026.04.25]**<img src="static/icons/globe.svg" width="14" height="14"> 新增对 **hermes** harness 的支持。
- **[2026.04.22]**<img src="static/icons/rocket.svg" width="14" height="14"> 新增对 **claude-code-chrome-extension** harness 的支持 —— Claude Code CLI + [Claude in Chrome](https://code.claude.com/docs/en/chrome) 扩展。
- **[2026.04.20]**<img src="static/icons/screwdriver-wrench.svg" width="14" height="14"> 新增对 **claw-code** harness 的支持。
- **[2026.04.18]** <img src="static/icons/globe.svg" width="14" height="14"> &nbsp;新增对 **browser-use** Harness 的支持。
- **[2026.04.17]** <img src="static/icons/rocket.svg" width="14" height="14"> &nbsp;新增对 **Codex** Harness 的支持。
- **[2026.04.16]** <img src="static/icons/bolt.svg" width="14" height="14"> &nbsp;新增对 **Claude Code** Harness 的支持。
- **[2026.04.16]** 被 **5 个精选 awesome-list** 收录：[awesome-harness-engineering](https://github.com/walkinglabs/awesome-harness-engineering)、[Awesome-AI-Agents](https://github.com/Jenqyang/Awesome-AI-Agents)、[awesome-computer-use](https://github.com/ranpox/awesome-computer-use)、[Awesome-GUI-Agents](https://github.com/ZJU-REAL/Awesome-GUI-Agents)、[LLM-Agent-Benchmark-List](https://github.com/zhangxjohn/LLM-Agent-Benchmark-List)。
- **[2026.04.15]** 姊妹项目 [**HarnessBench**](https://github.com/reacher-z/HarnessBench) 发布 — 固定模型、比较 Harness。已上架 [PyPI](https://pypi.org/project/harness-bench/)。
- **[2026.04.14]** <img src="static/icons/screwdriver-wrench.svg" width="14" height="14"> &nbsp;新增对 **OpenCode** Harness 的支持。
- **[2026.04.14]** 项目被 [**DeepWiki**](https://deepwiki.com/reacher-z/ClawBench) 收录 — 可用自然语言提问 ClawBench 相关问题。
- **[2026.04.11]** 荣获 [**HuggingFace 当日论文 #3**](https://huggingface.co/papers/2604.08523)!
- **[2026.04.11]** 论文发布于 [arXiv (2604.08523)](https://arxiv.org/abs/2604.08523)。数据集上线 [HuggingFace](https://huggingface.co/datasets/NAIL-Group/ClawBench)。

<br/>

<p align="center">
<img src="static/icons/globe.svg" width="24" height="24">&nbsp;<b>真实网站</b>
&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;
<img src="static/icons/cube.svg" width="24" height="24">&nbsp;<b>隔离容器</b>
&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;
<img src="static/icons/shield-halved.svg" width="24" height="24">&nbsp;<b>请求拦截器</b>
&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;
<img src="static/icons/layer-group.svg" width="24" height="24">&nbsp;<b>五层录制</b>
</p>

<br/>

## <img src="static/icons/layer-group.svg" width="20" height="20"> 数据集

ClawBench 提供 **三个** Hugging Face 数据集 —— 任务定义，以及 V1 / V2 的完整执行 trace。全部开源，一行命令即可下载。benchmark 本身也镜像在 **TIGER-Lab**，方便发现和引用。

| 数据集 | 内容 | 下载 |
|---|---|---|
| **[NAIL-Group/ClawBench](https://huggingface.co/datasets/NAIL-Group/ClawBench)** _(也镜像在 [TIGER-Lab/ClawBench](https://huggingface.co/datasets/TIGER-Lab/ClawBench))_ | V1（153 个任务）和 V2（130 个任务）的任务定义、评分规则和元数据 —— 即“做什么”和“怎么打分”。 | `hf download --repo-type dataset NAIL-Group/ClawBench` |
| **[NAIL-Group/ClawBenchV1Trace](https://huggingface.co/datasets/NAIL-Group/ClawBenchV1Trace)** | V1 每个模型运行一个目录，内含 `recording.mp4`、`requests.jsonl`、`actions.jsonl`、`agent-messages.jsonl`、`interception.json`、`run-meta.json` —— 即我们用来评分该次运行的全部数据。 | `hf download --repo-type dataset NAIL-Group/ClawBenchV1Trace` |
| **[NAIL-Group/ClawBenchV2Trace](https://huggingface.co/datasets/NAIL-Group/ClawBenchV2Trace)** | **V2** 模型运行的同款 5 层数据包。滚动更新 —— 新模型评测完成后会持续加入。 | `hf download --repo-type dataset NAIL-Group/ClawBenchV2Trace` |

> Trace 数据集体积较大；可用 `hf download --include "<pattern>"` 仅拉取某个模型或某个任务。

> **🏆 实时排行榜：** [`claw-bench.com/leaderboard`](https://claw-bench.com/leaderboard)（默认 V2，两阶段评分 —— 拦截 + LLM judge）。完整评分公式见 [`docs/scoring.md`](docs/scoring.md)。提交你的运行结果：向 [`leaderboard/results.csv`](https://huggingface.co/datasets/NAIL-Group/ClawBench/blob/main/leaderboard/results.csv) 提 PR。

## 工作流程

```
   你选择一个任务             ClawBench 启动一个          智能体驱动浏览器:          拦截器捕获所有操作
   来自 V1 或 V2 的            隔离的 Docker 容器          导航、填表、点击            并录制完整五层数据
   日常场景                    + Chromium

   ┌──────────────┐           ┌──────────────┐           ┌──────────────┐           ┌──────────────┐
   │ "在 Rover 上 │    ──►    │    容器      │    ──►    │   AI 智能体  │    ──►    │   五层数据   │
   │  预订宠物    │           │  + Chromium  │           │  浏览真实    │           │   全部拦截   │
   │  寄养"       │           │  + 智能体    │           │   网站       │           │   完整录制   │
   └──────────────┘           └──────────────┘           └──────────────┘           └──────────────┘
```

<br/>

# <img src="static/icons/robot.svg" width="28" height="28"> LLM 快速开始

将你的编程智能体 (Claude Code, Cursor, Copilot 等) 指向 [`AGENTS.md`](AGENTS.md)，直接提问即可。

<br/>

# <img src="static/icons/person.svg" width="28" height="28"> 手动快速开始

日常使用建议直接从 PyPI 安装 ClawBench:

```bash
uv tool install clawbench-eval
```

也可以使用 `pipx install clawbench-eval` 或 `python -m pip install clawbench-eval`。
安装后的命令仍然是 `clawbench`、`clawbench-run` 和 `clawbench-batch`。

如果你想要更细粒度的控制或参与贡献，可以克隆仓库并运行根目录 `uv` 包入口:

```bash
git clone https://github.com/reacher-z/ClawBench.git && cd ClawBench && ./run.sh
```

**前置条件:** [Python 3.11+](https://python.org)、[uv](https://docs.astral.sh/uv/)，以及一个容器引擎 —— [Docker](https://www.docker.com/) **或** [Podman](https://podman.io/)。ClawBench 会自动检测已安装的那个；也可以用 `export CONTAINER_ENGINE=docker` 或 `export CONTAINER_ENGINE=podman` 强制指定。

<details>
<summary><b>安装 Docker 或 Podman</b> (macOS / Linux / Windows)</summary>

#### macOS

```bash
# 方案 A —— Docker Desktop（最简单，带 GUI）
brew install --cask docker
open -a Docker                 # 启动后等任务栏的鲸鱼图标转完

# 方案 B —— Podman（rootless，无 daemon，仅 CLI）
brew install podman
podman machine init            # 一次性：下载 Linux VM 镜像
podman machine start           # 每次 podman 命令前必须先启动
```

> **macOS 上 Podman 需要 VM。** 只 `brew install podman` 是不够的 —— Podman 在 macOS 上靠一个小 Linux VM 来跑容器，装完必须跑一次 `podman machine init && podman machine start`，否则 `podman info` 会直接报 `Cannot connect to Podman`。

#### Linux (Ubuntu / Debian)

```bash
# 方案 A —— Podman（默认 rootless，推荐）
sudo apt update && sudo apt install -y podman

# 方案 B —— Docker
sudo apt install -y docker.io
sudo usermod -aG docker $USER  # 登出再登入让 shell 拾取新组
```

> **Rootful Docker 文件归属坑：** 用 `sudo` 方式跑的 Docker，容器里产生的文件 `docker cp` 出来之后属主是 `root`，普通用户 `rm` 不动。ClawBench 驱动在每次运行后会检测到这个情况，自动 chown `test-output/` 回当前用户。如果你也会用其他容器工具并排跑，可以考虑 rootless Podman（或 rootless Docker）从根上避免这个问题。

#### Windows

```powershell
# 方案 A —— Docker Desktop（WSL2 后端）
winget install Docker.DockerDesktop
# 然后从开始菜单启动 Docker Desktop，等它就绪

# 方案 B —— Podman
winget install RedHat.Podman
podman machine init
podman machine start
```

> 下面那些 `uv run …` 命令请从 **PowerShell**、**WSL2** 或 **Git Bash** 里跑。和 macOS 一样，Windows Podman 第一次用之前也必须 `podman machine init && podman machine start`。

</details>

**1. 配置模型** —— 一次性设置。

如果你是从 PyPI 安装的，请在希望保存运行结果和可编辑配置的目录中运行
`clawbench`。首次启动时会在本地创建 `models/` 模板；你可以在 TUI 中添加模型，
也可以直接编辑配置文件:

```bash
clawbench
$EDITOR models/models.yaml
```

如果你是从源码 checkout 运行:

```bash
cp models/models.example.yaml models/models.yaml
$EDITOR models/models.yaml
```

用于生成一次性运行邮箱的 PurelyMail 凭据已在仓库提交的 `.env` 中提供。只有在你想使用自己的 PurelyMail 账号，或启用可选 HuggingFace 上传时，才需要编辑 `.env`。

> [!NOTE]
> **首次运行会构建容器镜像**（Chromium + ffmpeg + noVNC + 所选 agent harness 依赖）。构建时会实时显示进度 spinner + 当前 step，后续运行直接走 layer 缓存，秒级完成。

**2. 跑你的第一个任务** (四选一):

> [!TIP]
> **推荐 &rarr; 交互式 TUI** &nbsp; 引导式选择模型 + 测试用例
> ```bash
> clawbench         # PyPI 安装
> uv run clawbench  # 源码 checkout
> ```
> 如果是从 PyPI 安装，请直接运行 `clawbench`。需要交互式终端。
> 管道 / CI / 非 TTY 环境请直接用 `clawbench-run` 或 `clawbench-batch`；
> 如果是源码 checkout，请在命令前加 `uv run`。

**(b) 指定模型跑单个任务:**
```bash
uv run clawbench-run test-cases/v1/001-daily-life-food-uber-eats claude-sonnet-4-6
```
容器启动后,脚本会打印一个 **noVNC URL**（如 `http://localhost:6080/vnc.html`）—— 在浏览器中打开即可实时观看 agent 操作。如果 6080 端口被占用,会自动选一个空闲端口。

结果落在 `./test-output/<model>/<harness>-<case>-<model>-<timestamp>/`，包含完整的五层录制。默认 harness 是 `openclaw`；想用 [opencode](https://opencode.ai) 就加 `--harness opencode`，想用 [Claude Code](https://docs.anthropic.com/en/docs/claude-code) 就加 `--harness claude-code`，想用 Claude Code + [Claude in Chrome](https://code.claude.com/docs/en/chrome) 扩展就加 `--harness claude-code-chrome-extension`（Microsoft Edge + 本地桥，通过旁路栈使 LiteLLM 路由的任意模型都可用），想用 [OpenAI Codex CLI](https://github.com/openai/codex) 就加 `--harness codex`，想用 [claw-code](https://github.com/ultraworkers/claw-code) 就加 `--harness claw-code`，想用 [browser-use](https://github.com/browser-use/browser-use) 就加 `--harness browser-use`（Python 框架，通过 LiteLLM 路由），想用 [Hermes Agent](https://github.com/NousResearch/hermes-agent) 就加 `--harness hermes`（原生浏览器工具通过 CDP 接入 ClawBench Chrome），想用 [Pi](https://pi.dev/) 就加 `--harness pi`（固定版本 [pi-browser-harness](https://pi.dev/packages/pi-browser-harness) 浏览器工具，接入同一个 ClawBench Chrome CDP 端点）。

**(c) 通过 noVNC 手动控制浏览器** —— 产出人工参考轨迹:
```bash
uv run clawbench-run test-cases/v1/001-daily-life-food-uber-eats --human
```
打开脚本打印的 noVNC URL,在浏览器里亲手完成任务,完事后关掉标签页。端口被占时会自动换一个。

**(d) 搭配外部 browser agent** —— 使用 Human mode 运行，打开 noVNC URL，让外部 browser agent 控制该浏览器会话；ClawBench 会照常录制和拦截。

<details>
<summary><b>从源码开发</b> &nbsp;— 克隆 + ``./run.sh``（面向贡献者）</summary>

如果你要改 driver、bundled test-cases 或者容器构建本身，用源码 checkout 更合适。

```bash
git clone https://github.com/reacher-z/ClawBench.git && cd ClawBench
cp models/models.example.yaml models/models.yaml   # 编辑：填入你的模型 API 密钥
# .env 已提供 PurelyMail 凭据；仅在自带凭据或配置 HF 上传时编辑
./run.sh                                           # 交互式 TUI
uv run clawbench-run \
  test-cases/v1/001-daily-life-food-uber-eats claude-sonnet-4-6   # 单个任务
uv run clawbench-run \
  test-cases/v1/001-daily-life-food-uber-eats --human             # 人工参考
```

这条路径会让你对 `src/`、`src/clawbench/runtime/chrome-extension/` 和 `test-cases/` 下的所有 suite 获得 live-reload，适合迭代 harness 本身。

</details>

<br/>

# <img src="static/icons/chart-bar.svg" width="28" height="28"> ClawBench-Lite

**第一次跑？先跑这个。** [`test-cases/v1-lite/`](test-cases/v1-lite/) 是完整 153 任务的 **20 个精选子集**，按站点知名度、真实日常相关度、难度和类别多样性挑选。它对齐了 [browser-use/benchmark](https://github.com/browser-use/benchmark) 的 20-tasks-per-source 规范，用完整 benchmark 一小部分的成本就能拿到可信的信号。

分层: **flagship 9 / core 8 / wildcard 3** —— 覆盖日常生活 (OpenTable, DoorDash, Instacart, TaskRabbit)、娱乐爱好 (Eventbrite, Goodreads, Fandango)、创建初始化 (Asana, Mailchimp, Squarespace)、旅行 (Airbnb)、教育 (LeetCode)、开发技术 (GitHub)、学术研究 (Overleaf)、个人管理 (1Password) 等类别。所有 Lite 任务均由 [`eval/agentic_eval.md`](eval/agentic_eval.md) 判定，不依赖 `url_pattern` 形态。

Lite 现在是一个一等 suite：使用 `--cases-suite v1-lite` 运行，或在 [`test-cases/v1-lite/`](test-cases/v1-lite/) 查看这些指向 V1 任务文件的链接。

<br/>

# <img src="static/icons/play.svg" width="28" height="28"> 演示

每次 ClawBench 运行都会产生完整的 MP4 录屏。访问[项目主页](https://claw-bench.com)查看 V1 任务录屏。

<br/>

# <img src="static/icons/circle-question.svg" width="28" height="28"> 任务走读示例

好奇一个任务从头到尾到底长什么样? 下面是 **001 号任务** 的完整走读。

**任务定义** —— 来自 [`test-cases/v1/001-daily-life-food-uber-eats/task.json`](test-cases/v1/001-daily-life-food-uber-eats/task.json):

```json
{
  "instruction": "On Uber Eats, order delivery: one Pad Thai, deliver to home address, note \"no peanuts\"",
  "time_limit": 30,
  "eval_schema": {
    "url_pattern": "__PLACEHOLDER_WILL_NOT_MATCH__",
    "method": "POST"
  }
}
```

智能体拿到的就是这段原文 `instruction`,另外有只读权限访问 `/my-info/alex_green_personal_info.json` (dummy user 的姓名、住址、电话、生日) 和一个一次性邮箱账号 (万一遇到强制登录)。它有 **30 分钟** 去触发一个 `POST` 请求,超时容器会被 kill。

**智能体要做什么** (顺利路径下):

1. 打开 `ubereats.com`
2. 从 `/my-info/alex_green_personal_info.json` 读出 dummy user 的家庭住址,填入配送地址输入框
3. 在菜品搜索框里搜 **"Pad Thai"**
4. 挑一家能配送到这个地址且有 Pad Thai 的餐厅
5. 进入菜品详情页,在定制或特殊说明字段里填 **"no peanuts"**
6. 加一份到购物车,打开购物车,必要时用一次性邮箱凭据处理登录弹窗
7. 进入 checkout,点 **Place Order**

**拦截器抓到了什么** —— 最后的 *Place Order* 那一点会发起一个 `POST` 请求。ClawBench 的 request interceptor 架在浏览器和目标站之间,**会在请求到达 Uber Eats 服务器之前抓下来**,所以 dummy user 永远不会被真的扣款。拦截发生的那一瞬间,五层录制 (MP4 视频、PNG 截图、HTTP 流量、浏览器动作、智能体消息) 会被一起冻结到 `/data/`。

**裁判怎么判 PASS / FAIL** —— 001 号任务的 `url_pattern` 是特意留的 sentinel `__PLACEHOLDER_WILL_NOT_MATCH__`,这意味着**没有任何请求路径能机械匹配**。判决完全由 [`eval/agentic_eval.md`](eval/agentic_eval.md) 里的 agentic judge 给出 —— 它把智能体的五层录制和人工参考轨迹对照,检查四件事:

- 智能体有没有真正走到最后的 checkout?
- 购物车里是不是**正好一份** Pad Thai (不是两份、也不是套餐)?
- 配送地址是不是 `alex_green_personal_info.json` 里的家庭住址?
- 订单的特殊说明字段里有没有 **"no peanuts"**?

四条全满足才算 **PASS**,任何一条没达到就是 **FAIL**,而且失败证据会被绑定到对应的判据上。正是这种 per-task rubric 让 ClawBench 对裁判敏感而不是对 URL 正则敏感 —— 完整 rubric 格式见 [`eval/README.md`](eval/README.md),judge prompt 见 [`eval/agentic_eval.md`](eval/agentic_eval.md)。

<br/>

# <img src="static/icons/chart-bar.svg" width="28" height="28"> 实验结果

<div align="center">

**6 个前沿 AI 智能体在 ClawBench V1 上的成功率 (%)**

</div>

| 排名 | 模型 | 总体 | 日常 | 金融 | 工作 | 开发 | 学术 | 旅行 | 社交 | 宠物 |
|:----:|-------|:------:|:-----:|:-----:|:----:|:---:|:----:|:----:|:----:|:----:|
| 1 | **Claude Sonnet 4.6** | **33.3** | 44.2 | **50.0** | 19.0 | 11.1 | **50.0** | 23.1 | **38.9** | **18.2** |
| 2 | GLM-5 | 24.2 | **30.8** | 16.7 | **38.1** | 16.7 | 28.6 | 0.0 | 16.7 | **18.2** |
| 3 | Gemini 3 Flash | 19.0 | 15.4 | 33.3 | 23.8 | **22.2** | 28.6 | **30.8** | 11.1 | 0.0 |
| 4 | Claude Haiku 4.5 | 18.3 | 15.4 | 22.2 | 19.0 | **27.8** | 21.4 | 7.7 | 16.7 | **18.2** |
| 5 | GPT-5.4 | 6.5 | 9.6 | 0.0 | 0.0 | 11.1 | 7.1 | 7.7 | 0.0 | 9.1 |
| 6 | Gemini 3.1 Flash Lite | 3.3 | 1.9 | 0.0 | 0.0 | 5.6 | 14.3 | 0.0 | 0.0 | 9.1 |

<details>
<summary><b>任务类别 (15 个类别, 153 个任务)</b></summary>

| 类别 | 数量 | 示例平台 |
|----------|:-----:|-------------------|
| 日常生活 | 21 | Uber Eats, DoorDash, Instacart, Zillow, Craigslist |
| 娱乐与爱好 | 15 | Ticketmaster, AMC Theatres, Topgolf, Crunchyroll |
| 创建与初始化 | 13 | Squarespace, Wix, Webflow, Ghost, Substack |
| 评分与投票 | 10 | Trustpilot, G2, Goodreads, RateMyProfessors |
| 旅行 | 9 | Booking.com, Expedia, Airbnb, TripAdvisor |
| 教育与学习 | 9 | Coursera, Udemy, Khan Academy, Duolingo |
| 办公与秘书 | 9 | Google Calendar, Slack, Notion, Trello |
| 美容与个护 | 9 | Sephora, Ulta, Glossier |
| 求职与 HR | 8 | LinkedIn, Greenhouse, Lever, Workday |
| 宠物与动物护理 | 8 | Chewy, Petco, Rover |
| 个人管理 | 6 | Mint, YNAB, Todoist |
| 购物与电商 | 6 | Amazon, eBay, Etsy, Target |
| 非营利与慈善 | 6 | GoFundMe, DonorsChoose |
| 学术与研究 | 5 | Google Scholar, Semantic Scholar, OpenReview |
| 金融与投资 | 4 | Robinhood, Fidelity, Coinbase |
| 其他 | 15 | 自动化、开发与技术、政府、家居服务、汽车 |

</details>

<br/>

## ClawBench 与相关工作对比

| Benchmark | 领域 | 环境 | 任务数 | ClawBench 的差异 |
|-----------|------|------|--------|------------------|
| [WebArena](https://webarena.dev) | 合成 Web 应用 | 自建副本 | 812 | 真实消费级网站,而非托管后台 UI |
| [GAIA](https://huggingface.co/datasets/gaia-benchmark/GAIA) | 通用助手 | 闭卷文本 + 工具 | 466 | 以浏览器为中心;端到端任务执行 |
| [SWE-bench](https://www.swebench.com) | 软件工程 | GitHub 仓库 | 2,294 | 非代码;面向日常消费场景 |
| [BrowserGym](https://github.com/ServiceNow/BrowserGym) | Web agent | 无头沙盒 | — | 云端一致;录制真实用户轨迹 |
| [Mind2Web](https://github.com/OSU-NLP-Group/Mind2Web) | Web 导航 | 静态轨迹 | 2,350 | 动态真实站点,不回放录像 |
| [Online-Mind2Web](https://github.com/OSU-NLP-Group/Online-Mind2Web) | 实时 Web 导航 | 真实站点 | 300 | V1+V2 共 283 任务规模接近,但提供完整 5 层录制 |
| [VisualWebArena](https://jykoh.com/vwa) | 视觉 Web 任务 | 自建沙盒(3 站点) | 910 | 真实网站完整视觉层 vs 3 个托管站点 |
| [WebVoyager](https://github.com/MinorJerry/WebVoyager) | 真实站点导航 | 真实站点(15) | 643 | 拦截评分 vs 仅 LLM judge,覆盖 144 站点 |
| [TheAgentCompany](https://the-agent-company.com) | 办公流程 | 自建沙盒(6 平台) | 175 | 面向日常消费场景,而非企业沙盒 |

ClawBench 定位:**真实消费级网站、日常任务、端到端录制**。若你想要受控沙盒或回放轨迹,上面这些项目都很出色。若你想知道你的 agent 今天能不能真的点一份外卖、订一张机票,就用 ClawBench。

<br/>

## 架构

<details>
<summary>容器内部结构</summary>

```
┌─────────────────────────────────────────────────┐
│  容器 (Docker / Podman)                          │
│                                                 │
│  ┌───────────┐   DOM 事件    ┌──────────────┐   │
│  │ content.js├──────────────►│ background.js│   │
│  │ (每个标签)│               │  (service    │   │
│  └───────────┘               │   worker)    │   │
│                              └──┬──────┬────┘   │
│                                 │      │        │
│                            动作 │      │ 截图   │
│                                 │      │        │
│  ┌──────────┐            ┌──────▼──────▼────┐   │
│  │  Xvfb    │◄──ffmpeg──►│  FastAPI Server  │   │
│  │ :99      │  x11grab   │  :7878           │   │
│  └──────────┘            └──────────────────┘   │
│                                  │              │
│  ┌──────────┐            ┌───────▼─────────┐    │
│  │ Chromium │            │     /data       │    │
│  │ :9222 CDP│            │  actions.jsonl  │    │
│  └──────────┘            │  requests.jsonl │    │
│                          │  screenshots/   │    │
│                          │  recording.mp4  │    │
│                          └─────────────────┘    │
└─────────────────────────────────────────────────┘
```

</details>

<br/>

# <img src="static/icons/terminal.svg" width="28" height="28"> 命令行

```bash
# 交互式 TUI (推荐):
./run.sh

# 单次运行:
uv run clawbench-run test-cases/v1/001-daily-life-food-uber-eats claude-sonnet-4-6

# 人工模式 (通过 noVNC 控制浏览器):
uv run clawbench-run test-cases/v1/001-daily-life-food-uber-eats --human

# 批量运行 (所有模型 x 用例 1-50, 3 个并发):
uv run clawbench-batch --all-models --case-range 1-50 --max-concurrent 3

# 批量运行 test-cases/v1/ 中的全部 V1 任务:
uv run clawbench-batch --models claude-sonnet-4-6 --all-cases --max-concurrent 3

# 批量运行 test-cases/v2/ 中的全部 V2 任务:
uv run clawbench-batch --models claude-sonnet-4-6 --cases-suite v2 --all-cases --max-concurrent 3

# 批量运行自定义 case 目录:
uv run clawbench-batch --models claude-sonnet-4-6 --cases-dir custom-cases --all-cases
```

V1 任务位于 [`test-cases/v1/`](test-cases/v1/)（153 个任务）。V2 任务位于 `test-cases/v2/`（130 个任务），Lite 位于 `test-cases/v1-lite/`（20 个任务）。所有 suite 都使用 [`test-cases/task.schema.json`](test-cases/task.schema.json)。测试用例编写细节见 [CONTRIBUTING.md](CONTRIBUTING.md)；输出结构与评测流程见 [eval/README.md](eval/README.md)。

<br/>

# <img src="static/icons/chart-bar.svg" width="28" height="28"> 测评

测评是**运行之后**的步骤 -- 先运行智能体收集轨迹,再将轨迹与人类参考运行进行对比评估。

```
 1. 运行智能体 (根 uv 包)            2. 测评 (eval/)
 ────────────────────────           ────────────────────────────────
 ./run.sh / clawbench-batch   ──►    Claude Code 子代理对比
 生成 test-output/                  智能体 vs 人类轨迹
   含五层录制数据                    按 eval/agentic_eval.md rubric 判定
```

测评器将智能体轨迹与人类参考轨迹在五层录制数据（视频、截图、HTTP 流量、浏览器动作、智能体消息）上进行逐步对比,输出 PASS/FAIL 及带证据的判定理由。

完整测评指南和 Claude Code prompt 模板详见 [eval/README.md](eval/README.md)。

<br/>

# <img src="static/icons/circle-question.svg" width="28" height="28"> FAQ

<details>
<summary><b>每次运行会产生什么数据?</b></summary>

每次会话会在 `/data/` 下记录五层同步数据:

| 层 | 文件 | 描述 |
|-------|------|-------------|
| 会话回放 | `recording.mp4` | 完整的会话视频 (H.264, 15fps) |
| 动作截图 | `screenshots/*.png` | 每个浏览器动作的带时间戳 PNG |
| 浏览器动作 | `actions.jsonl` | 每个 DOM 事件 (click, keydown, input, pageLoad, scroll 等) |
| HTTP 流量 | `requests.jsonl` | 每个 HTTP 请求,包含 headers、body 和查询参数 |
| 智能体消息 | `agent-messages.jsonl` | 完整的智能体对话记录 (思考、文本、工具调用) |

对于 Pi harness，`agent-messages.jsonl` 会保存经过过滤的 Pi JSON mode 输出，包括 `message_start` / `message_end` 事件、`tool_execution_*` 事件、工具调用 content block，以及所选模型输出 reasoning 时的 `thinking` block。流式 `message_update` 片段（包括 `*_delta` 行）会被省略，因为完整 assistant message 已经保存在 `message_end` 事件中。

Pi 的 `agent.log`、`proxy.log` 等 harness 诊断日志不会复制到最终的 `data/` 目录。

拦截结果保存在 `interception.json` 中。

</details>

<details>
<summary><b>请求拦截器如何工作?</b></summary>

拦截器会阻止关键的、不可逆的 HTTP 请求 (结账、表单提交、邮件发送) 以防止真实副作用。它通过 CDP 的 `Fetch` 域连接到 Chrome,并将请求与评测 schema (`url_pattern` 正则 + `method` + 可选的 `body`/`params`) 进行匹配。命中时,它会将被阻止的请求保存到 `interception.json`,杀掉智能体并停止录制。

拦截器**不**验证任务完成 -- 评测由独立的评估器在会话结束后处理。

对于在支付墙后的任务 (智能体没有有效的信用卡),评测 schema 使用一个永不匹配的占位模式,因此会话会一直运行到超时。

</details>

<details>
<summary><b>合成用户档案是什么?</b></summary>

每个容器都有一个 `/my-info/` 目录,包含一个虚拟用户身份 (Alex Green): 个人信息 JSON、邮箱凭证和简历 PDF。邮箱是每次运行时新创建的一次性 PurelyMail 地址。智能体在需要填写表单、注册账号等时会读取这些文件。

源模板: `src/clawbench/runtime/shared/alex_green_personal_info.json` (档案) 和 `src/clawbench/utils/resume_template.json` (简历)。

</details>

<details>
<summary><b>可以用 Podman 代替 Docker 吗?</b></summary>

可以。设置 `export CONTAINER_ENGINE=podman`。框架会自动检测可用的引擎。Podman 无需 root 权限。

</details>

<details>
<summary><b>智能体可以使用哪些工具?</b></summary>

所有支持的 harness 都运行在同一个容器录制和拦截环境里。CLI/MCP harness 只暴露浏览器工具和一组受限的只读 shell 命令 (`ls`、`cat`、`find`、`grep`、`head`、`tail`、`jq`、`wc` 等)，可能绕过浏览器的命令 (`curl`、`python`、`node`、`wget`) 会被阻止。Hermes 和 Pi 使用原生 browser/file 工具并直接连接到同一个 ClawBench Chrome CDP 端点。Pi harness 会刻意只 allowlist 只读文件工具和浏览器交互工具；`bash`、`write`、`edit`、`browser_http_get`、`browser_run_script` 不会启用。智能体指令也明确要求只通过浏览器完成任务。

</details>

<details>
<summary><b>如何添加新的测试用例?</b></summary>

参见 [CONTRIBUTING.md](CONTRIBUTING.md)。简言之: 在目标语料目录下创建目录 (`test-cases/v1/` 用于 V1,`test-cases/v2/` 用于 V2),编写符合 `test-cases/task.schema.json` 的 `task.json`,定义评测 schema,用人工模式测试,然后提交 PR。

</details>

<br/>

## 贡献

我们特别欢迎第一次参与开源的贡献者。如果你平时在网上订过外卖、预约过医生、填过表单,你就已经具备写一个测试用例的能力 —— 大部分 PR 只是单个 JSON 文件,通常一天内合并。

**上手快的几件事:**

- [新增一个测试用例](CONTRIBUTING.md#adding-a-new-test-case)(约 30 分钟,不需要懂容器)
- [新增一个类别](CONTRIBUTING.md#what-were-looking-for) 覆盖 10+ 个任务 &rarr; 获邀成为下一版论文共同作者
- [提交一个新模型](CONTRIBUTING.md#what-were-looking-for) 上公共 leaderboard
- 浏览 [good first issues](https://github.com/reacher-z/ClawBench/labels/good%20first%20issue)

详见 [CONTRIBUTING.md](CONTRIBUTING.md),包含完整流程和贡献者致谢政策。

## 社区

欢迎来和研究者、开发者、贡献者一起讨论真实世界的浏览器 agent。

<table>
<tr>
<td align="center" width="33%">
<a href="https://discord.gg/clawbench">
<img src="https://img.shields.io/badge/Discord-Join-5865F2?style=for-the-badge&logo=discord&logoColor=white" alt="Discord">
</a>
<br/>
<sub><b>English community</b><br/>Agent builders, researchers, contributors</sub>
</td>
<td align="center" width="33%">
<a href="static/community/wechat_grp_422.jpg">
<img src="https://img.shields.io/badge/%E5%BE%AE%E4%BF%A1%E7%BE%A4-%E5%8A%A0%E5%85%A5-07C160?style=for-the-badge&logo=wechat&logoColor=white" alt="微信群">
</a>
<br/>
<sub><b>中文社区</b><br/>研究者、开发者、贡献者交流</sub>
</td>
<td align="center" width="33%">
<a href="https://github.com/reacher-z/ClawBench/discussions">
<img src="https://img.shields.io/badge/GitHub-Discussions-181717?style=for-the-badge&logo=github&logoColor=white" alt="GitHub Discussions">
</a>
<br/>
<sub><b>异步问答</b><br/>可搜索 / 长期保存</sub>
</td>
</tr>
</table>

Discord 和 GitHub Discussions 可用于持续交流；微信群请使用上方二维码链接。

## 常见问题

**ClawBench 是什么?**
ClawBench 是一个开源的 AI browser agent 基准 —— 即那些驱动真实浏览器去完成用户任务的系统(基于 GPT、Claude,或开源模型)。V1 衡量 agent 是否真的完成了 153 项日常在线任务,涵盖 144 个真实网站;V2 在 `test-cases/v2/` 中新增 130 项任务。它衡量的是端到端完成情况,而不是 agent 产生的文本看起来是否对。

**ClawBench 覆盖哪些任务?**
15 个生活类别:外卖、订票、投简历、购物、租房、邮件与日历管理、学术研究、软件开发、学习平台等等。每一项都是一个普通人在普通的一周里、在真实网站上可能做的事。

**153 个任务够评测吗?**
够作为 V1 的 benchmark 信号:这 153 项任务覆盖 144 个真实网站和 15 个生活类别,而且完整跑一遍成本很高,因为每次运行都要启动隔离容器、访问真实网站、记录五层数据,并在运行后对照人工参考轨迹评判。V2 在 `test-cases/v2/` 里又补充了 130 项任务。想低成本试跑时,可以先用 20 题精选子集 [`test-cases/v1-lite/`](test-cases/v1-lite/)。

**任务成功如何判定?**
每个任务运行在隔离的浏览器容器中,并进行五层录制:视频、截图、网络请求、浏览器动作和 agent 消息。原始 V1 结果由评测器将 agent 轨迹与人工参考运行对照,并基于录制证据给出 PASS / FAIL。V2 和较新的 leaderboard 行采用两阶段评分:首先由请求拦截器判断最终被拦截的 HTTP 请求是否匹配任务的 URL / method schema;然后由 LLM judge 判断该请求 payload 是否真正满足自然语言任务要求。

**账号登录、注册和初始任务环境如何处理?**
每次运行都会获得一套合成用户档案和一个新的一次性 PurelyMail 邮箱。如果任务需要注册,agent 通常从头开始注册,并使用提供的身份信息和邮箱。如果任务依赖初始文件或工作区上下文,这些文件会放在该任务的 `extra_info/` 目录中,并在运行时挂载给 agent。

**真实网站发生变化怎么办?**
真实网站变化本身就是 ClawBench 想要评测的一部分:我们关心的是 agent 能否处理生产网站,而不是冻结的静态页面。因此,网站改版、可用性变化、风控系统或不同流程都可能影响运行结果。可复现性来自公开的任务定义、eval schema、run metadata 和五层 trace;如果要研究网站漂移,也可以跨时间重复运行同一批任务。

**CAPTCHA / 人机校验造成的失败如何处理?**
如果 agent 遇到 CAPTCHA,它必须尝试解决。我们观察到一些前沿模型可以解决部分 CAPTCHA。CAPTCHA 失败可能来自模型行为、浏览器控制栈限制,也可能来自网站自己的风控。trace 数据集可以让这些失败被检查。

**目前最高分是多少?**
33.3% —— 大约三分之一的任务完成率 —— 来自我们评测过的最强前沿模型。大多数任务仍能击败我们测试过的每一个模型;提升空间真实存在,基准尚未饱和。

**公开模型结果是基于哪个 harness 跑的?**
仓库默认 harness 是 `openclaw`,但 leaderboard 每一行都会显式记录 harness。V1 结果使用 OpenClaw;较新的运行可能使用 Hermes 或其他支持的 harness。比较模型时请同时查看 `harness` 列,因为模型和 harness 是两个独立实验维度。

**ClawBench 和 OpenClaw 深耦合吗?**
不深耦合。OpenClaw 是默认 harness,但 ClawBench 支持 `src/clawbench/runtime/harnesses/` 中列出的可替换 harness。

**支持 CLI agent 吗?**
支持。ClawBench 评测的是浏览器任务完成情况,但 CLI / coding-agent harness 可以用原生工具或 MCP 驱动同一个被录制和拦截的 Chromium 会话。

**如何复现已发表的分数?**
在源码 checkout 中配置好 `models/models.yaml` 后运行 `uv run clawbench`。TUI 会构建容器镜像，并在你选择的模型上运行本地任务。批量运行 V1 用 `--all-cases`；运行 V2 用 `--cases-suite v2 --all-cases`；低成本试跑 Lite 用 `--cases-suite v1-lite --all-cases`。

**会更新新模型结果吗?**
会。新模型可以通过贡献流程和 issue 提交 / 请求测试。公开结果会在完整运行完成后加入;如果是未跑完整个语料的结果,应明确标注为 partial。

**在真实网站上运行 ClawBench 安全吗?**
runner 使用加固的容器,内置请求拦截器,默认阻止下单付款、注册账号、发送邮件等不可逆动作。需要*模拟*这些动作的任务(比如"加入购物车并结账")会在最后一个可逆步骤终止。若你的研究确实需要,可以按任务放宽拦截器。

**可以贡献新任务或新 harness 吗?**
可以。V1 任务放在 `test-cases/v1/`;V2 任务放在 `test-cases/v2/`;Lite 任务放在 `test-cases/v1-lite/`。测试用例 schema 和验证流程详见 `CONTRIBUTING.md`。

**ClawBench 和 HarnessBench 是什么关系?**
同一套评分管线,正交维度。ClawBench 固定 harness、比较不同模型;HarnessBench 固定模型、比较不同 harness。两者共享 153 项任务集、五层录制和 agentic evaluator —— 分数可直接相互比较。

## 引用

如果你在研究中使用了 ClawBench,请引用:

```bibtex
@misc{zhang2026clawbench,
  title         = {ClawBench: Can AI Agents Complete Everyday Online Tasks?},
  author        = {Yuxuan Zhang and Yubo Wang and Yipeng Zhu and Penghui Du and Junwen Miao and Xuan Lu and Wendong Xu and Yunzhuo Hao and Songcheng Cai and Xiaochen Wang and Huaisong Zhang and Xian Wu and Yi Lu and Minyi Lei and Kai Zou and Huifeng Yin and Ping Nie and Liang Chen and Dongfu Jiang and Wenhu Chen and Kelsey R. Allen},
  year          = {2026},
  eprint        = {2604.08523},
  archivePrefix = {arXiv},
  primaryClass  = {cs.AI},
  url           = {https://arxiv.org/abs/2604.08523}
}
```

## 核心贡献者

<table>
<tr>
<td align="center">
<a href="https://github.com/reacher-z">
<img src="https://github.com/reacher-z.png" width="80" height="80" style="border-radius:50%"><br/>
<sub><b>Yuxuan Zhang</b></sub>
</a>
</td>
<td align="center">
<a href="https://github.com/Wyyyb">
<img src="https://github.com/Wyyyb.png" width="80" height="80" style="border-radius:50%"><br/>
<sub><b>Yubo Wang</b></sub>
</a>
</td>
<td align="center">
<a href="https://github.com/Perry2004">
<img src="https://github.com/Perry2004.png" width="80" height="80" style="border-radius:50%"><br/>
<sub><b>Perry Zhu</b></sub>
</a>
</td>
<td align="center">
<a href="https://github.com/eternaldolphin">
<img src="https://github.com/eternaldolphin.png" width="80" height="80" style="border-radius:50%"><br/>
<sub><b>Penghui Du</b></sub>
</a>
</td>
<td align="center">
<a href="https://github.com/MEKSAAA">
<img src="https://github.com/MEKSAAA.png" width="80" height="80" style="border-radius:50%"><br/>
<sub><b>Junwen Miao</b></sub>
</a>
</td>
</tr>
</table>

## 指导老师

<table>
<tr>
<td align="center">
<a href="https://github.com/k-r-allen">
<img src="https://github.com/k-r-allen.png" width="80" height="80" style="border-radius:50%"><br/>
<sub><b>Kelsey R. Allen</b></sub>
</a>
</td>
<td align="center">
<a href="https://github.com/wenhuchen">
<img src="https://github.com/wenhuchen.png" width="80" height="80" style="border-radius:50%"><br/>
<sub><b>Wenhu Chen</b></sub>
</a>
</td>
<td align="center">
<a href="https://github.com/jdf-prog">
<img src="https://github.com/jdf-prog.png" width="80" height="80" style="border-radius:50%"><br/>
<sub><b>Dongfu Jiang</b></sub>
</a>
</td>
<td align="center">
<a href="https://github.com/chenllliang">
<img src="https://github.com/chenllliang.png" width="80" height="80" style="border-radius:50%"><br/>
<sub><b>Liang Chen</b></sub>
</a>
</td>
</tr>
</table>

## 支持 ClawBench

如果 ClawBench 对你的研究或产品工作有帮助，
最有用的支持就是**[给仓库点一个 Star](https://github.com/reacher-z/ClawBench)** ——
这能让更多 AI agent 研究者发现这个 benchmark，也帮我们持续投入数据集维护。

<p align="center">
<a href="https://github.com/reacher-z/ClawBench">
<img src="https://img.shields.io/badge/%E2%98%85%20Star%20this%20repo-181717?style=for-the-badge&logo=github&logoColor=white" alt="Star this repo">
</a>
</p>

欢迎贡献 —— 新的 test case、bug 修复，或者是我们还没评测过的模型结果提交。参见 [`CONTRIBUTING.md`](CONTRIBUTING.md)。

<p align="center">
<a href="https://github.com/reacher-z/ClawBench/graphs/contributors">
<img src="https://contrib.rocks/image?repo=reacher-z/ClawBench" alt="Contributors">
</a>
</p>

## Star 历史

<a href="https://star-history.com/#reacher-z/ClawBench&Date">
  <picture>
    <source media="(prefers-color-scheme: dark)" srcset="https://api.star-history.com/svg?repos=reacher-z/ClawBench&type=Date&theme=dark" />
    <source media="(prefers-color-scheme: light)" srcset="https://api.star-history.com/svg?repos=reacher-z/ClawBench&type=Date" />
    <img alt="ClawBench Star 历史" src="https://api.star-history.com/svg?repos=reacher-z/ClawBench&type=Date" width="600" />
  </picture>
</a>

## 许可证与致谢

Apache 2.0 -- 详见 [LICENSE](LICENSE)。

基于以下开源项目构建: [OpenClaw](https://github.com/openclaw/openclaw)、[opencode](https://opencode.ai)、[Claude Code](https://docs.anthropic.com/en/docs/claude-code)、[Claude in Chrome](https://code.claude.com/docs/en/chrome) 扩展、[OpenAI Codex CLI](https://github.com/openai/codex)、[browser-use](https://github.com/browser-use/browser-use)、[claw-code](https://github.com/ultraworkers/claw-code)、[Hermes Agent](https://github.com/NousResearch/hermes-agent)，以及带 [pi-browser-harness](https://pi.dev/packages/pi-browser-harness) 的 [Pi](https://pi.dev/)（可选 harness），[Microsoft Playwright MCP](https://github.com/microsoft/playwright-mcp)（opencode、claude-code、codex 和 claw-code harness 的浏览器控制桥），[LiteLLM](https://github.com/BerriAI/litellm)（claude-code、claude-code-chrome-extension、codex、browser-use、claw-code 和 pi harness 的 API 转换代理），[noVNC](https://github.com/novnc/noVNC) (MPL 2.0)，以及 [websockify](https://github.com/novnc/websockify) (LGPL 3.0)。
