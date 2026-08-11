# AI Video Studio backend - deployment image
#
# Works as-is on Railway and Render (both build directly from this
# Dockerfile). Installs ffmpeg (required for rendering) since neither
# platform's default buildpack includes it.

FROM python:3.12-slim

# --- System deps: ffmpeg for rendering, curl for healthchecks ---
RUN apt-get update && \
    apt-get install -y --no-install-recommends ffmpeg curl && \
    rm -rf /var/lib/apt/lists/*

WORKDIR /app

# --- Python deps (cached separately from app code) ---
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# --- App code ---
COPY app ./app

# Directories the app writes to at runtime. On Railway/Render these are
# ephemeral unless you attach a persistent volume/disk mounted at
# /app/storage and /app/data - see README "Deploying" section.
RUN mkdir -p /app/storage /app/data

# Railway/Render inject $PORT at runtime and route traffic to it - the
# app must bind to that exact port, not a hardcoded one.
ENV PORT=8000
EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=5s --start-period=15s \
  CMD curl -f http://localhost:${PORT}/health || exit 1

# Shell form so $PORT is expanded at container start.
CMD uvicorn app.main:app --host 0.0.0.0 --port ${PORT}
