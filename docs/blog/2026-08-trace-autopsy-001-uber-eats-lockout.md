# Trace Autopsy #1: How Opus 4.6 Lost a Pad Thai to a Phone-Number Wall

*First in a series where we dissect one failed ClawBench run at a time, using the benchmark's 5-layer recordings: agent messages, DOM actions, raw HTTP, network interception, and video.*

## The task

ClawBench task `001-daily-life-food-uber-eats`, about as everyday as it gets:

> "On Uber Eats, order delivery: one Pad Thai, deliver to home address, note 'no peanuts'"

The agent gets a dummy identity ("Alex Green", a Toronto address, a fresh disposable email inbox) and 30 minutes on the real ubereats.com. The grader is not an LLM judge — it's a network interceptor waiting for one specific HTTP request: a `POST` to `ubereats.com/_p/api/createDraftOrderV2` whose cart contains an item matching `[Pp]ad [Tt]hai` with `deliveryType: ASAP`. Fire that request with the right body and you pass. Nothing else counts.

**Model:** `claude-opus-4-6` (thinking: medium), running the OpenClaw browser harness.
**Verdict:** FAIL after 678 seconds. From `interception.json`:

> `"Session stopped: agent went idle (300s no actions) before triggering the eval interceptor."`

978 HTTP requests captured in `requests.jsonl`. Zero of them were the checkout call.

## The timeline

Timestamps from `agent-messages.jsonl` (UTC).

**11:09:00 — Clean start.** The agent reads the identity files first, notes the delivery address, and opens ubereats.com. The bare domain throws an access-denied wall; it calmly reroutes to `/ca` and lands on an IP-geolocated Toronto feed. Good recovery, ~18 seconds in.

**11:09:31 — Login begins.** It clicks "Log in", enters the disposable email at `auth.uber.com/v2`, and Uber emails a 4-digit code.

**11:09:55 — The email side-quest.** It opens the PurelyMail webmail in a second tab and grinds through genuinely annoying UI: a `'selector' is not supported` tool error, a Roundcube keyboard-shortcuts dialog that pops up twice, a click that silently does nothing, and finally a hand-rolled `evaluate` dispatching synthetic mouse events on `tr.message`. It digs the code out of the "Welcome to Uber" email: *"I can see the verification code: **1539**."* The whole multi-tab, error-recovering detour succeeds.

**11:11:51 — OTP accepted.** Name filled ("Alex" / "Green"), terms accepted. The account exists. The agent is one screen away from the food.

