# ClawBench 与相关工作

[← ClawBench](README.zh-CN.md) · [English](related-work.md)

## ClawBench 与相关工作对比

| Benchmark | 领域 | 环境 | 任务数 | ClawBench 的差异 |
| --- | --- | --- | --- | --- |
| [WebArena](https://webarena.dev) | 合成 web 应用 | 自建副本 | 812 | 真实消费级网站，而非托管副本上的后台 UI |
| [GAIA](https://huggingface.co/datasets/gaia-benchmark/GAIA) | 通用助手 | 闭卷文本 + 工具 | 466 | 以浏览器为中心；端到端任务执行 |
| [SWE-bench](https://www.swebench.com) | 软件工程 | GitHub 仓库 | 2,294 | 非代码；日常消费者工作流 |
| [BrowserGym](https://github.com/ServiceNow/BrowserGym) | Web 智能体 | 无头沙箱 | — | 云端对齐；记录真实用户旅程 |
| [Mind2Web](https://github.com/OSU-NLP-Group/Mind2Web) | Web 导航 | 静态轨迹 | 2,350 | 动态真实网站，而非回放轨迹 |
| [Online-Mind2Web](https://github.com/OSU-NLP-Group/Online-Mind2Web) | 真实 web 导航 | 真实网站 | 300 | 规模相当（V1+V2：281 vs 300），但每次运行都有完整五层录制 |
| [VisualWebArena](https://jykoh.com/vwa) | 视觉 web 任务 | 自建（3 个站点） | 910 | 真实网站 + 完整视觉层（对比 3 个托管应用） |
| [WebVoyager](https://github.com/MinorJerry/WebVoyager) | 真实网站导航 | 真实网站（15 个） | 643 | 拦截判定 vs 仅 LLM judge，覆盖 143 个站点 |
| [TheAgentCompany](https://the-agent-company.com) | 办公工作流 | 自建（6 个平台） | 175 | 消费者日常任务，而非企业沙箱 |

ClawBench 的定位：**真实消费级网站、日常任务、端到端录制**。如果你需要受控沙箱或回放轨迹，上面这些项目都很优秀；如果你想知道你的智能体*今天*能不能真的点一份外卖、订一张机票，那就用这个。
