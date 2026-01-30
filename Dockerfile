# Multi-stage build for Ukrainian Name Detection API

# Stage 1: Build stage
FROM python:3.11-slim as builder

WORKDIR /app

# Install build dependencies
RUN apt-get update && apt-get install -y \
    build-essential \
    cmake \
    git \
    && rm -rf /var/lib/apt/lists/*

# Copy requirements and install dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir --user -r requirements.txt

# Download spaCy model
RUN python -m spacy download uk_core_news_md

# Stage 2: Runtime stage
FROM python:3.11-slim

WORKDIR /app

# Install runtime dependencies
RUN apt-get update && apt-get install -y \
    libgomp1 \
    && rm -rf /var/lib/apt/lists/*

# Copy installed packages from builder
COPY --from=builder /root/.local /root/.local
ENV PATH=/root/.local/bin:$PATH

# Copy spaCy model data
COPY --from=builder /root/.local/lib/python3.11/site-packages/uk_core_news_md /root/.local/lib/python3.11/site-packages/uk_core_news_md

# Copy application code
COPY app/ ./app/
COPY tests/ ./tests/

# Create models directory
RUN mkdir -p /app/models

# Environment variables
ENV PYTHONUNBUFFERED=1
ENV NAME_DETECTOR_HOST=0.0.0.0
ENV NAME_DETECTOR_PORT=8000

# Expose port
EXPOSE 8000

# Health check
HEALTHCHECK --interval=30s --timeout=10s --start-period=60s --retries=3 \
    CMD curl -f http://localhost:8000/health || exit 1

# Run the application
CMD ["python", "-m", "app.main"]
