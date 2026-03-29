FROM python:3.12-slim AS base

RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# ── Dependencies stage ────────────────────────────────────────────────
FROM base AS deps

COPY pyproject.toml ./
RUN pip install --no-cache-dir ".[dev]"

# ── Application stage ─────────────────────────────────────────────────
FROM deps AS app

COPY . .

# Create non-root user
ARG HOST_UID=9999
ARG HOST_GID=9999
RUN groupadd -g ${HOST_GID} appuser || true \
    && useradd -u ${HOST_UID} -g ${HOST_GID} -m appuser || true \
    && mkdir -p /app/logs \
    && chown -R ${HOST_UID}:${HOST_GID} /app

USER ${HOST_UID}:${HOST_GID}

EXPOSE 8000

CMD ["uvicorn", "ai_proxy.app:app", "--host", "0.0.0.0", "--port", "8000"]
