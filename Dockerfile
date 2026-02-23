FROM python:3.9-slim

# Install system dependencies
RUN apt-get update && apt-get install -y \
    build-essential \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# 1. Install vnpy-live-trading dependencies
COPY vnpy-live-trading/ /app/vnpy-live-trading/
WORKDIR /app/vnpy-live-trading
RUN pip install --no-cache-dir -e .

# 2. Install quant-strategy-manager dependencies
WORKDIR /app/quant-strategy-manager
COPY quant-strategy-manager/pyproject.toml .
COPY quant-strategy-manager/src/ ./src/
COPY quant-strategy-manager/api_server.py .
COPY quant-strategy-manager/simple_auth.py .

RUN pip install --no-cache-dir -e ".[api]"

# Create logs directory
RUN mkdir -p logs

# Expose API port
EXPOSE 5000

# Set environment variables
ENV PYTHONUNBUFFERED=1
ENV API_PORT=5000

# Run the API server
CMD ["python", "api_server.py"]
