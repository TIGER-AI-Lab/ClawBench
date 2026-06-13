# ClawBench Runtime Server

The ClawBench Runtime Server is a Python backend instrumentation server that connects to Chromium over CDP and writes benchmark artifacts. It is responsible for:

- Capturing browser DOM actions through CDP-injected listeners and storing them in jsonl format.
- Capturing screenshots through CDP after browser actions.
- Logging HTTP requests and blocking matching eval-schema requests through CDP's `Fetch` domain.
- Recording the Xvfb display to `recording.mp4`.

## Implementation

Single `server.py` — a FastAPI application run with uvicorn.

### Endpoints

| Method | Path                  | Content-Type     | Description                                                                             |
| ------ | --------------------- | ---------------- | --------------------------------------------------------------------------------------- |
| GET    | `/api/status`         | —                | Returns `{"status": "ok"}`                                                              |
| POST   | `/api/action`         | application/json | Compatibility endpoint; CDP capture writes actions directly                             |
| POST   | `/api/screenshot`     | application/json | Compatibility endpoint; CDP capture writes screenshots directly                         |
| POST   | `/api/stop`           | —                | Signals session stop, returns session summary                                           |
| POST   | `/api/stop-recording` | —                | Stops ffmpeg recording, finalizes MP4                                                   |

### Screen Recording

The server starts an ffmpeg process on startup that records the Xvfb virtual display (`DISPLAY=:99`) to `/data/recording.mp4` using H.264 at 15fps. On `/api/stop-recording`, the ffmpeg process is gracefully terminated with SIGINT to finalize the MP4 file. The `/api/stop` endpoint handles session bookkeeping (eval promotion, watchdog signaling) without stopping the recording, allowing a grace period to capture the final state.

NOTE: Since the actual MP4 is assembled after the session ends, during testings that need manual termination, do `curl -X POST http://localhost:7878/api/stop` instead of stopping the container/process directly to ensure the recording is finalized properly.

### Data Storage

All data is written to the directory specified by `CLAWBENCH_DATA_DIR` (default: `/data`):

```
/data/
  actions.jsonl       # Append-only, one JSON object per line
  requests.jsonl      # Append-only browser request log
  interception.json   # Interception result
  screenshots/        # {timestamp}.png files
  recording.mp4       # MP4 screen recording
```

### Running Locally

The runtime server normally runs only inside the benchmark container. For
debugging the server by itself, use its local uv project:

```bash
cd src/clawbench/runtime/runtime-server
CLAWBENCH_DATA_DIR=./data DISPLAY=:99 uv run --frozen uvicorn server:app --host 0.0.0.0 --port 7878
```

### Dependencies

The runtime server is container-only and has its own uv project in
`src/clawbench/runtime/runtime-server/`:
- `fastapi` — web framework
- `uvicorn` — ASGI server
- `websocket-client` — WebSocket client for CDP communication

System dependency: `ffmpeg` (for screen recording and MP4 encoding).
