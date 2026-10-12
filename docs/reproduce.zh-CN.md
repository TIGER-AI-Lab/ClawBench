# 复现已发布结果

[← ClawBench](README.zh-CN.md) · [English](reproduce.md)

## <img src="../assets/icons/check-double.svg" width="20" height="20"> 复现排行榜

> **我们的分数是稳定的**：同一模型、同一 judge（`deepseek/deepseek-v4-pro`，lenient rubric）两次独立运行，在 V2 语料上 Intercepted 与 Reward 的差异都在 ±2 个百分点以内。

有 **两条** 路径可以在你自己的机器上验证。

### 路径 A —— 重跑智能体，再评分

验证 *完整链路*（你的智能体 + 我们的 judge）与我们 leaderboard 行是否一致。

```bash
clawbench-batch --models deepseek/deepseek-v4-flash --cases-suite v2 \
  --all-cases --harness hermes --no-judge --output-dir ./my-run
clawbench-rescore ./my-run --judge-model deepseek-v4-pro --rubric both
```

### 路径 B —— 不重跑，直接重判我们发布的 trace

只验证 *judge* 是否与我们一致（便宜，无需智能体算力，适合排查 judge 配置）。

```bash
hf download --repo-type dataset TIGER-Lab/ClawBenchV2Trace \
  --include "batch-aligned-*/deepseek-v4-flash-free/**" --local-dir ./reproduce
clawbench-rescore ./reproduce --judge-model deepseek-v4-pro --rubric both
```

对 leaderboard 上任意模型，路径 B 的一键版本：

```bash
clawbench-reproduce --model deepseek-v4-flash --tolerance 2.0
```

### 通过标准

对 `deepseek-v4-flash:free × hermes × v2`，公开行是 **Intercepted 3.1% / Reward-lenient 2.3% / Reward-strict 0.0%（3 / 129）**。三个指标都落在 ±2 个百分点内即算 **复现成功**。差距更大通常意味着 judge 模型不同、rubric prompt 不同，或 harness 配置漂移 —— 用你的 `eval_results/<batch>/summary.json` 与公开行逐项对比即可定位。

## <img src="../assets/icons/bolt.svg" width="20" height="20"> ClawBench-Lite

**第一次跑？先跑这个。** [`test-cases/v1-lite/`](../test-cases/v1-lite) 是 V1 的 **20 个精选子集**，按站点知名度、真实日常相关度、难度和类别多样性挑选。它对齐了 [browser-use/benchmark](https://github.com/browser-use/benchmark) 的 20-tasks-per-source 规范，用完整 benchmark 一小部分的成本就能拿到可信的信号。

分层：**flagship 9 / core 8 / wildcard 3** —— 覆盖日常生活 (OpenTable, DoorDash, Instacart, TaskRabbit)、娱乐爱好 (Eventbrite, Goodreads, Fandango)、创建初始化 (Asana, Mailchimp, Squarespace)、旅行 (Airbnb)、教育 (LeetCode)、开发技术 (GitHub)、学术研究 (Overleaf)、个人管理 (1Password) 等类别。所有 Lite 任务均由 [`eval/agentic_eval.md`](../eval/agentic_eval.md) 判定，不依赖 `url_pattern` 形态。

用 `--cases-suite v1-lite` 运行，或直接查看 [`test-cases/v1-lite/`](../test-cases/v1-lite) 里的任务文件。
