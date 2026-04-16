# ── Build Stage ─────────────────────────────────────────────────────────────
FROM python:3.11-slim as builder

WORKDIR /app

# Install system dependencies for core AI and DB drivers
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    libpq-dev \
    && rm -rf /var/lib/apt/lists/*

# Install python dependencies
COPY coordinator/requirements.txt .
RUN pip install --no-cache-dir --upgrade pip && \
    pip install --no-cache-dir --user -r requirements.txt

# ── Production Stage ────────────────────────────────────────────────────────
FROM python:3.11-slim

WORKDIR /app

# Install runtime dependencies for Postgres and OpenCV
RUN apt-get update && apt-get install -y --no-install-recommends \
    libpq5 \
    libgl1 \
    libglib2.0-0 \
    && rm -rf /var/lib/apt/lists/*

# Copy requirements and install directly in production image
# This avoids the "not found" binary path issues from multi-stage builds
COPY coordinator/requirements.txt .
RUN pip install --no-cache-dir --upgrade pip && \
    pip install --no-cache-dir -r requirements.txt

# Copy application source
COPY coordinator/ ./coordinator/
COPY config.py .

# Environment defaults
ENV PORT=8000
ENV DATABASE_URL=""
ENV JWT_SECRET="change-me-in-production"
ENV LOG_LEVEL="INFO"

# Run with Gunicorn + Uvicorn workers
# Using 'python -m gunicorn' is the most robust way to call the binary
CMD python -m gunicorn coordinator.main:app \
    --workers 1 \
    --worker-class uvicorn.workers.UvicornWorker \
    --bind 0.0.0.0:$PORT
