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
    libgl1-mesa-glx \
    libglib2.0-0 \
    && rm -rf /var/lib/apt/lists/*

# Copy installed packages from builder
COPY --from=builder /root/.local /root/.local
ENV PATH=/root/.local/bin:$PATH

# Copy application source
COPY coordinator/ ./coordinator/
COPY config.py .

# Environment defaults
ENV PORT=8000
ENV DATABASE_URL=""
ENV JWT_SECRET="change-me-in-production"
ENV LOG_LEVEL="INFO"

# Run with Gunicorn + Uvicorn workers for production performance
CMD gunicorn coordinator.main:app \
    --workers 4 \
    --worker-class uvicorn.workers.UvicornWorker \
    --bind 0.0.0.0:$PORT
