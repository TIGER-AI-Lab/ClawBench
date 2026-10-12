# 真实运行：作答、拦截与评分

[← ClawBench](README.zh-CN.md) · [English](demo.md)

这是一条发布在 ClawBench V2 Traces 中的 **Claude Opus 4.7 / Hermes** 运行，网站为 **Khan Academy**，任务为 **V2-1122**。任务要求进入 Algebra 1 → Linear equations & graphs → Solutions to 2-variable equations，并回答第一道练习题。

[![代数练习录屏与保存的评测证据](../assets/demo/task-1122-poster.png)](../assets/demo/task-1122.mp4)

[播放 / 暂停 MP4](../assets/demo/task-1122.mp4) · [GIF 动图](../assets/demo/task-1122.gif) · [完整 3 分 38 秒录屏](https://huggingface.co/datasets/TIGER-Lab/ClawBenchV2Trace/blob/bb88da2b8a94044df7888d79c1ad4c7e88949043/batch-20260509-202734/claude-opus-4-7/hermes-v2-1122-education-course-khanacademy-claude-opus-4-7-20260509-233452/data/recording.mp4)

## 片段中发生了什么

| 步骤 | 原始记录 |
| --- | --- |
| 选择答案 | 动作日志在 `2026-05-09T23:35:53.131Z` 记录了选择 **D**。 |
| 点击 **Check** | 随后的提交点击记录于 `2026-05-09T23:35:59.287Z`。 |
| 拦截请求 | `intercepted: true`；`POST /api/internal/graphql/attemptProblem`；`operationName: attemptProblem`；`problemNumber: 1`。 |
| 查看判定 | 公开的 `judge.json` 保存了 `match: true`，judge 为 `deepseek/deepseek-v4-pro`。 |

保存的判定理由是：请求提交了指定练习第一题的答案。此页展示原始保存的判定；记录中的 lenient/strict rubric 信息未指定。

## 剪辑与来源

浏览器画面取自原始录屏的 **00:51–01:08**，裁剪至练习区域，以 **2 倍速**播放；随后展示 **3 秒**请求证据和 **4 秒**判定证据，总时长 **15.5 秒**。两个证据面板依据原始 JSON 制作，属于编辑说明。完整录屏中还包含其他导航和重试。

录屏来自 [TIGER-Lab/ClawBenchV2Trace](https://huggingface.co/datasets/TIGER-Lab/ClawBenchV2Trace)，数据集卡片列出的许可证为 Apache-2.0；录制的网站界面为 Khan Academy。README 为减少动态效果的偏好提供静态预览，也提供可暂停的 MP4。

证据面板摘录 endpoint、method、operationName、题号和判定。完整证据可通过下方源文件链接访问。

## 固定版本的证据

数据集版本：`bb88da2b8a94044df7888d79c1ad4c7e88949043`。[机器可读清单](../assets/demo/source.json)同时保存了剪辑参数和展示字段。

| 原始文件 | SHA-256 |
| --- | --- |
| [recording.mp4](https://huggingface.co/datasets/TIGER-Lab/ClawBenchV2Trace/blob/bb88da2b8a94044df7888d79c1ad4c7e88949043/batch-20260509-202734/claude-opus-4-7/hermes-v2-1122-education-course-khanacademy-claude-opus-4-7-20260509-233452/data/recording.mp4) | `23f9c7a33184378ac1b410a508428d5eaf0461f317ba5513c6472f93416bfda4` |
| [actions.jsonl](https://huggingface.co/datasets/TIGER-Lab/ClawBenchV2Trace/blob/bb88da2b8a94044df7888d79c1ad4c7e88949043/batch-20260509-202734/claude-opus-4-7/hermes-v2-1122-education-course-khanacademy-claude-opus-4-7-20260509-233452/data/actions.jsonl) | `65c72e322f87f40af41d0aca0a4a48f0e46ce14f88d3ba55fb1aae8e87e629cd` |
| [interception.json](https://huggingface.co/datasets/TIGER-Lab/ClawBenchV2Trace/blob/bb88da2b8a94044df7888d79c1ad4c7e88949043/batch-20260509-202734/claude-opus-4-7/hermes-v2-1122-education-course-khanacademy-claude-opus-4-7-20260509-233452/data/interception.json) | `649ad2c3fb60726f9e4eb3fb87337eeb95f5ad9186a8bad23c36c60a9a5bc03b` |
| [judge.json](https://huggingface.co/datasets/TIGER-Lab/ClawBenchV2Trace/blob/bb88da2b8a94044df7888d79c1ad4c7e88949043/batch-20260509-202734/claude-opus-4-7/hermes-v2-1122-education-course-khanacademy-claude-opus-4-7-20260509-233452/data/judge.json) | `3552351f293b5427b54147c4b824374d8494e662193959d0aac03f7053459734` |

## 为什么需要两个阶段

另一条 [V2-1033 导航运行](https://huggingface.co/datasets/TIGER-Lab/ClawBenchV2Trace/blob/bb88da2b8a94044df7888d79c1ad4c7e88949043/batch-20260509-202734/claude-opus-4-7/hermes-v2-1033-education-learning-registration-khanacademy-claude-opus-4-7-20260509-230313/data/interception.json)成功触发了拦截，但[保存的 judge 判定](https://huggingface.co/datasets/TIGER-Lab/ClawBenchV2Trace/blob/bb88da2b8a94044df7888d79c1ad4c7e88949043/batch-20260509-202734/claude-opus-4-7/hermes-v2-1033-education-learning-registration-khanacademy-claude-opus-4-7-20260509-230313/data/judge.json)为 `match: false`：捕获的 URL 打开了相关文章，而非任务要求的课程。因此，请分别报告拦截和判定完成两个结果。

## 重新生成素材

在仓库根目录运行以下命令。生成器会先核对四份源文件的哈希和展示字段；下载的源文件保存在指定本地目录中。如需使用已安装的 Chrome，可加 `--browser-executable /path/to/chrome`。

```bash
uvx --from huggingface_hub hf download TIGER-Lab/ClawBenchV2Trace \
  "batch-20260509-202734/claude-opus-4-7/hermes-v2-1122-education-course-khanacademy-claude-opus-4-7-20260509-233452/data/recording.mp4" \
  "batch-20260509-202734/claude-opus-4-7/hermes-v2-1122-education-course-khanacademy-claude-opus-4-7-20260509-233452/data/actions.jsonl" \
  "batch-20260509-202734/claude-opus-4-7/hermes-v2-1122-education-course-khanacademy-claude-opus-4-7-20260509-233452/data/interception.json" \
  "batch-20260509-202734/claude-opus-4-7/hermes-v2-1122-education-course-khanacademy-claude-opus-4-7-20260509-233452/data/judge.json" \
  --repo-type dataset --revision bb88da2b8a94044df7888d79c1ad4c7e88949043 --local-dir ./demo-source

uv run --no-project --with playwright --with imageio-ffmpeg \
  python -m playwright install chromium
uv run --no-project --with playwright --with imageio-ffmpeg \
  python assets/demo/build_demo.py \
  --source-dir "./demo-source/batch-20260509-202734/claude-opus-4-7/hermes-v2-1122-education-course-khanacademy-claude-opus-4-7-20260509-233452/data"
```
