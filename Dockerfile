# syntax=mirror.gcr.io/docker/dockerfile:1

# Docker Hub images come through mirror.gcr.io, Google's public Docker Hub
# mirror: CI's anonymous Docker Hub pulls hit its rate limit (429 Too Many
# Requests). Pinned so Dependabot's docker ecosystem can bump them (an
# unpinned tag can't be bumped — or reproduced). Node major tracks web/.nvmrc.
FROM ghcr.io/astral-sh/uv:0.12.23 AS uv

# --- Frontend build -----------------------------------------------------
FROM mirror.gcr.io/library/node:24-alpine AS frontend-build
WORKDIR /app/web
COPY web/package.json web/package-lock.json ./
RUN npm ci
COPY web/ ./
RUN npm run build

# --- Backend + compiled frontend ----------------------------------------
FROM mirror.gcr.io/library/python:3.13-slim AS backend
COPY --from=uv /uv /uvx /bin/
WORKDIR /app

# Install deps first so this layer is cached across app-code-only changes.
COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-dev

COPY app/ ./app/
COPY migrations/ ./migrations/
COPY alembic.ini ./
COPY --from=frontend-build /app/web/dist ./web/dist

ENV PATH="/app/.venv/bin:$PATH" \
    PYTHONUNBUFFERED=1

EXPOSE 8000
CMD ["sh", "-c", "alembic upgrade head && uvicorn app.main:app --host 0.0.0.0 --port 8000"]
