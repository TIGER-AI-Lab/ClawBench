# 安装与首次运行

[← ClawBench](README.zh-CN.md) · [English](getting-started.md)

## <img src="../assets/icons/rocket.svg" width="24" height="24"> 快速开始

### 安装

```bash
uv tool install clawbench-eval
```

也可以用 `pipx install clawbench-eval` 或 `python -m pip install clawbench-eval`。安装后可用交互式 `clawbench` 启动器，以及运行、评分和分析命令；详见 [CLI 参考](cli.md)。

贡献者可使用下方的[源码开发说明](getting-started.zh-CN.md#develop-from-source)。**用编程智能体来跑？** 把它指向 [`AGENTS.md`](../AGENTS.md)。

**前置条件：** [Python 3.11+](https://python.org)、[uv](https://docs.astral.sh/uv/)，以及一个容器引擎 —— [Docker](https://www.docker.com/) **或** [Podman](https://podman.io/)。ClawBench 会自动检测已安装的那个；也可用 `export CONTAINER_ENGINE=docker` / `export CONTAINER_ENGINE=podman` 强制指定。

<details>
<summary><b>安装 Docker 或 Podman</b>（macOS / Linux / Windows）</summary>

#### macOS

```bash
# 方案 A —— Docker Desktop（最简单，带 GUI）
brew install --cask docker
open -a Docker                 # 启动后等鲸鱼图标稳定

# 方案 B —— Podman（rootless，无 daemon，仅 CLI）
brew install podman
podman machine init            # 一次性：下载 Linux VM 镜像
podman machine start           # 任何 podman 命令之前都必须先启动
```

> **macOS 上的 Podman 需要一个 VM。** 只 `brew install podman` 是不够的 —— macOS 上 Podman 在一个小型 Linux VM 里跑容器，所以装完必须执行一次 `podman machine init && podman machine start`，否则 `podman info` 会报 `Cannot connect to Podman`。

#### Linux (Ubuntu / Debian)

```bash
# 方案 A —— Podman（默认 rootless，推荐）
sudo apt update && sudo apt install -y podman

# 方案 B —— Docker
sudo apt install -y docker.io
sudo usermod -aG docker $USER  # 重新登录让 shell 生效
```

> **rootful Docker 的文件属主问题：** 用传统的 `sudo` docker 时，从容器里导出的文件在宿主机上属主是 `root`。ClawBench 的 driver 会在每次运行后检测并把 `test-output/` 的属主改回当前用户 —— 但如果你同时还用别的容器工具，rootless Podman（或 rootless Docker）能彻底避免这个问题。

#### Windows

```powershell
# 方案 A —— Docker Desktop（WSL2 后端）
winget install Docker.DockerDesktop
# 然后从开始菜单启动 Docker Desktop，等它就绪

# 方案 B —— Podman
winget install RedHat.Podman
podman machine init
podman machine start
```

> 下面的 `uv run …` 命令请在 **PowerShell**、**WSL2** 或 **Git Bash** 中运行。和 macOS 一样，Windows 上的 Podman 首次使用前需要 `podman machine init && podman machine start`。

</details>

### 1. 配置模型

一次性设置。如果是 PyPI 安装，请在你希望存放结果和配置的目录下运行 `clawbench`，首次启动会在 `models/` 下生成本地模板：

```bash
clawbench
$EDITOR models/models.yaml
```

源码 checkout：

```bash
cp models/models.example.yaml models/models.yaml
$EDITOR models/models.yaml
```

评分需要一个 judge。跑任何带评分的批量任务之前，请先配置 `deepseek-v4-pro` 的 API key —— 所有公开 leaderboard 行都用的是它：

```yaml
deepseek-v4-pro:
  api_key: "sk-..."
  base_url: <api_base_url>
  api_type: openai-completions
```

一次性运行邮箱用的 PurelyMail 凭据已随仓库的 `.env` 提供。只有当你想用自己的 PurelyMail 账号、或想开启可选的 HuggingFace 上传时才需要改 `.env`。

> [!NOTE]
> **首次运行会构建容器镜像**（Chromium + ffmpeg + noVNC + 所选 harness 的依赖），过程中会显示当前构建步骤。后续运行复用缓存层，几秒即可完成。

### 2. 跑通第一个任务

> [!TIP]
> **推荐 → 交互式 TUI**，引导式选择模型和测试用例：
> ```bash
> clawbench         # PyPI 安装
> uv run clawbench  # 源码 checkout
> ```
> 需要交互式终端。管道 / CI / 非 TTY 环境请直接用 `clawbench-run` 或 `clawbench-batch`。

**单模型跑单任务：**

```bash
clawbench-run test-cases/v2/v2-1033-education-learning-registration-khanacademy your-model
```

将 `your-model` 替换成 `models/models.yaml` 中配置的 key。这个 V2 任务导航到 Khan Academy 课程页面，具有有效的 `GET` 拦截规则。从源码 checkout 运行时，在命令前加 `uv run`。

容器启动后脚本会打印一个 **noVNC 地址**（例如 `http://localhost:6080/vnc.html`），打开即可实时观看智能体操作；6080 被占用时会自动换端口。结果输出在 `./test-output/<model>/<harness>-<case>-<model>-<timestamp>/`，包含完整五层录制。

**跑完整个语料：**

```bash
clawbench-batch --models your-model --cases-suite v2 --all-cases
```

`your-model` 是你在第 1 步里配置的 key；`--cases-suite v2` 跑完整 V2 语料（换成 `v1-lite` 则是 20 题子集）。`--max-concurrent N` 控制并发（本地默认 2，Kernel 或 Browserbase 默认 1），`--harness <name>` 选择智能体。每个任务都会被拦截并由第 1 步配置的 `deepseek-v4-pro` judge 打分 —— 加 `--no-judge` 可跳过评分。`batch-summary.json` 和各次运行的录制都会写到 `./test-output/`。

分析已完成批次的 Stage-1/Stage-2 通过率、失败分类、各类别结果与自报成功偏差：

```bash
clawbench-analyze --runs-dir test-output/batch-<timestamp> --out report.md
```

**自己上手操作，产出人工参考轨迹：**

```bash
uv run clawbench-run test-cases/v1/001-daily-life-food-uber-eats --human
```

打开脚本给出的 noVNC 地址，手动完成任务后关闭标签页即可。你也可以让**外部浏览器智能体**接管这个会话，ClawBench 照样录制和拦截。

### 3. 选择 harness

harness 是驱动浏览器的智能体框架，和模型是两个独立维度。默认是 `openclaw`，在 `clawbench-run` / `clawbench-batch` 上用 `--harness <name>` 切换。

| Harness | `--harness` | 如何驱动浏览器 | 什么时候用 |
| --- | --- | --- | --- |
| [OpenClaw](https://github.com/openclaw/openclaw) | `openclaw`（默认） | Playwright MCP 桥接 | 想要 V1 结果所用的参考配置 |
| [Hermes Agent](https://github.com/NousResearch/hermes-agent) | `hermes` | 原生 browser 工具走 CDP | 想对齐大部分 V2 leaderboard 行 |
| [opencode](https://opencode.ai) | `opencode` | Playwright MCP 桥接 | 比较不同 coding agent 框架 |
| [Claude Code](https://docs.anthropic.com/en/docs/claude-code) | `claude-code` | Playwright MCP 桥接 | 比较不同 coding agent 框架 |
| Claude Code + [Claude in Chrome](https://code.claude.com/docs/en/chrome) | `claude-code-chrome-extension` | Chrome 扩展 + 本地 bridge（Microsoft Edge） | 测试扩展链路；任意 LiteLLM 路由的 provider 均可 |
| [OpenAI Codex CLI](https://github.com/openai/codex) | `codex` | Playwright MCP 桥接 | 比较不同 coding agent 框架 |
| [claw-code](https://github.com/ultraworkers/claw-code) | `claw-code` | Playwright MCP 桥接 | 比较不同 coding agent 框架 |
| [browser-use](https://github.com/browser-use/browser-use) | `browser-use` | 原生浏览器框架，经 LiteLLM 路由 | 比较专用 web agent |
| [Pi](https://pi.dev/) | `pi` | 固定版本 [pi-browser-harness](https://pi.dev/packages/pi-browser-harness) 走 CDP | 只读工具 allowlist、无 shell |
| — | `random-click` | 随机点击，不用模型 | 建立下界基线 |
| — | `null` | 什么都不做 | 衡量 harness / 录制本身的开销 |

完整注册表：[`src/clawbench/runtime/harnesses/harnesses.yaml`](../src/clawbench/runtime/harnesses/harnesses.yaml)。

### 4. 其他浏览器运行时与框架

| 我想…… | 去哪看 |
| --- | --- |
| 用托管的远程浏览器代替本地容器 | [`docs/browser-runtimes.md`](browser-runtimes.md) —— Kernel 和 Browserbase 配置、参数与录制 |
| 用 Harbor 框架跑 V2（并且跑得快） | [`docs/harbor.md`](harbor.md) —— 转换、judge 配置、并发、排错 |
| 查所有 CLI 命令和参数 | [`docs/cli.md`](cli.md) |

<details id="develop-from-source">
<summary><b>从源码开发</b> &nbsp;—— 克隆 + <code>./run.sh</code>，面向贡献者</summary>

```bash
git clone https://github.com/TIGER-AI-Lab/ClawBench.git && cd ClawBench
cp models/models.example.yaml models/models.yaml   # 编辑：填入你的模型 API key
# .env 已提供 PurelyMail 凭据；只有用自己的凭据或开启 HF 上传时才需要改
./run.sh                                           # 交互式 TUI
uv run clawbench-run \
  test-cases/v1/001-daily-life-food-uber-eats claude-sonnet-4-6   # 单次运行
uv run clawbench-run \
  test-cases/v1/001-daily-life-food-uber-eats --human             # 人工模式
```

这条路径下 `src/`、`src/clawbench/runtime/chrome-extension/` 和 `test-cases/` 下所有 suite 都是实时生效的 —— 迭代 harness 本身时很有用。

</details>
