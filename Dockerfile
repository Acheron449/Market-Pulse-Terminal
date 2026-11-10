# Market Pulse Terminal — single-container build.
#
# Stage 1 builds the SPA, stage 2 runs the API and serves that build from the same
# origin (app/main.py mounts frontend/dist when it exists), so SSE, the API and the
# static assets share one port and one CORS policy.
#
#   docker build -t market-pulse-terminal .
#   docker run --rm -p 8000:8000 --env-file .env market-pulse-terminal

# ---------- frontend ----------
FROM node:20-slim AS web
WORKDIR /web
RUN corepack enable
COPY frontend/package.json frontend/pnpm-lock.yaml ./
RUN pnpm install --frozen-lockfile
COPY frontend/ ./
# tsc --noEmit && vite build (frontend/package.json "build")
RUN pnpm build

# ---------- backend ----------
FROM python:3.12-slim AS runtime
COPY --from=ghcr.io/astral-sh/uv:0.5.11 /uv /usr/local/bin/uv
ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy
WORKDIR /app

# Dependencies first so a source change does not re-resolve them.
COPY backend/pyproject.toml backend/uv.lock ./backend/
RUN cd backend && uv sync --frozen --no-dev

COPY backend/ ./backend/
COPY --from=web /web/dist ./frontend/dist

# kernels write SQLite into <repo>/backend/data (DATABASE_PATH default).
RUN mkdir -p /app/backend/data
VOLUME ["/app/backend/data"]

EXPOSE 8000
WORKDIR /app/backend
HEALTHCHECK --interval=30s --timeout=5s --start-period=20s --retries=3 \
    CMD python -c "import urllib.request, sys; sys.exit(0 if urllib.request.urlopen('http://127.0.0.1:8000/api/health', timeout=3).status == 200 else 1)"
CMD ["/app/backend/.venv/bin/uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
