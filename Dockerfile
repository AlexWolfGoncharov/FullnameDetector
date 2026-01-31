# Multi-stage build for Ukrainian Name Detection API

# Stage 1: Build stage
FROM python:3.11-slim AS builder

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

# Install spaCy Ukrainian model (direct pip: spacy download has compatibility issues)
# Requires spacy>=3.8 for uk_core_news_md-3.8.0
RUN pip install --no-cache-dir --user "spacy>=3.8.0,<3.9.0" && \
    pip install --no-cache-dir --user \
    "https://github.com/explosion/spacy-models/releases/download/uk_core_news_md-3.8.0/uk_core_news_md-3.8.0-py3-none-any.whl"

# Stage 1b: Завантаження всіх моделей (LLM, RoBERTa)
# docker build --build-arg HF_TOKEN=hf_xxx .
ARG HF_TOKEN
ENV HF_TOKEN=${HF_TOKEN}
COPY scripts/download_models.py /app/scripts/
RUN mkdir -p /app/models && python /app/scripts/download_models.py

# Stage 2: Runtime stage
FROM python:3.11-slim

WORKDIR /app

# Install runtime dependencies (curl for healthcheck)
RUN apt-get update && apt-get install -y \
    libgomp1 \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Copy installed packages from builder (includes spaCy model)
COPY --from=builder /root/.local /root/.local
ENV PATH=/root/.local/bin:$PATH

# Copy models (LLM GGUF + RoBERTa HF cache)
COPY --from=builder /app/models /app/models

# RoBERTa NER шукає в HF_HOME
ENV HF_HOME=/app/models/hf_cache

# Copy application code
COPY app/ ./app/
COPY tests/ ./tests/

# Create directories
RUN mkdir -p /app/logs

# Environment variables
ENV PYTHONUNBUFFERED=1
ENV PYTHONPATH=/app
ENV NAME_DETECTOR_HOST=0.0.0.0
ENV NAME_DETECTOR_PORT=8000
ENV NAME_DETECTOR_LLM_ENABLED=true
ENV NAME_DETECTOR_LLM_BACKEND=llama_cpp

# Expose port
EXPOSE 8000

# Health check (start-period: LLM ~2.5GB завантажується при старті)
HEALTHCHECK --interval=30s --timeout=10s --start-period=180s --retries=3 \
    CMD curl -f http://localhost:8000/health || exit 1

# Run the application
CMD ["python", "-m", "app.main"]
