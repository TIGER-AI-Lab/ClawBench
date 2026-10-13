# Download tasks and traces

[← ClawBench](../README.md) · [中文](data.zh-CN.md)

## <img src="../assets/icons/layer-group.svg" width="20" height="20"> Datasets

ClawBench ships **three** Hugging Face datasets — task definitions plus full execution traces for V1 and V2. All open, downloadable in one command.

| Dataset | What's in it | Get it |
| --- | --- | --- |
| **[NAIL-Group/ClawBench](https://huggingface.co/datasets/NAIL-Group/ClawBench)** _(mirrored at [TIGER-Lab/ClawBench](https://huggingface.co/datasets/TIGER-Lab/ClawBench))_ | Task definitions, rubrics, and metadata for V1 and V2 — what to attempt and how it's judged. | `hf download --repo-type dataset NAIL-Group/ClawBench` |
| **[NAIL-Group/ClawBenchV1Trace](https://huggingface.co/datasets/NAIL-Group/ClawBenchV1Trace)** | One directory per V1 model run: `recording.mp4`, `requests.jsonl`, `actions.jsonl`, `agent-messages.jsonl`, `interception.json`, `run-meta.json`. | `hf download --repo-type dataset NAIL-Group/ClawBenchV1Trace` |
| **[TIGER-Lab/ClawBenchV2Trace](https://huggingface.co/datasets/TIGER-Lab/ClawBenchV2Trace)** | Same 5-layer bundle for **V2** runs. Rolling — new models added as they're evaluated. | `hf download --repo-type dataset TIGER-Lab/ClawBenchV2Trace` |

> **Build with the traces:** See the [Trace Cookbook](trace-cookbook.md) for download recipes, data schemas, and research directions.

> The trace datasets are large; use `hf download --include "<pattern>"` to pull a single model or a single task.

> **🏆 Live leaderboard:** [`claw-bench.com/leaderboard`](https://claw-bench.com/leaderboard) (V2 default, two-stage scoring — interception + LLM judge). Full scoring formula in [`eval/scoring.md`](../eval/scoring.md). Add your run: PR to [`leaderboard/results.csv`](https://huggingface.co/datasets/TIGER-Lab/ClawBench/blob/main/leaderboard/results.csv).
