# ClawBench Codebase 评测报告与优化 Issue 清单

评测日期：2026-09-10

评测范围：`src/clawbench`、Harbor 适配与运行时、任务语料、评分器、CI、构建文件和文档。
评测方式：代码静态审查、配置与任务数量核对、现有测试/CI 路径审查、Harbor 上游版本核对，以及在 uv 管理的 Python 3.12 环境中运行测试。当前工作区没有 Docker，因此 Harbor 容器 E2E 仍无法执行；下文会明确区分“已复现”和“静态发现”。

本报告记录的是修复前基线；同一 PR 已直接修复 `HAR-003`、`ADP-001` 和 `EVAL-001`，并补充了对应回归测试。基线中提到的旧 schema、extra-info 和 judge 状态描述均保留用于审计前后差异。

## 0. Harbor 接入更新（置顶）

### 现状判断

Harbor 接入并不是从零开始：仓库已有 `clawbench-harbor-adapt`、`src/clawbench/runtime/harbor/`、Harbor 文档和适配测试，当前定位是“把 V2 转成 Harbor task，由 Harbor 负责 agent registry、并发、重试和运行”。这部分实现有价值，但目前只能判定为**生成层面的接入**，还不能判定为**可持续的端到端 Harbor 集成**。

截至 2026-09-10，Harbor 官方仓库最新 release 是 `v0.22.0`（2026-08-22），其 `pyproject.toml` 要求 Python `>=3.12`：

