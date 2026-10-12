# Historical result snapshots

[← ClawBench](../README.md) · [中文](results.zh-CN.md)

These tables are preserved from the README at revision `23ff392`. They describe different corpora, harnesses, and rubrics; denominators reflect the corpus at run time. For current results, use the [live leaderboard](https://huggingface.co/spaces/TIGER-Lab/ClawBench).

## <img src="../assets/icons/chart-bar.svg" width="20" height="20"> Results

<div align="center">

**ClawBench leaderboard** &nbsp;&middot;&nbsp; by corpus × harness &nbsp;&middot;&nbsp; live at [claw-bench.com](https://claw-bench.com/)

</div>

<details open>
<summary><b>V2 (Hermes)</b> &nbsp;·&nbsp; 8 models &nbsp;·&nbsp; ds-v4-pro judge, lenient + strict</summary>

| Rank  | Model                  | Harness | Intercepted | Reward (lenient) | Reward (strict) | Pass / Total |
| :---: | ---------------------- | ------- | ----------: | ---------------: | --------------: | -----------: |
|   1   | **claude-opus-4-7**    | hermes  |   **54.6%** |        **44.6%** |           24.6% |     58 / 130 |
|   2   | gpt-5.5                | hermes  |       45.4% |            35.4% |           18.5% |     46 / 130 |
|   3   | glm-5.1                | hermes  |       48.5% |            34.6% |           17.7% |     45 / 130 |
|   4   | deepseek-v4-pro        | hermes  |       43.9% |            33.9% |           12.3% |     44 / 130 |
|   5   | openrouter-owl-alpha   | hermes  |       14.6% |             0.0% |            0.0% |      0 / 130 |
|   6   | z-ai/glm-4.5-air:free  | hermes  |        4.6% |             2.3% |            0.8% |      3 / 130 |
|   7   | deepseek-v4-flash:free | hermes  |        3.1% |             2.3% |            0.0% |      3 / 129 |
|   8   | minimax-m2.5:free      | hermes  |        2.3% |             1.5% |            0.0% |      2 / 130 |

**Intercepted** = final HTTP request matched the task's URL/method (Stage 1, deterministic). **Reward (lenient)** = additionally judged by `deepseek/deepseek-v4-pro` to fulfill the instruction under the "no contradiction → match" rubric (Stage 2). **Reward (strict)** = same judge, strict rubric ("ambiguous → mismatch"). Ranked by Intercepted; Reward as tiebreak. Totals reflect the corpus size at run time.

</details>

<details>
<summary><b>V2 (OpenClaw)</b> &nbsp;·&nbsp; 1 model</summary>

| Rank  | Model   | Harness  | Intercepted | Reward (lenient) | Reward (strict) | Pass / Total |
| :---: | ------- | -------- | ----------: | ---------------: | --------------: | -----------: |
|   1   | glm-5.1 | openclaw |        0.0% |             0.0% |            0.0% |      0 / 130 |

</details>

<details>
<summary><b>V1 (Hermes)</b> &nbsp;·&nbsp; 6 frontier models, original paper rubric</summary>

| Rank  | Model                     | Harness | Pass Rate | Pass / Total |
| :---: | ------------------------- | ------- | --------: | -----------: |
|   1   | claude-opus-4-6           | hermes  |     61.4% |     94 / 153 |
|   2   | claude-sonnet-4-6         | hermes  |     56.9% |     87 / 153 |
|   3   | claude-haiku-4-5-20251001 | hermes  |     30.1% |     46 / 153 |
|   4   | gpt-5.4-2026-03-05        | hermes  |     25.5% |     39 / 153 |
|   5   | gpt-5.4-mini-2026-03-17   | hermes  |     24.8% |     38 / 153 |
|   6   | kimi-k2.5                 | hermes  |     17.6% |     27 / 153 |

V1 Pass Rate is from the original paper rubric (Claude Code agentic-eval subagent comparing each run against human reference trajectories under `eval/agentic_eval.md`). The two-stage Reward (interception + `deepseek/deepseek-v4-pro` lenient judge) for V1 will appear here once V1 trace bundles are re-judged.

</details>

<details>
<summary>V1 per-category breakdown (Sonnet 4.6 vs 6-model comparison)</summary>

| Rank  | Model                 | Overall  |  Daily   | Finance  |   Work   |   Dev    | Academic |  Travel  |  Social  |   Pets   |
| :---: | --------------------- | :------: | :------: | :------: | :------: | :------: | :------: | :------: | :------: | :------: |
|   1   | **Claude Sonnet 4.6** | **33.3** |   44.2   | **50.0** |   19.0   |   11.1   | **50.0** |   23.1   | **38.9** | **18.2** |
|   2   | GLM-5                 |   24.2   | **30.8** |   16.7   | **38.1** |   16.7   |   28.6   |   0.0    |   16.7   | **18.2** |
|   3   | Gemini 3 Flash        |   19.0   |   15.4   |   33.3   |   23.8   | **22.2** |   28.6   | **30.8** |   11.1   |   0.0    |
|   4   | Claude Haiku 4.5      |   18.3   |   15.4   |   22.2   |   19.0   | **27.8** |   21.4   |   7.7    |   16.7   | **18.2** |
|   5   | GPT-5.4               |   6.5    |   9.6    |   0.0    |   0.0    |   11.1   |   7.1    |   7.7    |   0.0    |   9.1    |
|   6   | Gemini 3.1 Flash Lite |   3.3    |   1.9    |   0.0    |   0.0    |   5.6    |   14.3   |   0.0    |   0.0    |   9.1    |

</details>

<details>
<summary><b>Task categories</b> &nbsp;·&nbsp; V1: 15 categories, 152 tasks</summary>

| Category                  | Tasks | Example Platforms                                             |
| ------------------------- | :---: | ------------------------------------------------------------- |
| Daily Life                |  21   | Uber Eats, DoorDash, Instacart, Zillow, Craigslist            |
| Entertainment & Hobbies   |  15   | Ticketmaster, AMC Theatres, Topgolf, Crunchyroll              |
| Creation & Initialization |  13   | Squarespace, Wix, Webflow, Ghost, Substack                    |
| Rating & Voting           |  10   | Trustpilot, G2, Goodreads, RateMyProfessors                   |
| Travel                    |   9   | Booking.com, Expedia, Airbnb, TripAdvisor                     |
| Education & Learning      |   9   | Coursera, Udemy, Khan Academy, Duolingo                       |
| Office & Secretary        |   9   | Google Calendar, Slack, Notion, Trello                        |
| Beauty & Personal Care    |   9   | Sephora, Ulta, Glossier                                       |
| Job Search & HR           |   8   | LinkedIn, Greenhouse, Lever, Workday                          |
| Pet & Animal Care         |   7   | Chewy, Petco, Rover                                           |
| Personal Management       |   6   | Mint, YNAB, Todoist                                           |
| Shopping & Commerce       |   6   | Amazon, eBay, Etsy, Target                                    |
| Nonprofit & Charity       |   6   | GoFundMe, DonorsChoose                                        |
| Academia & Research       |   5   | Google Scholar, Semantic Scholar, OpenReview                  |
| Finance & Investment      |   4   | Robinhood, Fidelity, Coinbase                                 |
| Others                    |  15   | Automation, Dev & Tech, Government, Home Services, Automotive |

</details>

<sub>For newer runs and additional harnesses, consult the [live leaderboard](https://huggingface.co/spaces/TIGER-Lab/ClawBench).</sub>
