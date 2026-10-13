# Historical V1 walkthrough

[← ClawBench](../README.md) · [中文](walkthrough.zh-CN.md)

## <img src="../assets/icons/play.svg" width="20" height="20"> Example walkthrough

Curious what one task actually looks like, start to finish? Here's task **001** end to end. Each run also produces a full MP4 session recording — see the [project page](https://claw-bench.com) for V1 task recordings.

**The task** — from [`test-cases/v1/001-daily-life-food-uber-eats/task.json`](../test-cases/v1/001-daily-life-food-uber-eats/task.json):

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

The agent gets this `instruction` verbatim, plus read-only access to `/my-info/alex_green_personal_info.json` (the dummy user's name, home address, phone, date of birth) and a disposable email account for any sign-in prompt. The time limit is **30 minutes**.

This is a historical V1 example: its placeholder URL pattern cannot match a final request. It illustrates the original human-reference evaluation; the Quickstart above uses a V2 task with an active interception schema.

**What the agent does** (the happy path):

1. Navigates to `ubereats.com`
2. Reads the dummy user's home address from `/my-info/alex_green_personal_info.json` and enters it in the delivery-address box
3. Searches for **"Pad Thai"** in the food search
4. Picks a restaurant that has Pad Thai available for delivery to that address
5. Opens the item detail page, finds the customization or special-instructions field, enters **"no peanuts"**
6. Adds one to cart, opens the cart, and handles any sign-in prompt using the disposable email credentials
7. Reaches checkout, taps **Place Order**

**How interception works** — for a task with an active URL pattern and method, ClawBench intercepts the matching final request before forwarding it to the live website. Task 001's placeholder does not configure such a match, so this example does not demonstrate automatic checkout interception. Runs record five layers of evidence: video, screenshots, HTTP traffic, browser actions, and agent messages.

**How the historical evaluator decides PASS / FAIL** — the human-reference workflow in [`eval/agentic_eval.md`](../eval/agentic_eval.md) compares the five-layer recording against a human reference run and checks four things:

- Did the agent actually reach the final checkout step?
- Is the cart exactly **one** Pad Thai (not two, not a combo)?
- Is the delivery address the user's home address from `alex_green_personal_info.json`?
- Does the order carry the **"no peanuts"** note in the instructions field?

All four must hold for a **PASS** in this human-reference evaluation. Missing a criterion produces a **FAIL** with supporting evidence. See [`eval/README.md`](../eval/README.md) for this workflow and [`eval/scoring.md`](../eval/scoring.md) for the current automatic scoring pipeline.
