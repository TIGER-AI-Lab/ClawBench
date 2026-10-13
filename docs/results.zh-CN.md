# 历史评测结果快照

[← ClawBench](README.zh-CN.md) · [English](results.md)

以下表格保留自 README 的 `23ff392` 版本，涉及不同语料、harness 和评分规则；分母反映运行时的语料规模。最新结果请查看[实时排行榜](https://huggingface.co/spaces/TIGER-Lab/ClawBench)。

## <img src="../assets/icons/chart-bar.svg" width="20" height="20"> 实验结果

<div align="center">

**ClawBench 排行榜** &nbsp;&middot;&nbsp; 按语料 × harness 划分 &nbsp;&middot;&nbsp; 实时版见 [claw-bench.com](https://claw-bench.com/)

</div>

<details open>
<summary><b>V2 (Hermes)</b> &nbsp;·&nbsp; 8 个模型 &nbsp;·&nbsp; ds-v4-pro judge，lenient + strict</summary>

| 排名  | 模型                   | Harness | Intercepted | Reward (lenient) | Reward (strict) | 通过 / 总数 |
| :---: | ---------------------- | ------- | ----------: | ---------------: | --------------: | -----------: |
|   1   | **claude-opus-4-7**    | hermes  |   **54.6%** |        **44.6%** |           24.6% |     58 / 130 |
|   2   | gpt-5.5                | hermes  |       45.4% |            35.4% |           18.5% |     46 / 130 |
|   3   | glm-5.1                | hermes  |       48.5% |            34.6% |           17.7% |     45 / 130 |
|   4   | deepseek-v4-pro        | hermes  |       43.9% |            33.9% |           12.3% |     44 / 130 |
|   5   | openrouter-owl-alpha   | hermes  |       14.6% |             0.0% |            0.0% |      0 / 130 |
|   6   | z-ai/glm-4.5-air:free  | hermes  |        4.6% |             2.3% |            0.8% |      3 / 130 |
|   7   | deepseek-v4-flash:free | hermes  |        3.1% |             2.3% |            0.0% |      3 / 129 |
|   8   | minimax-m2.5:free      | hermes  |        2.3% |             1.5% |            0.0% |      2 / 130 |

**Intercepted** = 最终 HTTP 请求命中任务的 URL/method（第一阶段，确定性）。**Reward (lenient)** = 在此基础上由 `deepseek/deepseek-v4-pro` 按"无矛盾即匹配"rubric 判定确实完成了指令（第二阶段）。**Reward (strict)** = 同一 judge，严格 rubric（"有歧义即不匹配"）。按 Intercepted 排序，Reward 作为并列时的次序。总数反映运行当时的语料规模。

</details>

<details>
<summary><b>V2 (OpenClaw)</b> &nbsp;·&nbsp; 1 个模型</summary>

| 排名  | 模型    | Harness  | Intercepted | Reward (lenient) | Reward (strict) | 通过 / 总数 |
| :---: | ------- | -------- | ----------: | ---------------: | --------------: | -----------: |
|   1   | glm-5.1 | openclaw |        0.0% |             0.0% |            0.0% |      0 / 130 |

</details>

<details>
<summary><b>V1 (Hermes)</b> &nbsp;·&nbsp; 6 个前沿模型，论文原始 rubric</summary>

| 排名  | 模型                      | Harness | 通过率 | 通过 / 总数 |
| :---: | ------------------------- | ------- | -----: | -----------: |
|   1   | claude-opus-4-6           | hermes  |  61.4% |     94 / 153 |
|   2   | claude-sonnet-4-6         | hermes  |  56.9% |     87 / 153 |
|   3   | claude-haiku-4-5-20251001 | hermes  |  30.1% |     46 / 153 |
|   4   | gpt-5.4-2026-03-05        | hermes  |  25.5% |     39 / 153 |
|   5   | gpt-5.4-mini-2026-03-17   | hermes  |  24.8% |     38 / 153 |
|   6   | kimi-k2.5                 | hermes  |  17.6% |     27 / 153 |

V1 通过率来自论文原始 rubric（Claude Code agentic-eval 子代理按 `eval/agentic_eval.md` 对照人工参考轨迹）。V1 的两阶段 Reward（拦截 + `deepseek/deepseek-v4-pro` lenient judge）会在 V1 trace 重新评分后补上。

</details>

<details>
<summary>V1 分类别细分（Sonnet 4.6 与 6 模型对比）</summary>

| 排名 | 模型 | 总体 | 日常 | 金融 | 工作 | 开发 | 学术 | 旅行 | 社交 | 宠物 |
|:----:|-------|:------:|:-----:|:-----:|:----:|:---:|:----:|:----:|:----:|:----:|
| 1 | **Claude Sonnet 4.6** | **33.3** | 44.2 | **50.0** | 19.0 | 11.1 | **50.0** | 23.1 | **38.9** | **18.2** |
| 2 | GLM-5 | 24.2 | **30.8** | 16.7 | **38.1** | 16.7 | 28.6 | 0.0 | 16.7 | **18.2** |
| 3 | Gemini 3 Flash | 19.0 | 15.4 | 33.3 | 23.8 | **22.2** | 28.6 | **30.8** | 11.1 | 0.0 |
| 4 | Claude Haiku 4.5 | 18.3 | 15.4 | 22.2 | 19.0 | **27.8** | 21.4 | 7.7 | 16.7 | **18.2** |
| 5 | GPT-5.4 | 6.5 | 9.6 | 0.0 | 0.0 | 11.1 | 7.1 | 7.7 | 0.0 | 9.1 |
| 6 | Gemini 3.1 Flash Lite | 3.3 | 1.9 | 0.0 | 0.0 | 5.6 | 14.3 | 0.0 | 0.0 | 9.1 |

</details>

<details>
<summary><b>任务类别</b> &nbsp;·&nbsp; V1：15 个类别，152 个任务</summary>

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
| 宠物与动物护理 | 7 | Chewy, Petco, Rover |
| 个人管理 | 6 | Mint, YNAB, Todoist |
| 购物与电商 | 6 | Amazon, eBay, Etsy, Target |
| 非营利与慈善 | 6 | GoFundMe, DonorsChoose |
| 学术与研究 | 5 | Google Scholar, Semantic Scholar, OpenReview |
| 金融与投资 | 4 | Robinhood, Fidelity, Coinbase |
| 其他 | 15 | 自动化、开发与技术、政府、家居服务、汽车 |

</details>

<sub>更新的运行结果与其他 harness 请见[实时排行榜](https://huggingface.co/spaces/TIGER-Lab/ClawBench)。</sub>
