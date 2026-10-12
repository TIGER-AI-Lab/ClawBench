# 常见问题

[← ClawBench](README.zh-CN.md) · [English](faq.md)

## <img src="../assets/icons/circle-question.svg" width="20" height="20"> 常见问题

### 这是什么

<details>
<summary><b>ClawBench 是什么？</b></summary>

一个开源的 AI browser agent 基准 —— 即那些驱动真实浏览器去完成用户任务的系统（基于 GPT、Claude 或开源模型）。V1 衡量 agent 是否真的完成了 152 项日常在线任务、覆盖 143 个真实网站；V2 在 `test-cases/v2/` 中新增 129 项任务。它衡量的是端到端完成情况，而不是 agent 产生的文本看起来是否对。

</details>

<details>
<summary><b>覆盖哪些任务？</b></summary>

15 个生活类别：外卖、订票、投简历、购物、租房、邮件与日历管理、学术研究、软件开发、学习平台等等。每一项都是一个普通人在普通的一周里、在真实网站上可能做的事。

</details>

<details>
<summary><b>约 150 个任务够评测吗？</b></summary>

够作为 V1 的 benchmark 信号：这些任务覆盖 143 个真实网站和 15 个生活类别，而且完整跑一遍成本很高 —— 每次运行都要启动隔离容器、访问真实网站、记录五层数据，并在运行后对照人工参考轨迹评判。V2 又补充了 129 项任务。想低成本试跑，可以先用 20 题精选子集 [`test-cases/v1-lite/`](../test-cases/v1-lite)。

</details>

<details>
<summary><b>目前最高分是多少？</b></summary>

