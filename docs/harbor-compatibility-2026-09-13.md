# Harbor compatibility assessment — 2026-09-13

## Conclusion

ClawBench 已有可用的任务转换层，但“任务能加载”“浏览器运行正常”“评分等价”和“Harbor 官方收录”是四个不同的验收层级。目前不应宣称完全适配所有 Harbor agents/providers。

本次基于 ClawBench main `9dd9d44`、现有适配分支 `bda1708`（PR #353），以及 Harbor main `fd0049126a060f930372f9b0b0aa330caf1f19e5` 研究。Harbor 已于 2026-09-12 发布 [v0.23.0](https://github.com/harbor-framework/harbor/releases/tag/v0.23.0)。本 PR 保留文档运行命令的 0.22.0 基线，只增加 0.23.0 的 loader 验证，不以解析成功推断完整运行兼容。

## Current coverage and gaps

| Layer | Evidence | Remaining work |
| --- | --- | --- |
| Task conversion | `harbor_adapter.py` converts instructions, task/schema files, extra files, environment and step scripts | Schema/staging changes remain in [#353](https://github.com/TIGER-AI-Lab/ClawBench/pull/353); do not duplicate them |
| Task layout | Harbor `Task` and `TaskConfig` explicitly support `steps/run/` | Upstream contribution guide shows a root-level layout; confirm submission convention separately |
| Browser tooling | Kernel already emits pinned Playwright MCP; local mode previously only emitted CDP variables | This PR registers the same MCP server for local mode; actual agent/browser E2E remains unverified |
| Readiness | Setup accepts HTTP success while step healthcheck checks interceptor readiness | [#346](https://github.com/TIGER-AI-Lab/ClawBench/pull/346) already addresses this; review and test that PR |
| Scoring | Interception plus lenient/strict judges; numeric reward metrics | #353 adds explicit inconclusive classification; aggregate reporting must preserve infrastructure denominators |
| Lifecycle | Kernel finalizes replay and deletes the browser before scoring | Deletion failure returns 1 under shell `set -e`, skipping subsequent evidence copy/scoring/email cleanup: [#358](https://github.com/TIGER-AI-Lab/ClawBench/issues/358) |
| Remote environments | Harbor E2B provider can build from a Dockerfile context as well as an image | No live E2B/Daytona/Modal result established here; Dockerfile/provider restrictions still need actual trials |
| Official distribution | Existing upstream [PR #2495](https://github.com/harbor-framework/harbor/pull/2495) is only an external documentation reference | It does not register a dataset or supply an upstream adapter |
| Oracle / parity | Generated `solve.sh` only echoes a message | It cannot prove task success; obtain accepted solvability evidence and run agreed parity protocol: [#359](https://github.com/TIGER-AI-Lab/ClawBench/issues/359) |

## Concrete implementation in this PR

Local Chromium and Kernel now both register `@playwright/mcp@0.0.79` against `http://127.0.0.1:9223`. The existing browser session and recording/interception path remain the MCP target. Harbor's Claude Code and Codex implementations consume task MCP servers; other agents need their own MCP support or an explicit CDP connection. This is a configuration fix, not browser-policy enforcement.

The loader test generates the full V2 corpus in **both** modes and checks that Harbor preserves the pinned MCP command, arguments, and CDP endpoint. It records installed and documented versions without marking a successful compatibility check skipped merely because a newer Harbor is installed.

## Issue / PR decisions

- Keep [#331](https://github.com/TIGER-AI-Lab/ClawBench/issues/331) as the integration umbrella. Its unchecked list is historical, not evidence every item is still required.
- Review #353 for schema/staging/judge semantics and #346 for readiness. This PR branches from main and does not absorb either contributor's work.
- [#357](https://github.com/TIGER-AI-Lab/ClawBench/issues/357): local browser MCP registration, implemented here.
- #358: lifecycle failure handling and durable public diagnostics; separate change with fault-injection tests and agreed exit/reward semantics.
- #359: upstream oracle and parity acceptance. Reconcile the parent issue's proposed no-op oracle with upstream requirements before submitting an adapter as ready.

Perry2004 explicitly deferred image publication in #331 and deferred CI while the adapter contract is evolving in [#350](https://github.com/TIGER-AI-Lab/ClawBench/issues/350#issuecomment-5641310892). Do not reopen those requests or make GHCR publication a prerequisite for this work. E2B's Dockerfile build path is evidence that a public image is not the only possible input; it is not proof this particular Dockerfile builds there.

## Completion criteria for full compatibility

1. Merge the independently reviewed contract/tool/readiness fixes; rerun loader checks on the combined revision.
2. Execute a local Docker trial using a stock MCP-capable agent and capture setup, browser actions, interception, both judge verdicts, reward files, recording, and cleanup. Include no-interception and injected infrastructure-failure cases before claiming result semantics are validated.
3. Run an explicit provider/agent matrix, starting with Docker + Claude Code/Codex and E2B + one agreed agent. Record exact Harbor, agent, model, corpus, judge and environment revisions. Unsupported or untested combinations remain labeled as such.
4. Agree live-site oracle/solvability evidence and a representative parity subset with the upstream maintainers. Match browser tools, task timeouts, model/judge settings, retries and run counts across native and Harbor runs. Report mean ± sample SEM and Stage 1, both Stage 2 scores, inconclusive/infrastructure counts with explicit denominators. Overlapping error bars alone are not proof of statistical equivalence.
5. Complete the upstream adapter package and structured metadata/reference configuration with real results. Registry/Hub publication follows the accepted distribution decision, rather than inventing dataset or image availability.

## Validation and limits

- Harbor 0.22.0 loader: 3 tests passed, covering all V2 tasks in local and Kernel modes.
- Harbor 0.23.0 loader: 3 tests passed; identical full-corpus coverage.
- Focused adapter/correctness/Kernel suite: 25 passed, 1 skipped without optional Harbor installed.
- No Docker executable is available on this host. No browser/provider E2E, paid model run, parity experiment, image publication, or official dataset registration was performed.

## Primary references

- [Harbor task loader at inspected revision](https://github.com/harbor-framework/harbor/blob/fd0049126a060f930372f9b0b0aa330caf1f19e5/src/harbor/models/task/task.py): step layout and runtime input validation.
- [Task configuration](https://github.com/harbor-framework/harbor/blob/fd0049126a060f930372f9b0b0aa330caf1f19e5/src/harbor/models/task/config.py): schema 1.4, steps, MCP and artifact declarations.
- [Claude Code agent](https://github.com/harbor-framework/harbor/blob/fd0049126a060f930372f9b0b0aa330caf1f19e5/src/harbor/agents/installed/claude_code.py) and [Codex agent](https://github.com/harbor-framework/harbor/blob/fd0049126a060f930372f9b0b0aa330caf1f19e5/src/harbor/agents/installed/codex.py): task MCP registration.
- [E2B environment](https://github.com/harbor-framework/harbor/blob/fd0049126a060f930372f9b0b0aa330caf1f19e5/src/harbor/environments/e2b.py): `_create_template` accepts Dockerfile build context or image.
- [Upstream adapter guide](https://github.com/harbor-framework/harbor/blob/fd0049126a060f930372f9b0b0aa330caf1f19e5/docs/content/docs/datasets/adapters.mdx): oracle, parity, metadata and submission requirements.
