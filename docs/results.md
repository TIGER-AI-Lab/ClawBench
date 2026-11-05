# Results archive

The README shows the current V2 leaderboard under the Hermes harness and the overall paper results. This page keeps the other published tables: V2 under OpenClaw, V1 under the Hermes harness, the per-category breakdown of the paper results, and the V1 task categories. The [live leaderboard](https://claw-bench.com/leaderboard) has the newest runs.

Compare scores only within the same corpus revision, harness, and rubric. The scoring formula is in [`eval/scoring.md`](../eval/scoring.md).

## V2 · OpenClaw harness

One model.

| Rank  | Model   | Harness  | Intercepted | Reward (lenient) | Reward (strict) | Pass / Total |
| :---: | ------- | -------- | ----------: | ---------------: | --------------: | -----------: |
|   1   | glm-5.1 | openclaw |        0.0% |             0.0% |            0.0% |      0 / 130 |

## V1 · Hermes harness

Six frontier models under the original paper rubric.

| Rank  | Model                     | Harness | Pass Rate | Pass / Total |
| :---: | ------------------------- | ------- | --------: | -----------: |
|   1   | claude-opus-4-6           | hermes  |     61.4% |     94 / 153 |
|   2   | claude-sonnet-4-6         | hermes  |     56.9% |     87 / 153 |
|   3   | claude-haiku-4-5-20251001 | hermes  |     30.1% |     46 / 153 |
|   4   | gpt-5.4-2026-03-05        | hermes  |     25.5% |     39 / 153 |
|   5   | gpt-5.4-mini-2026-03-17   | hermes  |     24.8% |     38 / 153 |
|   6   | kimi-k2.5                 | hermes  |     17.6% |     27 / 153 |

V1 Pass Rate is from the original paper rubric (Claude Code agentic-eval subagent comparing each run against human reference trajectories under `eval/agentic_eval.md`). The two-stage Reward (interception + `deepseek/deepseek-v4-pro` lenient judge) for V1 will appear here once V1 trace bundles are re-judged.

### V1 per-category breakdown

Claude Sonnet 4.6 and five other models, by category.

| Rank  | Model                 | Overall  |  Daily   | Finance  |   Work   |   Dev    | Academic |  Travel  |  Social  |   Pets   |
| :---: | --------------------- | :------: | :------: | :------: | :------: | :------: | :------: | :------: | :------: | :------: |
|   1   | **Claude Sonnet 4.6** | **33.3** |   44.2   | **50.0** |   19.0   |   11.1   | **50.0** |   23.1   | **38.9** | **18.2** |
|   2   | GLM-5                 |   24.2   | **30.8** |   16.7   | **38.1** |   16.7   |   28.6   |   0.0    |   16.7   | **18.2** |
|   3   | Gemini 3 Flash        |   19.0   |   15.4   |   33.3   |   23.8   | **22.2** |   28.6   | **30.8** |   11.1   |   0.0    |
|   4   | Claude Haiku 4.5      |   18.3   |   15.4   |   22.2   |   19.0   | **27.8** |   21.4   |   7.7    |   16.7   | **18.2** |
|   5   | GPT-5.4               |   6.5    |   9.6    |   0.0    |   0.0    |   11.1   |   7.1    |   7.7    |   0.0    |   9.1    |
|   6   | Gemini 3.1 Flash Lite |   3.3    |   1.9    |   0.0    |   0.0    |   5.6    |   14.3   |   0.0    |   0.0    |   9.1    |

## V1 task categories

15 categories, 152 tasks.

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

Codex and Claude Code runs on V2, and the V1 OpenClaw aggregate, are still in flight — they land on the [live leaderboard](https://claw-bench.com/leaderboard) first.
