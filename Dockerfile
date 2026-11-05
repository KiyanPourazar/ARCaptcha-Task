# syntax=docker/dockerfile:1
FROM python:3.12-slim-bookworm

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    # UC Mode Chrome (shared with noVNC for Headful)
    DISPLAY=:99 \
    DOCKER_UC_DISPLAY=:99 \
    DRIVER_MODE=uc \
    SELENIUM_REMOTE_URL= \
    SB_DRIVER_KEY=binary

WORKDIR /app

# Heavy OS deps — cached unless this block changes
RUN apt-get update && apt-get install -y --no-install-recommends \
      ca-certificates \
      curl \
      gnupg \
      unzip \
      fonts-liberation \
      fonts-noto-color-emoji \
      libnss3 \
      libatk-bridge2.0-0 \
      libgtk-3-0 \
      libx11-xcb1 \
      libxcomposite1 \
      libxdamage1 \
      libxrandr2 \
      libgbm1 \
      libasound2 \
      libpangocairo-1.0-0 \
      libcups2 \
      xvfb \
      x11vnc \
      novnc \
      websockify \
      procps \
    && mkdir -p /etc/apt/keyrings \
    && curl -fsSL https://dl.google.com/linux/linux_signing_key.pub \
         | gpg --dearmor -o /etc/apt/keyrings/google-chrome.gpg \
    && echo "deb [arch=amd64 signed-by=/etc/apt/keyrings/google-chrome.gpg] http://dl.google.com/linux/chrome/deb/ stable main" \
         > /etc/apt/sources.list.d/google-chrome.list \
    && apt-get update \
    && apt-get install -y --no-install-recommends google-chrome-stable \
    && rm -rf /var/lib/apt/lists/* \
    && ln -sf /usr/bin/google-chrome-stable /usr/local/bin/google-chrome \
    && ln -sf /usr/bin/google-chrome-stable /usr/bin/chrome || true

# Python deps — layer reused unless requirements.txt changes.
# BuildKit pip cache avoids re-downloading wheels across rebuilds.
COPY requirements.txt .
RUN --mount=type=cache,target=/root/.cache/pip \
    pip install -r requirements.txt

# App code last — edits here do NOT re-run apt or pip
COPY app ./app
COPY tests ./tests
COPY docs ./docs
COPY scripts ./scripts
COPY pytest.ini .
COPY .env.example .

RUN mkdir -p /data \
    && chmod +x /app/scripts/docker-entrypoint.sh

EXPOSE 8000 7900

ENTRYPOINT ["/app/scripts/docker-entrypoint.sh"]
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
