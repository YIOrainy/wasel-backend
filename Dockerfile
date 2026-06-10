# syntax=docker/dockerfile:1
FROM python:3.13-slim

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1

WORKDIR /app

# uv — a much faster installer/resolver than pip (Rust). Pin to :latest here;
# pin a concrete version (e.g. :0.7.0) for fully reproducible builds.
COPY --from=ghcr.io/astral-sh/uv:latest /uv /usr/local/bin/uv

# Dependencies in their own layer, BEFORE the app code, so changing code never
# re-triggers a dependency install. The cache mount persists the wheel cache
# across builds — reused even on --no-cache builds — so re-installs are fast.
COPY requirements.txt .
RUN --mount=type=cache,target=/root/.cache/uv \
    uv pip install --system -r requirements.txt

COPY app ./app
COPY alembic ./alembic
COPY alembic.ini .
COPY pyproject.toml .

EXPOSE 8000

# Apply pending migrations, then start the server.
CMD ["sh", "-c", "alembic upgrade head && uvicorn app.entrypoints.api.main:app --host 0.0.0.0 --port 8000"]
