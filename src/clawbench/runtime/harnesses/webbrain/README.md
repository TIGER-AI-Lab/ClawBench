# WebBrain harness

This harness evaluates the browser-native [WebBrain](https://github.com/webbrain-one/webbrain)
extension against ClawBench tasks. The image loads an exact WebBrain commit alongside the
ClawBench recorder, then a small CDP driver configures and invokes WebBrain through its existing
extension message interface.

## Compatibility

- Local browser mode is required because remote browser mode cannot load the unpacked extension.
- The first version accepts `api_type: openai-completions`. Other API types fail before a model
  request instead of silently using the wrong wire format.
- The first key from `api_keys` is used when present; otherwise `api_key` is used. Rotation is not
  currently supported.
- ClawBench model configs do not expose model vision capability, so the generic provider is
  configured text/tool-only.

WebBrain's supported Instant clarification setting and prompt-free permission mode are enabled for
unattended benchmark runs. The task instruction is the authoritative user request, and ClawBench's
request interceptor remains the final boundary for consequential submissions. First-run onboarding
is also marked complete because the harness configures the provider and run mode directly.

## Output

The driver writes WebBrain updates, trace events, and the terminal response to
`/data/agent-messages.jsonl`. Reported LLM token usage is normalized from WebBrain's trace store
into `/data/usage.jsonl`. Cost stays `price_unavailable` because ClawBench model configuration does
not provide per-token prices to the extension harness.
