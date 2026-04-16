# Stage 1: Build all Python packages
FROM python:3.9-slim AS builder

WORKDIR /app

# Install build tools
RUN apt-get update && apt-get install -y --no-install-recommends \
        build-essential \
    && rm -rf /var/lib/apt/lists/*

# 1. Install data-access-lib
COPY data-access-lib/ /app/data-access-lib/
WORKDIR /app/data-access-lib
RUN pip install --no-cache-dir --prefix=/install -e .

# 2. Install vnpy-live-trading
WORKDIR /app
COPY vnpy-live-trading/ /app/vnpy-live-trading/
WORKDIR /app/vnpy-live-trading
RUN pip install --no-cache-dir --prefix=/install -e .

# 3. Install quant-strategy-manager
WORKDIR /app
COPY quant-strategy-manager/pyproject.toml quant-strategy-manager/README.md quant-strategy-manager/api_server.py quant-strategy-manager/simple_auth.py ./
COPY quant-strategy-manager/src ./src
RUN pip install --no-cache-dir --prefix=/install -e ".[api]"

# Stage 2: Runtime image (no build tools)
FROM python:3.9-slim

WORKDIR /app

# Copy installed packages from builder
COPY --from=builder /install /usr/local

# Copy application source
COPY data-access-lib/ /app/data-access-lib/
COPY vnpy-live-trading/ /app/vnpy-live-trading/
COPY quant-strategy-manager/ /app/quant-strategy-manager/

# Install without dependencies (already satisfied from /usr/local)
WORKDIR /app/quant-strategy-manager
RUN pip install --no-cache-dir --no-deps -e .

# Create logs directory
RUN mkdir -p /app/logs

# Environment variables
ENV PYTHONUNBUFFERED=1
ENV API_PORT=5000

# Expose and run
EXPOSE 5000
CMD ["python", "api_server.py"]