**11:12:41 — The wall.** Uber shows "Keep your account secure": a radio group with **Phone** ("Provide a phone number to use at log in — Recommended", pre-checked) and **Passkey**, plus a Next button. No skip. The agent sees the problem immediately — the persona file has no phone number (`contact` holds only an email; we checked, it really doesn't) — and thinks:

> "There's no skip option. I need to choose Phone and provide a phone number. But the user info doesn't have a phone number."

**11:13:02 — The fatal bet.** Instead of testing the Passkey option it had just flagged, the agent gambles:

> "Let me try navigating directly to Uber Eats to see if I'm already logged in — the account was created, this might just be an optional security step."

It navigates away, mid-verification.

**11:13:24 — Bet lost.** It briefly misreads the feed as success ("it looks like I'm logged in"), then the next snapshot corrects it: the "Log in" link is still there. It returns to `auth.uber.com/v2` and re-enters the email.

**11:13:59 — The door slams.** The login screenshot shows the lock; the DOM snapshot moments later contains, verbatim:

> alert: "Your account is currently disabled. Visit z.uber.com/account-disabled for more information."
> dialog: "Account Locked — We are unable to log you in at this time. Please reach out to support for further assistance."

Uber's anti-fraud system saw a brand-new account bail out of mandatory verification and killed it. The agent clicks "Start Over" and retries the email once more (`actions.jsonl` shows the input events on `#PHONE_NUMBER_or_EMAIL_ADDRESS` at 11:14:31–40). Still locked.

**11:14:57 — The last message.** The agent writes a tidy, accurate post-mortem to the user and asks:

> "Could you provide a phone number I can use for the Uber account, or if you already have an existing Uber Eats account, share those login credentials?"

Nobody answers. This is an unattended benchmark run. Five minutes of silence later, the harness terminates the session — time of death 11:20:18, per run-meta's 678-second duration. The Pad Thai was never in a cart.

## The failure mechanism

Name it precisely: **mid-verification abandonment lockout**. The agent treated browser navigation as a free, reversible probe — "navigate away and see if the session stuck" — inside a flow where leaving *is* the destructive action. One optimistic click converted a recoverable blocker (no phone number on file) into an unrecoverable one (the only available account, on the only available email, permanently disabled). Everything after 11:13:02 was just the trace documenting a corpse.

There's a secondary mechanism stacked on top: **terminal question in an unattended setting**. Asking the user for a phone number is exactly right for a human-in-the-loop assistant and exactly wrong as a final action when no human is watching; the idle timeout, not the model, formally ended the run.

## What this says about agent design

- **Perception wasn't the problem.** Opus 4.6 beat a bot wall, ran a two-tab OTP relay through a hostile webmail UI, and read every page correctly — the classically "hard" parts of browser use. The run died on a resource-and-risk judgment call.
- **Agents need a one-way-door model.** Auth, verification, checkout, and account-creation flows have irreversible transitions. "Try it and see" is a fine policy on a search page and a catastrophic one mid-verification. The agent even *knew* the state was fragile — it just didn't price the exit.
- **Cheap probes before destructive ones.** The non-destructive alternative (click Passkey, inspect what it asks for) was proposed twice in the agent's own thinking and never executed. The destructive probe ran first.
- **Blocked ≠ dead.** Stopping at the wall and reporting "Uber requires a phone number; none is on file" would have been a *graceful* failure, leaving retries open. Burning the account is strictly worse — and current agents don't distinguish the two.

Every claim above is checkable: the run is `001-daily-life-food-uber-eats-claude-opus-4-6-20260329-110845` in the public trace dump, five synced layers deep, mp4 included.

**Traces:** [huggingface.co/datasets/NAIL-Group/ClawBenchV1Trace](https://huggingface.co/datasets/NAIL-Group/ClawBenchV1Trace) · **Benchmark:** [github.com/TIGER-AI-Lab/ClawBench](https://github.com/TIGER-AI-Lab/ClawBench) · **Leaderboard:** [claw-bench.com](https://claw-bench.com)

## X thread

**1/**
Trace autopsy: how a frontier model (Opus 4.6) failed to order one Pad Thai on Uber Eats.

Not perception. Not the bot wall. Not the OTP dance — it nailed all of that.

One optimistic click got its account permanently locked. Full trace inside. 🧵

**2/**
Setup: ClawBench runs agents on the REAL ubereats.com. Grader = network interceptor waiting for POST createDraftOrderV2 with a "Pad Thai" item. No LLM judge — either the checkout request fires or it doesn't.

978 HTTP requests logged this run. 0 were checkout.

**3/**
First 3 min were genuinely impressive: rerouted around an access-denied wall, created an account, pulled OTP "1539" out of a disposable inbox in a second tab (fighting a Roundcube popup + tool errors with hand-rolled JS). Then Uber asked: secure your account. Phone or Passkey. No skip.

**4/**
The persona file has no phone number. The agent's actual reasoning:

"the account was created, this might just be an optional security step"

…and it navigated away, mid-verification. Uber's anti-fraud saw a new account bail on mandatory verification: "Account Locked."

**5/**
Failure mechanism: mid-verification abandonment lockout. The agent treated navigation as a free, reversible probe inside a flow where LEAVING is the destructive action. It even proposed the safe probe (try Passkey) twice in its own thinking — and never ran it.

Then it asked the user for a phone number. Nobody's there. Idle 300s → session killed.

**6/**
Design lesson: agents need a one-way-door model. Auth/verification/checkout flows have irreversible exits, and "try it and see" must be priced accordingly. Blocked is recoverable; locked is not.

Every claim is checkable — 5-layer traces (reasoning, DOM, HTTP, interception, video) are public:
hf.co/datasets/NAIL-Group/ClawBenchV1Trace
github.com/TIGER-AI-Lab/ClawBench
