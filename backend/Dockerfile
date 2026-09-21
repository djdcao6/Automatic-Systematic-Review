# The backend image: what Render builds (see render.yaml) and what CI builds to keep it working.
# Build from the repo root:  docker build -t asr-backend backend
FROM python:3.11-slim-bookworm

# Same uv the lockfile and build backend (uv_build) were made with.
COPY --from=ghcr.io/astral-sh/uv:0.12.5 /uv /bin/uv

# psql, for inspecting the database from a shell on the service (Render's SSH). Debian's
# client is older than the server, so it is for looking, not for pg_dump.
RUN apt-get update \
    && apt-get install -y --no-install-recommends postgresql-client \
    && rm -rf /var/lib/apt/lists/*

ENV UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    UV_PYTHON_DOWNLOADS=never \
    PYTHONUNBUFFERED=1
WORKDIR /app

# Dependencies first, so a code change does not reinstall them.
COPY pyproject.toml uv.lock README.md ./
RUN uv sync --locked --no-dev --no-install-project

COPY src ./src
COPY alembic.ini ./
COPY migrations ./migrations
# The operator scripts (delete_account.py and friends), run from a shell on the service.
COPY scripts ./scripts
RUN uv sync --locked --no-dev

ENV PATH="/app/.venv/bin:$PATH"

# One worker on purpose: the sign-in and sign-up rate limits are kept in this process
# (see rate_limit.py), and PDFs live on a disk that only one instance can mount.
# Runs as root: the persistent disk's ownership is not documented for other users, so
# dropping privileges is left until it has been checked on a real service.
EXPOSE 10000
CMD ["sh", "-c", "exec uvicorn asr_backend.main:app --host 0.0.0.0 --port ${PORT:-10000}"]
