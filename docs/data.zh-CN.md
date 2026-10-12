# 下载任务与执行轨迹

[← ClawBench](README.zh-CN.md) · [English](data.md)

## <img src="../assets/icons/layer-group.svg" width="20" height="20"> 数据集

ClawBench 提供 **三个** Hugging Face 数据集 —— 任务定义，以及 V1 / V2 的完整执行 trace。全部开源，一行命令即可下载。

| 数据集 | 内容 | 下载 |
| --- | --- | --- |
| **[NAIL-Group/ClawBench](https://huggingface.co/datasets/NAIL-Group/ClawBench)** _(也镜像在 [TIGER-Lab/ClawBench](https://huggingface.co/datasets/TIGER-Lab/ClawBench))_ | V1 和 V2 的任务定义、评分规则和元数据 —— 即"做什么"和"怎么打分"。 | `hf download --repo-type dataset NAIL-Group/ClawBench` |
| **[NAIL-Group/ClawBenchV1Trace](https://huggingface.co/datasets/NAIL-Group/ClawBenchV1Trace)** | V1 每个模型运行一个目录，内含 `recording.mp4`、`requests.jsonl`、`actions.jsonl`、`agent-messages.jsonl`、`interception.json`、`run-meta.json`。 | `hf download --repo-type dataset NAIL-Group/ClawBenchV1Trace` |
| **[TIGER-Lab/ClawBenchV2Trace](https://huggingface.co/datasets/TIGER-Lab/ClawBenchV2Trace)** | **V2** 运行的同款 5 层数据包。滚动更新 —— 新模型评测完成后持续加入。 | `hf download --repo-type dataset TIGER-Lab/ClawBenchV2Trace` |

> **基于 trace 开展研究：** 参见 [Trace Cookbook](trace-cookbook.md)，了解下载示例、数据结构和研究方向。

> Trace 数据集体积较大；可用 `hf download --include "<pattern>"` 仅拉取某个模型或某个任务。

> **🏆 实时排行榜：** [`claw-bench.com/leaderboard`](https://claw-bench.com/leaderboard)（默认 V2，两阶段评分 —— 拦截 + LLM judge）。完整评分公式见 [`eval/scoring.md`](../eval/scoring.md)。提交你的结果：向 [`leaderboard/results.csv`](https://huggingface.co/datasets/TIGER-Lab/ClawBench/blob/main/leaderboard/results.csv) 提 PR。
