# Browser runtimes

By default ClawBench launches Chromium inside its own container. You can point it at a managed remote browser instead — useful when the host cannot run containers comfortably, or when you want the provider to handle scaling and session replay.

`--browser-runtime` accepts `local` (default), `kernel`, `browserbase`, `browser-use`, `remote-cdp`, and `steel`. **`steel` is reserved and not implemented yet** — selecting it raises an error.

## Local container (default)

Nothing to configure. Chromium, Xvfb, ffmpeg, noVNC, and the recorder/interceptor all run in the task container; the session video lands at `recording.mp4`.

## Kernel

Put the key in `.env.local`:

```dotenv
KERNEL_API_KEY=...
```

Then select the runtime on a single or batch run:

```bash
uv run clawbench-run test-cases/v1/<case> your-model \
  --browser-runtime kernel

uv run clawbench-batch --models your-model --all-cases \
  --browser-runtime kernel
```

Kernel runs use ClawBench's existing CDP action capture, screenshots, HTTP logging, and request interception. ClawBench starts a Kernel replay with each browser and downloads the completed video to `data/recording.mp4` before deleting the session.

Provider options are passed as JSON. Supported fields are `stealth`, `region`, `proxy`, and `tags`:

```bash
uv run clawbench-batch --models your-model --all-cases \
  --browser-runtime kernel \
  --browser-runtime-options '{"stealth":true,"region":"us-east"}'
```

Set `KERNEL_BASE_URL` to override the default `https://api.onkernel.com` API endpoint. Batch concurrency defaults to **1**; raise `--max-concurrent` only as far as your Kernel account limit allows.

## Browserbase

Put the key in `.env.local`:

```dotenv
BROWSERBASE_API_KEY=bb_...
```

Then select the runtime on a single or batch run:

```bash
uv run clawbench-run test-cases/v1/<case> your-model \
  --browser-runtime browserbase

uv run clawbench-batch --models your-model --all-cases \
  --browser-runtime browserbase
```

Browserbase runs reuse the same CDP action capture, screenshots, HTTP logging, and request interception as local runs, so scoring is unchanged. The provider records the video: instead of a local `recording.mp4`, the Browserbase Session Inspector URL is stored as `browser_runtime.recording_url` in `run-meta.json`.

Provider options are passed as JSON:

```bash
uv run clawbench-batch --models your-model --all-cases \
  --browser-runtime browserbase \
  --browser-runtime-options '{"region":"us-west-2","proxies":true}'
```

**Concurrency.** `--max-concurrent` defaults to **1** with Browserbase (2 for local runs) because parallel sessions consume provider quota. Raise it only as far as your plan's concurrent-session limit allows.

## Browser Use

Put the key in `.env.local`:

```dotenv
BROWSER_USE_API_KEY=bu_...
```

Then select the runtime on a single or batch run:

```bash
uv run clawbench-run test-cases/v1/<case> your-model \
  --browser-runtime browser-use

uv run clawbench-batch --models your-model --all-cases \
  --browser-runtime browser-use
```

[Browser Use Cloud](https://docs.browser-use.com/cloud/quickstart) runs reuse the same CDP action capture, screenshots, HTTP logging, and request interception as local runs. ClawBench creates each browser with recording enabled, stops it after the run, and downloads the video to `data/recording.mp4`. Zero Data Retention projects never record, so those runs fail with `browser_runtime_artifact_failed`.

Provider options are passed as JSON. Supported fields are `proxyCountryCode` (default `us`, `null` disables the proxy), `profileId`, `customProxy`, `solveCaptchas`, `extensionIds`, and `metadata`:

```bash
uv run clawbench-batch --models your-model --all-cases \
  --browser-runtime browser-use \
  --browser-runtime-options '{"proxyCountryCode":"de"}'
```

Set `BROWSER_USE_BASE_URL` to override the default `https://api.browser-use.com/api/v4` endpoint (for example `https://api.eu.browser-use.com/api/v4`). Batch concurrency defaults to **1**; raise `--max-concurrent` only as far as your project's concurrent-browser limit allows.

## Attaching to a browser you already run

```bash
uv run clawbench-run test-cases/v1/<case> your-model \
  --browser-runtime remote-cdp --browser-cdp-url ws://localhost:9222/devtools/browser/<id>
```

Recording and interception attach to that session instead of starting a browser — the same mechanism the Hermes and Pi harnesses use internally.

Related: [`docs/cli.md`](cli.md) · [`docs/harbor.md`](harbor.md)
