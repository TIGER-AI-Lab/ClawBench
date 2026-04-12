FROM python:3.12-slim

# Rootless Podman without subuid: only UID/GID 0 exist in the namespace.
# 1) Disable apt sandbox (apt tries to switch to _apt user → setgroups fails)
# 2) Wrap dpkg-statoverride so chown to non-root groups (e.g. messagebus) doesn't abort
# 3) Restore real dpkg-statoverride after install
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

# noVNC + websockify for human mode (browser-based VNC client)
RUN git clone --depth 1 --branch v1.6.0 https://github.com/novnc/noVNC.git /opt/novnc \
    && git clone --depth 1 --branch v0.13.0 https://github.com/novnc/websockify.git /opt/novnc/utils/websockify

COPY --from=node:24-slim /usr/local/bin/node /usr/local/bin/node
COPY --from=node:24-slim /usr/local/lib/node_modules /usr/local/lib/node_modules
RUN ln -s /usr/local/lib/node_modules/npm/bin/npm-cli.js /usr/local/bin/npm \
    && ln -s /usr/local/lib/node_modules/npm/bin/npx-cli.js /usr/local/bin/npx

# Pin openclaw version — patched below for #47879 (--autoConnect → --browserUrl)
RUN PLAYWRIGHT_SKIP_BROWSER_DOWNLOAD=1 npm install -g openclaw@2026.3.13

# Patch: replace --autoConnect with --browserUrl http://127.0.0.1:9222 in all dist files
# See https://github.com/openclaw/openclaw/issues/47879
RUN find /usr/local/lib/node_modules/openclaw/dist -name '*.js' -exec \
    sed -i 's/"--autoConnect"/"--browserUrl","http:\/\/127.0.0.1:9222"/g' {} +

COPY --from=ghcr.io/astral-sh/uv:0.11.6 /uv /usr/local/bin/uv

WORKDIR /app
COPY extension-server/ ./extension-server/
# RUN cd extension-server && UV_PYTHON_PREFERENCE=only-system uv sync
RUN cd extension-server && uv sync

COPY chrome-extension/ ./chrome-extension/

COPY setup-openclaw.sh /setup-openclaw.sh
RUN chmod +x /setup-openclaw.sh

COPY entrypoint.sh /entrypoint.sh
RUN chmod +x /entrypoint.sh

EXPOSE 6080 7878 9223

ENTRYPOINT ["/entrypoint.sh"]
