# Contributing to ClawBench

**First-time open-source contributor?** We specifically want to hear from you. Most of ClawBench is plain JSON + a short schema, and the thing that makes the benchmark valuable is breadth of everyday tasks — which means the best people to contribute are the people doing everyday things on the web. If you've booked a doctor's appointment, ordered groceries, filed a government form, joined a book club, or returned an Amazon package, you already know how to write a test case.

## What we're looking for

| Contribution | Effort | Impact |
|---|---|---|
| Add one new test case | ~30 min | Every additional site expands coverage |
| Add a batch of test cases in one new category (e.g., healthcare, K-12, real estate) | ~2-3 hours | Unlocks a new evaluation axis |
| Add a new model config (in `models/models.yaml`) | ~1 hour | Get your model on the leaderboard |
| Fix a flaky task (find a broken task, propose a fix) | ~20 min | Keeps the leaderboard fair |
| Translate docs into a new language | ~1 hour | Chinese / Japanese / Korean / Spanish welcomed |
| Report a bug via [issue template](https://github.com/TIGER-AI-Lab/ClawBench/issues/new/choose) | ~5 min | Helps us prioritize |

## Recognition for contributors

- **Every merged PR** — your GitHub avatar appears on the repo contributor wall automatically.
- **3+ merged test cases** — you're listed in the Community Contributors section of the README and thanked in the next arXiv paper revision's acknowledgments (with your consent).
- **A whole new category (10+ tasks)** — proposed as a co-author on the relevant follow-up paper / workshop submission.
- **Model runner** — your model ships on the live leaderboard at [claw-bench.com](https://claw-bench.com) with a direct link to your org.

## Good first issues

The issue tracker has a [`good first issue`](https://github.com/TIGER-AI-Lab/ClawBench/labels/good%20first%20issue) label for contributions sized at "30 minutes, no container experience required." Typical entries:

- Add a new test case for a site we don't yet cover (list in the issue description)
- Verify a flagged-flaky task still works
- Add an `extra_info/` file to enrich an existing task

If no `good first issue` is currently open, just open one with your idea and we'll label it and help you land the PR.

## Adding a new test case

ClawBench currently has two full task corpora: V1 lives in `test-cases/v1/` with 152 tasks, and V2 lives in `test-cases/v2/` with 129 tasks. Both use `test-cases/task.schema.json`. Unless a maintainer asks for a V2-only contribution, add new tasks to V1.

1. **Pick a task ID** — find the next available number by checking existing directories in the target corpus (`test-cases/v1/` for V1, or `test-cases/v2/` for V2).

2. **Create the directory** following the naming convention:
   ```
   test-cases/v1/<id>-<metaclass>-<class>-<platform>/
   ```
   Example: `test-cases/v1/887-daily-life-food-grubhub/`

   V2 directories use the `v2-` prefix:
   ```
   test-cases/v2/v2-<id>-<metaclass>-<class>-<platform>/
   ```

3. **Create `task.json`** in the directory. It must conform to `test-cases/task.schema.json`:
   ```json
   {
     "$schema": "../../task.schema.json",
     "metadata": {
       "task_id": 887,
       "metaclass": "daily-life",
       "class": "food",
       "description": "Order a burger on Grubhub",
       "sites_involved": ["grubhub.com"],
       "platform": "grubhub",
       "common_info": {
         "email_credentials": "credentials to use the assigned disposable email account",
         "user_info": "alex_green_personal_info.json; the dummy user's personal information",
         "user_resume": "PDF resume with disposable email account injected"
       }
     },
     "instruction": "On Grubhub, order delivery: one cheeseburger to home address",
     "eval_schema": {
       "url_pattern": "__PLACEHOLDER_WILL_NOT_MATCH__",
       "method": "POST"
     },
     "time_limit": 30
   }
   ```
   For V2 tasks, use the same shared schema reference: `"$schema": "../../task.schema.json"`.

4. **Set the eval_schema** — this tells the interceptor which HTTP request to block:
   - If the task has an irreversible action (form submit, email send, application submit): set `url_pattern` to a regex matching the submission endpoint, and `method` to the HTTP method.
   - If the task is behind a payment wall (agent has no valid credit card): use `"url_pattern": "__PLACEHOLDER_WILL_NOT_MATCH__"` — the interceptor will never fire and the session runs until timeout.
   - See [`test-cases/task.schema.json`](test-cases/task.schema.json) for the supported `body` and `params` filters.

5. **Test with human mode** to verify the task is completable:
   ```bash
   uv run clawbench-run test-cases/v1/887-daily-life-food-grubhub --human
   ```
   For V2:
   ```bash
   uv run clawbench-run test-cases/v2/v2-887-daily-life-food-grubhub --human
   ```

6. **Submit a PR** with your new test case directory. Include in the PR description:
   - Which site and category
   - The URL where the "Submit" action fires (so reviewers can confirm the interceptor config)
   - A one-line note on whether the task is solvable by a human in under a minute

## Extra info files

If the task requires additional context (e.g., a pre-filled profile, a specific document), add files under `extra_info/` in the test case directory and reference them in `task.json`:

```json
"extra_info": [
  {
    "path": "extra_info/cover_letter.txt",
    "description": "Cover letter to attach with the application"
  }
]
```

## Code changes

For changes to the framework itself (test driver, runtime server, Chrome extension, container):

1. Read the [source map](src/README.md) to locate the component and its dependencies.
   The [documentation index](docs/README.md) links to usage and integration guides.
2. Open an issue first for anything beyond a small bug fix so we can align on approach before you spend time.
3. Keep the change focused, run the relevant checks below, and open a PR describing
   the resulting behavior and how you tested it. Add a [changelog entry](#changelog).

From a checkout with [Python 3.11+ and uv installed](docs/getting-started.md):

```bash
uv sync --frozen
uv run --frozen pre-commit install  # optional: run configured checks before commits
```

The root package contains the host CLI and development tools. The runtime server
has a separate [uv project](src/clawbench/runtime/runtime-server/pyproject.toml);
see its [README](src/clawbench/runtime/runtime-server/README.md) for local debugging.

For Python changes, run the same lint, format, type, and host-test checks as CI:

```bash
uv run --frozen ruff check .
uv run --frozen ruff format --check .
uv run --frozen pyright src/clawbench tests
uv run --frozen pytest
```

During development, target the affected tests, for example
`uv run --frozen pytest tests/test_harness_registry.py`. Host tests run on Linux,
macOS, and Windows in [CI](.github/workflows/run-test.yml).

For documentation changes, check repository-relative links from the project root:

```bash
uv run --frozen python scripts/ci/check_markdown_links.py
```

This checks file destinations; review heading links and rendered Markdown too.
For packaging changes, run `uv build` and review the distribution checks in
[static-check](.github/workflows/static-check.yml). Container and harness changes
also have a separate [image-build workflow](.github/workflows/check-harness-build.yml).

## Changelog

Every pull request must add a concise bullet describing its change under `## [Unreleased]` in [`CHANGELOG.md`](CHANGELOG.md). If the `Unreleased` section or the appropriate subsection does not exist, create it.

Follow the existing [Keep a Changelog](https://keepachangelog.com/) structure:

```markdown
## [Unreleased]

### Added

- Added a new capability.

### Fixed

- Fixed a user-visible bug.

## [X.Y.Z] - YYYY-MM-DD
```

Use only `Added`, `Changed`, `Deprecated`, `Removed`, `Fixed`, and `Security` subsections, in that order, and omit empty subsections.
Released versions should not be modified by contributors other than maintainers.

## Reporting issues

Please use the [issue templates](https://github.com/TIGER-AI-Lab/ClawBench/issues/new/choose) to report bugs or propose new test cases.

## Community

Questions, task ideas, model submissions, or just want to chat about browser agents?

- **GitHub issues:** [open one](https://github.com/TIGER-AI-Lab/ClawBench/issues/new/choose) — fastest route to a maintainer
- **微信群:** use the [QR code](./assets/community/wechat_grp_422.jpg)
- **Hugging Face:** [dataset discussions](https://huggingface.co/datasets/NAIL-Group/ClawBench/discussions) — asynchronous, searchable, next to the data
- **Email:** open an issue; we respond there first

## Code of conduct

Be decent to each other. No harassment, no personal attacks, no spam. We follow the spirit of the [Contributor Covenant](https://www.contributor-covenant.org/version/2/1/code_of_conduct/). Maintainers reserve the right to close PRs / remove comments / ban accounts that harm the community.