请查看按语料、harness 和评分规则划分的[实时榜单](https://huggingface.co/spaces/TIGER-Lab/ClawBench)。33.3% 属于历史 V1 论文评测，并非当前所有结果中的最高分。比较成绩时，请使用相同的语料版本、指标和分母。

</details>

<details>
<summary><b>ClawBench 和 HarnessBench 是什么关系？</b></summary>

ClawBench 评测模型 / harness 组合在日常网页任务上的表现。HarnessBench 侧重固定基础模型、比较不同 harness。比较分数时，请列明模型、harness、语料版本、judge 和评分规则。

</details>

### 怎么跑

<details>
<summary><b>每次运行会产生什么数据？</b></summary>

每次会话会在 `/data/` 下记录五层同步数据：

| 层 | 文件 | 描述 |
|-------|------|-------------|
| 会话回放 | `recording.mp4` 或 `run-meta.json` 中的录制 URL | 本地/Kernel H.264 视频，或 Browserbase Session Inspector 回放 |
| 动作截图 | `screenshots/*.png` | 浏览器动作后经限流捕获的带时间戳 PNG |
| 浏览器动作 | `actions.jsonl` | 每个 DOM 事件 (click, keydown, input, pageLoad, scroll 等) |
| HTTP 流量 | `requests.jsonl` | 每个 HTTP 请求，包含 headers、body 和查询参数 |
| 智能体消息 | `agent-messages.jsonl` | 完整的智能体对话记录（思考、文本、工具调用） |

对于 Pi harness，`agent-messages.jsonl` 会保存经过过滤的 Pi JSON mode 输出，包括 `message_start` / `message_end` 事件、`tool_execution_*` 事件、工具调用 content block，以及所选模型输出 reasoning 时的 `thinking` block。流式 `message_update` 片段（包括 `*_delta` 行）会被省略，因为完整 assistant message 已经保存在 `message_end` 事件中。

Pi 的 `agent.log`、`proxy.log` 等 harness 诊断日志不会复制到最终的 `data/` 目录。拦截结果保存在 `interception.json` 中。

</details>

<details>
<summary><b>合成用户档案是什么？</b></summary>

每个容器都有一个 `/my-info/` 目录，包含一个虚拟用户身份（Alex Green）：个人信息 JSON、邮箱凭证和简历 PDF。邮箱是每次运行时新创建的一次性 PurelyMail 地址。智能体在需要填写表单、注册账号等时会读取这些文件。

源模板：`src/clawbench/runtime/shared/alex_green_personal_info.json`（档案）和 `src/clawbench/runner/run_support/resume_template.json`（简历）。

</details>

<details>
<summary><b>账号登录、注册和初始任务环境如何处理？</b></summary>

每次运行都会获得上述合成档案和一个新的一次性邮箱。如果任务需要注册，agent 通常从头开始注册。如果任务依赖初始文件或工作区上下文，这些文件会放在该任务的 `extra_info/` 目录中，并在运行时挂载给 agent。

</details>

<details>
<summary><b>智能体可以使用哪些工具？</b></summary>

所有支持的 harness 都运行在同一个容器录制和拦截环境里。CLI/MCP harness 只暴露浏览器工具和一组受限的只读 shell 命令（`ls`、`cat`、`find`、`grep`、`head`、`tail`、`jq`、`wc` 等），可能绕过浏览器的命令（`curl`、`python`、`node`、`wget`）会被阻止。Hermes 和 Pi 使用原生 browser/file 工具并直接连接到同一个 ClawBench Chrome CDP 端点。Pi harness 会刻意只 allowlist 只读文件工具和浏览器交互工具；`bash`、`write`、`edit`、`browser_http_get`、`browser_run_script` 不会启用。智能体指令也明确要求只通过浏览器完成任务。

</details>

<details>
<summary><b>可以用 Podman 代替 Docker 吗？</b></summary>

可以。设置 `export CONTAINER_ENGINE=podman`，框架会自动检测可用的引擎，Podman 无需 root 权限。（Harbor 运行是例外 —— 它使用 Harbor 自己的 Docker provider。）

</details>

<details>
<summary><b>ClawBench 和 OpenClaw 深耦合吗？支持 CLI agent 吗？</b></summary>

不深耦合；支持。OpenClaw 只是默认 harness，harness 之间可替换 —— 见[快速开始](getting-started.zh-CN.md)里的 harness 表和 `src/clawbench/runtime/harnesses/harnesses.yaml` 注册表。CLI / coding-agent harness 用原生工具或 MCP 驱动同一个被录制和拦截的 Chromium 会话。

</details>

### 评分与安全

<details>
<summary><b>任务成功如何判定？</b></summary>

每个任务运行在隔离的浏览器容器中，并进行五层录制。原始 V1 结果由评测器将 agent 轨迹与人工参考运行对照，并基于录制证据给出 PASS / FAIL。V2 和较新的 leaderboard 行采用两阶段评分：首先由请求拦截器判断最终被拦截的 HTTP 请求是否匹配任务的 URL / method schema；然后由 LLM judge 判断该请求 payload 是否真正满足自然语言任务要求。

</details>

<details>
<summary><b>请求拦截器如何工作？在真实网站上运行安全吗？</b></summary>

拦截器会阻止关键的、不可逆的 HTTP 请求（结账、表单提交、邮件发送）以防止真实副作用。它通过 CDP 的 `Fetch` 域连接到 Chrome，并将请求与评测 schema（`url_pattern` 正则 + `method` + 可选的 `body`/`params`）匹配。命中时会把被阻止的请求保存到 `interception.json`，杀掉智能体并停止录制。需要*模拟*不可逆动作的任务（比如"加入购物车并结账"）会在最后一个可逆步骤终止；若研究需要，可以按任务放宽拦截器。

拦截器**不**验证任务完成 —— 那是运行后独立评测的事。对于在支付墙后的任务（智能体没有有效的信用卡），评测 schema 使用一个永不匹配的占位模式，因此会话会一直运行到超时。

</details>

<details>
<summary><b>公开模型结果是基于哪个 harness 跑的？</b></summary>

仓库默认 harness 是 `openclaw`，但 leaderboard 每一行都会显式记录 harness。V1 结果使用 OpenClaw；较新的运行可能使用 Hermes 或其他支持的 harness。比较模型时请同时查看 `harness` 列，因为模型和 harness 是两个独立实验维度。

</details>

<details>
<summary><b>真实网站发生变化怎么办？</b></summary>

真实网站变化本身就是 ClawBench 想要评测的一部分：我们关心的是 agent 能否处理生产网站，而不是冻结的静态页面。因此网站改版、可用性变化、风控系统或不同流程都可能影响运行结果。可复现性来自公开的任务定义、eval schema、run metadata 和五层 trace；跨时间重复运行同一批任务也可以用来度量网站漂移。

</details>

<details>
<summary><b>CAPTCHA / 人机校验造成的失败如何处理？</b></summary>

如果 agent 遇到 CAPTCHA，它必须尝试解决。我们观察到一些前沿模型可以解决部分 CAPTCHA。CAPTCHA 失败可能来自模型行为、浏览器控制栈限制，也可能来自网站自己的风控。trace 数据集可以让这些失败被逐一检查。

</details>

### 贡献与覆盖

<details>
<summary><b>如何添加新的测试用例？</b></summary>

参见 [CONTRIBUTING.md](../CONTRIBUTING.md)。简言之：在目标语料目录下创建目录（`test-cases/v1/` 或 `test-cases/v2/`），编写符合 `test-cases/task.schema.json` 的 `task.json`，定义评测 schema，用人工模式测试，然后提交 PR。harness 定义在 `src/clawbench/runtime/harnesses/harnesses.yaml`。

</details>

<details>
<summary><b>如何复现已发表的分数？</b></summary>

见[复现排行榜](reproduce.zh-CN.md)一节的两条路径和通过标准。

</details>

<details>
<summary><b>会更新新模型结果吗？</b></summary>

会。新模型可以通过贡献流程和 issue 提交 / 请求测试。公开结果会在完整运行完成后加入；未跑完整个语料的结果会明确标注为 partial。

</details>
