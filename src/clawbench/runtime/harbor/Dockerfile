FROM python:3.11-slim

# Harbor starts the main service with "sleep infinity" and then execs task
# setup/test scripts into it. This image therefore contains the browser runtime
# but intentionally does not define an agent harness or entrypoint.
RUN echo 'APT::Sandbox::User "root";' > /etc/apt/apt.conf.d/01disable-sandbox \
    && mv /usr/bin/dpkg-statoverride /usr/bin/dpkg-statoverride.real \
    && printf '#!/bin/sh\n/usr/bin/dpkg-statoverride.real "$@" 2>/dev/null || true\n' \
    > /usr/bin/dpkg-statoverride && chmod +x /usr/bin/dpkg-statoverride \
    && apt-get update && apt-get install -y --no-install-recommends \
    chromium xvfb ffmpeg socat curl git x11vnc xclip \
    libegl1 libgbm1 \
    fonts-noto-color-emoji fonts-noto-cjk \
    && mv /usr/bin/dpkg-statoverride.real /usr/bin/dpkg-statoverride \
    && apt-get clean && rm -rf /var/lib/apt/lists/*

RUN git clone --depth 1 --branch v1.6.0 https://github.com/novnc/noVNC.git /opt/novnc \
    && git clone --depth 1 --branch v0.13.0 https://github.com/novnc/websockify.git /opt/novnc/utils/websockify

COPY --from=ghcr.io/astral-sh/uv:0.11.6 /uv /usr/local/bin/uv

WORKDIR /app
COPY runtime-server/pyproject.toml runtime-server/uv.lock ./src/runtime-server/
WORKDIR /app/src/runtime-server
RUN UV_PYTHON_PREFERENCE=only-system uv sync --frozen \
    && uv pip install --python .venv/bin/python fpdf2

WORKDIR /app
COPY runtime-server/server.py ./src/runtime-server/server.py
COPY chrome-extension/ ./src/chrome-extension/
COPY shared/ ./src/shared/
COPY harbor/ ./src/harbor/
RUN chmod +x /app/src/harbor/*.sh

ENV CLAWBENCH_CDP_URL=http://127.0.0.1:9223 \
    BROWSER_CDP_URL=http://127.0.0.1:9223 \
    CDP_URL=http://127.0.0.1:9223 \
    CHROME_CDP_URL=http://127.0.0.1:9223 \
    PLAYWRIGHT_CDP_URL=http://127.0.0.1:9223 \
    CLAWBENCH_NOVNC_URL=http://127.0.0.1:6080/vnc.html \
    CLAWBENCH_RUNTIME_URL=http://127.0.0.1:7878

EXPOSE 6080 7878 9223

WORKDIR /app
