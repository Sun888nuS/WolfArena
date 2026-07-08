FROM ghcr.io/astral-sh/uv:0.11.12 AS uv

FROM python:3.11-slim

ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1
ENV PATH="/app/.venv/bin:$PATH"

WORKDIR /app

COPY --from=uv /uv /uvx /usr/local/bin/
COPY backend/pyproject.toml ./pyproject.toml
COPY backend/uv.lock ./uv.lock
RUN uv sync --frozen --no-dev --no-install-project

COPY backend/app ./app
COPY backend/alembic.ini ./alembic.ini

EXPOSE 8000

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
