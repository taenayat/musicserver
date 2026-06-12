# Multi-stage build: a Node stage compiles the React frontend, then the Python
# stage runs the backend and serves the built bundle as static files.
# Build context is ./gateway (see docker-compose.yml), so paths below are
# relative to the gateway directory.

# ── Stage 1: build the React frontend ─────────────────────────────────────────
FROM node:20-slim AS frontend
WORKDIR /app/frontend
COPY frontend/package*.json ./
RUN npm ci
COPY frontend/ ./
RUN npm run build
# → /app/frontend/dist

# ── Stage 2: Python runtime ───────────────────────────────────────────────────
FROM python:3.12-slim
ENV PYTHONUNBUFFERED=1
WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends \
        ca-certificates git ffmpeg \
    && rm -rf /var/lib/apt/lists/*

# deno: yt-dlp needs a JS runtime to extract current YouTube formats. Without it
# newer yt-dlp warns "No supported JavaScript runtime" and formats go missing.
# The static binary from the official image is enough.
COPY --from=denoland/deno:bin /deno /usr/local/bin/deno

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY *.py ./
COPY --from=frontend /app/frontend/dist ./frontend/dist

EXPOSE 8080
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8080", "--log-level", "info", "--access-log"]
