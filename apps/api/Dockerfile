# Stage 1: Build dependencies
FROM python:3.12-slim AS builder

WORKDIR /build

RUN pip install --no-cache-dir pip-tools

COPY pyproject.toml .
RUN pip install --no-cache-dir --target=/build/deps .

# Stage 2: Runtime
FROM python:3.12-slim AS runtime

WORKDIR /app

RUN addgroup --system app && adduser --system --group app

COPY --from=builder /build/deps /usr/local/lib/python3.12/site-packages

COPY src/ ./src/
COPY alembic/ ./alembic/
COPY alembic.ini .

RUN mkdir -p /app/data/uploads && chown -R app:app /app

USER app

EXPOSE 8000

CMD ["python", "-m", "uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
