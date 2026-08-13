FROM python:3.11-slim AS base

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    libpq-dev \
    curl \
    git \
    && rm -rf /var/lib/apt/lists/*

COPY pyproject.toml .
# Install ONLY production deps (no dev extras)
RUN pip install -e "."

# Download spaCy model
RUN python -m spacy download en_core_web_sm

# ---- Worker target (build with: --target worker) ----
FROM base AS worker
COPY . .
RUN chmod +x scripts/start_api.sh scripts/start_worker.sh scripts/start_beat.sh
CMD ["./scripts/start_worker.sh"]

# ---- API target (default final stage for Railway/Render) ----
FROM base AS api
COPY . .
RUN chmod +x scripts/start_api.sh scripts/start_worker.sh scripts/start_beat.sh
EXPOSE 8000
CMD ["./scripts/start_api.sh"]
