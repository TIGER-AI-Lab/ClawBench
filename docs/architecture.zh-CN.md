# 录制与运行时架构

[← ClawBench](README.zh-CN.md) · [English](architecture.md)

## <img src="../assets/icons/screwdriver-wrench.svg" width="20" height="20"> 工作流程

<p align="center">
  <picture>
    <source media="(max-width: 1200px) and (prefers-color-scheme: dark)" srcset="../assets/workflow-zh-mobile-dark.svg" width="460">
    <source media="(max-width: 1200px)" srcset="../assets/workflow-zh-mobile-light.svg" width="460">
    <source media="(prefers-color-scheme: dark)" srcset="../assets/workflow-zh-dark.svg">
    <img src="../assets/workflow-zh-light.svg" alt="选择任务、准备浏览器环境、运行智能体、录制并评测任务完成情况。" width="960">
  </picture>
</p>

<details>
<summary><b>容器内部结构</b></summary>

```
┌─────────────────────────────────────────────────┐
│  容器 (Docker / Podman)                         │
│                                                 │
│  ┌──────────┐  CDP Fetch/Runtime/Page 事件      │
│  │ Chromium ├─────────────────────────────┐     │
│  │ :9222 CDP│                             │     │
│  └──────────┘                             │     │
│                                           │     │
│  ┌──────────┐            ┌────────────────▼─┐   │
│  │  Xvfb    │◄──ffmpeg──►│  FastAPI Server  │   │
│  │ :99      │  x11grab   │  :7878           │   │
│  └──────────┘            └──────────────────┘   │
│                                  │              │
│                          ┌───────▼─────────┐    │
│                          │     /data       │    │
│                          │  actions.jsonl  │    │
│                          │  requests.jsonl │    │
│                          │  screenshots/   │    │
│                          │  recording.mp4  │    │
│                          └─────────────────┘    │
└─────────────────────────────────────────────────┘
```

</details>
