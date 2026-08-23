# syntax=docker/dockerfile:1.7
FROM python:3.12-slim AS builder

COPY --from=ghcr.io/astral-sh/uv:0.12.5 /uv /uvx /bin/
ENV UV_COMPILE_BYTECODE=1 UV_LINK_MODE=copy UV_PYTHON_DOWNLOADS=0
WORKDIR /app

COPY pyproject.toml uv.lock README.md ./
RUN --mount=type=cache,target=/root/.cache/uv uv sync --locked --no-dev --no-install-project

COPY src ./src
RUN --mount=type=cache,target=/root/.cache/uv uv sync --locked --no-dev --no-editable

FROM python:3.12-slim AS runtime
ENV PYTHONUNBUFFERED=1 PYTHONDONTWRITEBYTECODE=1 PATH="/app/.venv/bin:$PATH"
WORKDIR /app
RUN groupadd --system app && useradd --system --gid app --create-home app

COPY --from=builder /app/.venv /app/.venv
COPY alembic ./alembic
COPY alembic.ini ./alembic.ini
USER app
EXPOSE 8000
CMD ["uvicorn", "rag_service.main:app", "--host", "0.0.0.0", "--port", "8000", "--proxy-headers"]