- 上游仓库：[harbor-framework/harbor](https://github.com/harbor-framework/harbor)
- 最新 release：[v0.22.0](https://github.com/harbor-framework/harbor/releases/tag/v0.22.0)
- 当前 ClawBench 文档固定：`docs/harbor.md:21-29`
- 修复前适配器：`src/clawbench/eval/harbor_adapter.py:216` 生成 `schema_version = "1.3"`；本 PR 改为集中常量并输出 `1.4`
- Harbor `v0.22.0` 模板已经使用 task schema `1.4`，需要显式建立兼容矩阵，不能继续靠“生成文件看起来像 TOML”来判断兼容性。

### Harbor 集成阻断项

1. **没有 CI 端到端 smoke path。** `tests/test_harbor_version_compatibility.py:21-24` 使用 `importorskip`，Harbor 不在项目依赖中时默认跳过；`.github/workflows/run-test.yml:37-46` 只跑主机 pytest，不安装 Harbor，也不执行 `harbor run`。
2. **Harbor runtime 镜像没有被现有 build workflow 覆盖。** `.github/workflows/check-harness-build.yml:78-86` 只扫描 `runtime/harnesses/**/Dockerfile*`，不会选择 `src/clawbench/runtime/harbor/Dockerfile`；修改 Harbor runtime 可能完全没有构建门禁。
3. **浏览器约束是提示语，不是技术控制。** 生成的 task 使用 `network_mode = "public"`（`harbor_adapter.py:230-245`），并由 Harbor 安装 stock agent。`instruction.md` 要求“只通过浏览器”，但 agent 仍可能使用 shell、`curl`、Python、Node 或直接请求站点 API，造成 benchmark policy bypass。
4. **评分故障被错误地折叠成 agent 失败。** `runtime/harbor/verify.py:311-386` 在缺少 judge 配置、judge 调用失败或返回不可解析 JSON 时写入 `reward=0` 并返回退出码 0。原生 runner 已有 `judge_inconclusive` 语义，但 Harbor 路径没有对齐。
5. **适配范围与契约不清晰。** 当前 adapter 默认 V2，但 `--cases-dir` 可以传入其他 suite，只做最小字段验证；V1/Lite/Claw-Eval 的 metadata、instruction 语义、数量口径和 Harbor source 标识没有正式契约。

### 目标接入形态

Harbor 应成为一个有版本门禁的执行后端，而不是一次性导出脚本：

1. 由单一 manifest 生成 task count、suite/version、task hash、Harbor schema version 和镜像 digest。
2. 固定支持矩阵，例如 `Harbor 0.22.x + Python 3.12 + Docker`，每次升级先跑 loader、单任务 smoke、verifier 和失败清理。
3. Harbor runtime 使用一次构建、可复用的版本化镜像；任务目录只携带 task-specific 文件，避免 129 份重复环境。
4. 用容器级 egress/tool policy 强制 browser-only：至少限制 agent 直接访问站点 API，允许列表由 `sites_involved`、模型端点、PurelyMail、judge 和浏览器 provider 组成；违反策略时输出 `policy_violation`，不能仅依赖 prompt。
5. Harbor verifier 输出统一结果协议：`reward`、`reward_lenient`、`reward_strict`、`intercepted`、`judge_status`、`failure_category`、`task_id`，并让 infra/judge 不确定性可被 Harbor 汇总。

### Harbor 接入验收门槛

- CI 在 Linux Docker runner 安装并锁定 Harbor 版本，生成 1 个真实 V2 task，使用 Harbor 自己的 loader 校验，再执行一个最小 `harbor run` smoke。
- smoke 覆盖：无拦截、拦截且 judge 成功、judge 超时、judge 返回非法 JSON、runtime 未 ready、Kernel cleanup 失败等路径。
- 生成的 `task.toml` schema version 与上游模板一致，或在报告中说明为什么继续兼容旧版本，并由测试固定行为。
- Harbor 运行结果与 native runner 对同一份 interception 的评分在 contract test 中一致；judge 不可判定时两条路径都返回 `judge_inconclusive`。
- 任务结束后 `/data`、recording、requests、actions、verifier logs 均可取得，浏览器和临时邮箱均被清理。
- CI 能在修改 `runtime/harbor/**` 时构建 Harbor 镜像；镜像依赖、上游源码和系统包均可追溯。

## 1. 总体结论与评分

当前 ClawBench 是一个功能丰富、研究迭代速度较快的 benchmark prototype，原生 runner 的任务发现、浏览器 runtime、五层记录和 judge 体系已经形成，但在 secrets、Harbor 生产化、评测有效性和可复现性方面仍有 release-blocking 风险。

| 维度 | 评分 | 判断 |
| --- | ---: | --- |
| Harbor 端到端集成 | 2/5 | 有 adapter/runtime，但没有 CI E2E，版本和失败语义未闭环 |
| 评测正确性 | 2/5 | native 与 Harbor judge 逻辑重复，Harbor infra failure 会变成 0 分 |
| 安全与隐私 | 1/5 | `.env` 被跟踪并打包；HTTP 日志可能包含认证信息 |
| 可复现性 | 2/5 | live websites、未固定的 apt/git 依赖、无统一 corpus manifest |
| 测试与 CI | 2/5 | Harbor 默认跳过，缺少 shell/Docker/security/coverage 门禁 |
| 可维护性 | 2/5 | 多个 800-1800 行模块，生命周期和异常处理分散 |
| 文档一致性 | 3/5 | Harbor 文档较完整，但任务数量、仓库 URL 和评分口径存在漂移 |

**总体：2.0/5，状态为红色。** 在 secrets 处置和 Harbor E2E 门禁完成前，不建议把 Harbor 结果作为 leaderboard-grade 或对外稳定兼容承诺。

## 2. 关键问题与证据

### P0 - 必须立即处理

| ID | 问题 | 证据 | 影响 | 处理要求 |
| --- | --- | --- | --- | --- |
| SEC-001 | `.env` 含非占位 PurelyMail API key，并被 Git 跟踪及打进 wheel/sdist | `.env`；`pyproject.toml:41-59` | 凭据泄露、第三方账户被接管、发布包扩散 | 立即 revoke/rotate；从 Git 和构建产物移除；历史泄露按已泄露处理；改为 secret injection |
| HAR-001 | Harbor 只做导出/loader 级验证，没有实际 `harbor run` 门禁 | `tests/test_harbor_version_compatibility.py:21-73`；`.github/workflows/run-test.yml:37-46` | 适配器、镜像、runtime、verifier 的回归不会被发现 | 增加锁版本 Linux Docker smoke 和失败路径测试 |
| EVAL-001 | Harbor judge outage/非法回复返回 reward 0、exit 0 | `runtime/harbor/verify.py:311-386` | 把基础设施故障计入 agent 失败，污染排行榜和重试统计 | 引入 `judge_inconclusive`，使用结构化 failure category，并与 native runner 对齐 |

### P1 - 近期必须完成

| ID | 问题 | 证据 | 影响 | 处理要求 |
| --- | --- | --- | --- | --- |
| SEC-002 | `requests.jsonl` 保存原始 request headers | `runtime/runtime-server/server.py:213-231,445-446` | `Authorization`、`Cookie` 等可能进入可分享 artifacts | 默认 header allowlist/脱敏；增加敏感字段测试和配置化 retention |
| HAR-002 | `network_mode = "public"` 加上 stock agent shell，browser-only 仅靠 prompt | `eval/harbor_adapter.py:230-245`；`runner/run_support/task.py:204-208` | agent 可绕过浏览器直接调用 API，破坏任务有效性 | Harbor 环境增加 egress/tool policy、违规检测和 `policy_violation` 结果 |
| HAR-003 | 生成 `schema_version = "1.3"`，未与 Harbor 0.22.0 的 `1.4` 模板建立兼容契约 | `eval/harbor_adapter.py:216`；`tests/test_harbor_adapter.py:107-113` | Harbor 升级可能静默改变解析或运行行为 | 集中定义版本常量，更新 schema 或锁定支持矩阵，CI 记录实际 Harbor 版本 |
| CI-001 | Harbor Dockerfile 不在 harness build 的扫描和选择逻辑内 | `.github/workflows/check-harness-build.yml:78-153` | Harbor runtime 改动可能没有镜像构建检查 | 单独加入 Harbor image matrix，或把 runtime image registry 化 |
| ADP-001 | Harbor `copy_extra_info()` 未复用 native 的路径校验，且按 basename flatten | `eval/harbor_adapter.py:360-371`；对照 `runner/run_support/task.py:132-185` | `..`/绝对路径/符号链接可越界；同名文件会覆盖 | 统一 `validate_extra_info_path`；保留相对路径或显式拒绝冲突 |
| DATA-001 | task validator 只检查少数字段，不编译 URL regex、不校验 method enum、extra_info 结构和所有路径 | `runner/run_support/task.py:246-265` | 错误会延迟到 runtime thread，表现为超时或未拦截 | 用 JSON Schema + 语义 validator；CI 在 adapter 前执行完整校验 |
| EVAL-002 | Harbor `verify.py` 与 native judge client/prompt/retry/parse 逻辑重复 | `runtime/harbor/verify.py:12-261`；`runner/judge.py` | 两条执行路径可能得出不同分数，修复需要改两份 | 抽取共享 judge contract/client，增加 native/Harbor golden tests |
| BUILD-001 | Docker 使用未 digest 固定的 `python:3.11-slim`、apt、git tag 和远程 npm/uv 依赖 | `runtime/harbor/Dockerfile:1-33`；`runtime/harnesses/base/Dockerfile.base:1-28` | 构建不可复现、供应链风险、冷启动不稳定 | 固定镜像 digest、源码 commit、锁文件和 SBOM；启用 Dependabot/Renovate |
| OPS-001 | Harbor setup/test/cleanup 的状态机和失败语义不完整 | `eval/harbor_adapter.py:274-345`；`runtime/harbor/cleanup-email.py:57-59` | 中断时可能残留浏览器、邮箱或录制进程；cleanup 总是 exit 0 | 为 setup/finalize/cleanup 增加幂等状态文件、超时和可观测结果 |

### P2 - 结构性优化

| ID | 问题 | 证据 | 处理要求 |
| --- | --- | --- | --- |
| DATA-002 | 语料数量没有单一事实源；`eval/scoring.md:30` 仍写 V1 153、V2 130，而当前目录是 152、129 | `README.md:91-93`；`eval/scoring.md:23-30` | 生成 corpus manifest，并让 scoring、README、leaderboard 校验使用同一份数据 |
| DOC-001 | 仓库身份 URL 混用 `TIGER-AI-Lab/ClawBench` 和 `reacher-z/ClawBench` | `README.md`；`pyproject.toml:19-23` | issue、release、包元数据和贡献入口指向不一致 | 选定 canonical URL，CI 检查文档链接一致性 |
| MNT-001 | `tui.py` 1802 行、`batch.py` 1006 行、runtime server 879 行、`run.py` 829 行、providers 805 行 | `find src -name '*.py' ...` | 修改 blast radius 大，测试隔离和代码审查成本高 | 按 orchestration、provider、artifact、judge、UI 拆分模块，定义 Protocol/接口 |
| TEST-001 | CI/pre-commit 没有 shellcheck、hadolint、secret scan、pip-audit、覆盖率阈值 | `.pre-commit-config.yaml`；`.github/workflows/*.yml` | shell、镜像和依赖风险只能在运行时暴露 | 增加静态安全和构建 lint；pytest-cov 按核心包设置最低线 |
| LIVE-001 | 任务依赖真实网站，缺少站点可用性 canary、拦截 golden trace 和漂移告警 | `test-cases/v1`、`test-cases/v2` 共 281 个任务 | 网站改版、登录墙和限流会被误判为模型失败 | 增加周期 canary、站点状态 artifact、可重复 fixture/control arm |
| RUNTIME-001 | `steel` 出现在 CLI choices，但 provider 明确抛出“reserved but not implemented” | `runner/run_support/browser_runtime/providers.py:17,235-243` | 用户能选择一个必然失败的模式 | 从公开 choices 移除，或标记 experimental 并给出可用实现 |

## 3. 需要维护者先回答的问题

1. Harbor 的正式支持范围是仅 V2，还是 V1/Lite/Claw-Eval 也必须可运行？每个 suite 是否需要独立 dataset version？
2. “browser-only”是评测硬约束还是 agent 行为建议？若是硬约束，允许哪些 egress、CLI 和本地文件操作？
3. Harbor 结果是否需要与 native runner 合并进同一 leaderboard？如果需要，`judge_inconclusive`、重试和 attempt 聚合规则是什么？
4. 当前 `.env` 中的 PurelyMail key 是否仍在使用？谁负责撤销、轮换和审计历史构建产物？
5. 是否接受将 Harbor host Python 升到 3.12，同时保持 ClawBench native runner 的 Python 3.11 支持？
6. `requests.jsonl` 是否允许包含 header？公开 trace 的隐私/保留期限和脱敏规则由谁批准？
7. Harbor runtime 是否要支持 Kernel 作为 CI control arm，还是只在本地/手工运行？
8. `TIGER-AI-Lab/ClawBench` 与 `reacher-z/ClawBench` 哪个是 canonical repository？

## 4. GitHub-ready Issue 草案

本次已将未被本 PR 覆盖的高优先级项提交为独立 GitHub issue，并全部指派给 `@Perry2004` 审核：

- [#351 Revoke and remove tracked PurelyMail credentials](https://github.com/TIGER-AI-Lab/ClawBench/issues/351)
- [#350 Add a real Harbor 0.22.x Docker end-to-end smoke gate](https://github.com/TIGER-AI-Lab/ClawBench/issues/350)
- [#352 Enforce browser-only execution policy](https://github.com/TIGER-AI-Lab/ClawBench/issues/352)
- [#349 Redact HTTP request headers before persisting public artifacts](https://github.com/TIGER-AI-Lab/ClawBench/issues/349)

下方仍保留完整的 issue 规格，便于后续维护者拆分、合并或追踪验收标准。

### [P0][Security] Revoke and remove tracked PurelyMail credentials

- Labels: `security`, `priority:P0`, `good first issue` 不适用
- Problem: `.env` 被 Git 跟踪，且 `pyproject.toml` 将其 force-include 到 wheel/sdist。文件中的 key 非占位值，应按已泄露凭据处理。
- Scope: revoke/rotate key；从历史和构建流程移除；新增 `.env.example`；CI 使用 secret；加入 secret scan；发布前检查 wheel/sdist 不含 secrets。
- Acceptance: `git ls-files .env` 为空；构建产物无 `.env`；无明文 key；文档不再要求把凭据打包或提交。

### [P0][Harbor] Add a real Harbor 0.22.x end-to-end smoke gate

- Labels: `harbor`, `ci`, `priority:P0`
- Problem: 当前兼容性测试默认跳过 Harbor，CI 不执行 `harbor run`，Harbor Dockerfile 也不在 build matrix。
- Scope: 固定 Harbor 版本和 Python 3.12；生成一个真实 V2 task；运行 Harbor loader、单任务 smoke、verifier 和 cleanup；将 Harbor runtime image 纳入 workflow。
- Acceptance: PR 修改 adapter/runtime 时 Linux Docker job 必须执行；失败时上传 task、runtime、verifier logs；版本、schema、image digest 被写入 artifact。

### [P0][Evaluation] Preserve judge-inconclusive in Harbor results

- Labels: `evaluation`, `harbor`, `priority:P0`
- Problem: judge 缺失、超时、网络错误和非法 JSON 均写成 reward 0、exit 0。
- Scope: 定义 `judge_status = ok|inconclusive|error` 和 `failure_category`；与 native runner 的 batch aggregation 对齐；区分 agent failure、infra failure、policy violation。
- Acceptance: judge outage 不进入 agent failed 计数；Harbor summary 可单独统计；重试只针对可重试类别。

### [P1][Security] Redact HTTP artifacts before persistence

- Labels: `security`, `privacy`, `priority:P1`
- Problem: runtime server 把 request headers 原样写入 `requests.jsonl`。
- Scope: 默认 allowlist；脱敏 `authorization`、`cookie`、`set-cookie`、CSRF 和 token 字段；限制 body/header 大小；增加 fixture tests。
- Acceptance: 测试输入中的 secret 不出现在任何公开 artifact；保留可解释的 redaction marker。

### [P1][Harbor] Enforce browser-only execution policy

- Labels: `harbor`, `benchmark-validity`, `priority:P1`
- Problem: `network_mode=public` 和 stock agent shell 允许绕过浏览器。
- Scope: Harbor task 增加 egress allowlist、工具限制和违规检测；将站点、模型、judge、PurelyMail/provider 依赖显式化。
- Acceptance: 直接 `curl`/API 提交被阻断或记录为 `policy_violation`；合法 CDP/browser flow 不受影响；结果中有违规证据。

### [P1][Adapter] Unify task validation and safe extra-info staging

- Labels: `harbor`, `security`, `priority:P1`
- Problem: Harbor adapter 没有复用 native path validation，basename flatten 可能越界或覆盖文件。
- Scope: 统一 path validator；拒绝绝对路径、`..`、逃逸 symlink 和 basename collision；编译 regex、校验 method 和字段类型。
- Acceptance: 恶意 fixture 在转换前失败；native/Harbor 复制结果一致；所有真实 suite 在 CI 通过。

### [P1][Build] Make Harbor images reproducible and auditable

- Labels: `build`, `supply-chain`, `priority:P1`
- Problem: base image、apt、git tags 和远程工具没有 digest/commit/SBOM 门禁。
- Scope: 固定 digest/commit；使用锁文件；生成 SBOM；定期依赖升级 PR；缓存共享 Harbor runtime image。
- Acceptance: 同一 commit 可重建相同 image digest 或解释差异；构建 artifact 包含来源和漏洞扫描结果。

### [P1][Evaluation] Share judge client and result contract between native and Harbor

- Labels: `evaluation`, `refactor`, `priority:P1`
- Problem: 两套 judge prompt/API/retry/JSON parse 逻辑会漂移。
- Scope: 抽取共享 client、schema、redaction、retry policy 和 golden prompts。
- Acceptance: 同一 interception fixture 在 native/Harbor 输出等价；非法响应、超时和 unsupported api type 有一致分类。

### [P2][Data] Generate one corpus manifest and remove count drift

- Labels: `documentation`, `data-quality`, `priority:P2`
- Problem: shipping corpus 是 V1 152、V2 129，但 scoring/leaderboard 文案仍有 153/130。
- Scope: 生成带 task hash、site、suite、version 的 manifest；文档和聚合脚本读取 manifest。
- Acceptance: CI 检查目录、manifest、README、scoring、leaderboard 数量一致。

### [P2][CI] Add shell, Docker, dependency and coverage gates

- Labels: `ci`, `security`, `priority:P2`
- Scope: shellcheck、hadolint、secret scan、pip-audit、pytest-cov、Harbor marker；对 runtime 目录变更精确触发对应镜像。
- Acceptance: 新增检查在 PR 必跑；无 Harbor 依赖的主机测试仍可快速运行。

### [P2][Architecture] Split orchestration and runtime modules

- Labels: `refactor`, `maintainability`, `priority:P2`
- Scope: 拆分 TUI/batch/run/providers/server；为 browser provider、judge、artifact sink、task adapter 定义接口。
- Acceptance: 单模块目标小于约 500 行；核心路径有单元测试；不改变现有 CLI 输出和 result schema。

## 5. 分阶段优化路线

### 阶段 0：0-24 小时，安全止血

- 撤销并轮换 PurelyMail key，审计历史提交、CI logs、wheel/sdist 和已有 Harbor jobs。
- 停止打包 `.env`；建立 `.env.example` 和 secret injection。
- 对公开 artifact 做一次 header/token 扫描，必要时下架已发布 trace。

### 阶段 1：1 个迭代周期，Harbor 基线

- 锁定 Harbor `0.22.x`、Python 3.12、Docker provider 和支持矩阵。
- 更新或明确 `schema_version`；修复 workflow 对 Harbor Dockerfile 的漏检。
- 加入真实 V2 one-task smoke，覆盖 local browser、verifier 和 cleanup。
- 明确 browser-only 策略，至少输出 policy violation，不再把 prompt 当安全边界。

### 阶段 2：1-2 个迭代周期，评分正确性

- 抽取共享 judge client/result schema。
- 实现 `judge_inconclusive`、重试分类和 Harbor summary 聚合。
- 给 `parse_verdict` 增加严格 JSON schema、大小限制和 prompt-injection-resistant framing。
- 对 native/Harbor 使用同一组 interception golden fixtures。

### 阶段 3：持续工程化

- 统一 corpus manifest、task hash、site canary 和 drift report。
- 固定镜像与依赖来源，生成 SBOM，加入漏洞和 secret 扫描。
- 拆分大模块，降低隐式全局状态；补充覆盖率、故障注入和 kill-path 测试。
- 记录每次 run 的 git SHA、Harbor 版本、image digest、judge 配置 hash、browser provider 和 policy version。

## 6. Definition of Done

- [ ] 不再跟踪或发布任何真实凭据，secret scan 和构建产物检查通过。
- [ ] Harbor 版本、Python、Docker provider、task schema 和 image digest 均被锁定并写入结果。
- [ ] Harbor one-task smoke 在 CI 中真实运行，而不是 `importorskip`。
- [ ] Harbor runtime 改动会触发对应镜像构建和 smoke。
- [ ] browser-only policy 可执行、可审计、可分类。
- [ ] judge outage/invalid response 进入 `judge_inconclusive`，不会伪装成 agent failure。
- [ ] native 与 Harbor 对同一 interception 的结果 contract 一致。
- [ ] requests/actions/recording/verifier artifacts 默认脱敏并有保留策略。
- [ ] corpus manifest、README、scoring、leaderboard 数量一致。
- [ ] 关键模块、shell、Docker、依赖和失败清理均有自动化门禁。

## 7. 外部参考

- Harbor repository: <https://github.com/harbor-framework/harbor>
- Harbor v0.22.0 release: <https://github.com/harbor-framework/harbor/releases/tag/v0.22.0>
- Harbor v0.22.0 task template: <https://raw.githubusercontent.com/harbor-framework/harbor/v0.22.0/src/harbor/cli/template-task/task.toml>
- ClawBench Harbor usage: [`docs/harbor.md`](harbor.md)
- ClawBench scoring reference: [`eval/scoring.md`](../eval/scoring.md)
