# ClawBench Extension Server

The ClawBench Extension Server is a Python backend server that receives data from the ClawBench Chrome Extension and processes it for benchmarking purposes. It is responsible for:

- Organizing and storing the data received from the extension in a structured format.
- Receiving user actions and storing them in a jsonl format.
- Receiving screenshots and storing them in a dedicated folder.
- Receiving and converting session recording chunks into .mp4 files when the session is complete.

The implementation is minimal, with only the necessary level of complexity and customization.

## Implementation

Single file: `server.py` — a FastAPI application run with uvicorn.

### Endpoints

| Method | Path | Content-Type | Description |
|--------|------|-------------|-------------|
| GET | `/api/status` | — | Returns `{"status": "ok"}` |
| POST | `/api/action` | application/json | Appends action JSON to `actions.jsonl` |
| POST | `/api/screenshot` | application/json | Decodes base64 PNG from `{"timestamp", "data"}`, saves to `screenshots/{timestamp}.png` |
| POST | `/api/stop` | — | Signals session stop, returns session summary |
| POST | `/api/stop-recording` | — | Stops ffmpeg recording, finalizes MP4 |

### Screen Recording

The server starts an ffmpeg process on startup that records the Xvfb virtual display (`DISPLAY=:99`) to `/data/recording.mp4` using H.264 at 15fps. On `/api/stop-recording`, the ffmpeg process is gracefully terminated with SIGINT to finalize the MP4 file. The `/api/stop` endpoint handles session bookkeeping (eval promotion, watchdog signaling) without stopping the recording, allowing a grace period to capture the final state.

### Data Storage

All data is written to the directory specified by `CLAWBENCH_DATA_DIR` (default: `/data`):

```
/data/
  actions.jsonl       # Append-only, one JSON object per line
  screenshots/        # {timestamp}.png files
  recording.mp4       # H.264 screen recording
```

### Running Locally

```bash
cd extension-server
CLAWBENCH_DATA_DIR=./data DISPLAY=:99 uv run uvicorn server:app --host 0.0.0.0 --port 7878
```

### Dependencies

Defined in `pyproject.toml`:
- `fastapi[standard]` — web framework + uvicorn
- `websocket-client` — WebSocket client for CDP communication

System dependency: `ffmpeg` (for screen recording and MP4 encoding).
