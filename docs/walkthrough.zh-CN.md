# 历史 V1 任务走读

[← ClawBench](README.zh-CN.md) · [English](walkthrough.md)

## <img src="../assets/icons/play.svg" width="20" height="20"> 任务走读示例

好奇一个任务从头到尾到底长什么样？下面是 **001 号任务** 的完整走读。每次运行还会产生完整 MP4 录屏 —— V1 任务录屏见[项目主页](https://claw-bench.com)。

**任务定义** —— 来自 [`test-cases/v1/001-daily-life-food-uber-eats/task.json`](../test-cases/v1/001-daily-life-food-uber-eats/task.json)：

```json
{
  "instruction": "On Uber Eats, order delivery: one Pad Thai, deliver to home address, note \"no peanuts\"",
  "time_limit": 30,
  "eval_schema": {
    "url_pattern": "__PLACEHOLDER_WILL_NOT_MATCH__",
    "method": "POST"
  }
}
```

智能体拿到的就是这段原文 `instruction`，另外有只读权限访问 `/my-info/alex_green_personal_info.json`（dummy user 的姓名、住址、电话、生日）和一个一次性邮箱账号（万一遇到强制登录）。任务时限为 **30 分钟**。

这是历史 V1 示例，其占位 URL 规则无法匹配最终请求，用于说明原始的人工参考轨迹评测。上方 Quickstart 使用具有有效拦截规则的 V2 任务。

**智能体要做什么**（顺利路径下）：

1. 打开 `ubereats.com`
2. 从 `/my-info/alex_green_personal_info.json` 读出 dummy user 的家庭住址，填入配送地址输入框
3. 在菜品搜索框里搜 **"Pad Thai"**
4. 挑一家能配送到这个地址且有 Pad Thai 的餐厅
5. 进入菜品详情页，在定制或特殊说明字段里填 **"no peanuts"**
6. 加一份到购物车，打开购物车，必要时用一次性邮箱凭据处理登录弹窗
7. 进入 checkout，点 **Place Order**

**拦截如何工作** —— 当任务配置了有效的 URL 规则和 HTTP method 时，ClawBench 会在匹配的最终请求被转发到真实网站之前拦截它。001 号任务的占位规则没有配置这样的匹配，因此这个示例不能说明 checkout 会被自动拦截。每次运行记录五层数据：视频、截图、HTTP 流量、浏览器动作和智能体消息。

**历史评测器怎么判 PASS / FAIL** —— [`eval/agentic_eval.md`](../eval/agentic_eval.md) 中的人工参考轨迹工作流对照五层录制与人工运行，检查四件事：

- 智能体有没有真正走到最后的 checkout？
- 购物车里是不是**正好一份** Pad Thai（不是两份、也不是套餐）？
- 配送地址是不是 `alex_green_personal_info.json` 里的家庭住址？
- 订单的特殊说明字段里有没有 **"no peanuts"**？

在这个人工参考评测中，四条全满足才算 **PASS**；任何一条没达到就是 **FAIL**，并给出对应证据。该工作流见 [`eval/README.md`](../eval/README.md)，当前自动评分流程见 [`eval/scoring.md`](../eval/scoring.md)。
