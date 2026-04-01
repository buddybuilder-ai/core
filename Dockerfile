# =============================================================================
# BuddyBuilder AI - Production Dockerfile
# =============================================================================
# Single-stage build with BuildKit cache mount:
# - pip downloads cached in BuildKit cache (NOT exported to GHA)
# - Only installed site-packages land in the image layer
# - Deps layer cached independently from app code layer

FROM python:3.11-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PYTHONPATH=/app \
    APP_HOME=/app

WORKDIR /app

# Create non-root user
RUN groupadd --gid 1000 appgroup && \
    useradd --uid 1000 --gid appgroup --shell /bin/bash --create-home appuser

# Copy only manifest — this layer is cached until pyproject.toml changes
COPY pyproject.toml README.md ./

# Install all runtime dependencies
# --mount=type=cache: pip downloads go to BuildKit cache volume, NOT image layer
# build-essential needed for chromadb C extensions; removed after install
RUN --mount=type=cache,target=/root/.cache/pip \
    apt-get update && apt-get install -y --no-install-recommends build-essential curl && \
    pip install --upgrade pip hatchling && \
    pip install \
        $(python -c "import tomllib; f=open('pyproject.toml','rb'); data=tomllib.load(f); print(' '.join(data['project']['dependencies']))") && \
    apt-get purge -y --auto-remove build-essential && \
    rm -rf /var/lib/apt/lists/*

# Copy application code — only invalidates layers below this line
COPY --chown=appuser:appgroup src/ ./src/
COPY --chown=appuser:appgroup alembic.ini ./
COPY --chown=appuser:appgroup migrations/ ./migrations/

# Copy rag_constants so rag_service.py can import it at runtime
# (rag_service.py does sys.path.insert to /app/rag_pipeline/)
COPY --chown=appuser:appgroup rag_pipeline/rag_constants.py ./rag_pipeline/

# Install app package only (deps already installed above — no re-download)
RUN --mount=type=cache,target=/root/.cache/pip \
    pip install --no-deps .

USER appuser

EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=10s --start-period=5s --retries=3 \
    CMD curl -f http://localhost:8000/health || exit 1

CMD ["uvicorn", "src.main:app", "--host", "0.0.0.0", "--port", "8000"]
