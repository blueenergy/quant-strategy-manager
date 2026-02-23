FROM python:3.9-slim

# Install system dependencies
RUN apt-get update && apt-get install -y \
    build-essential \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Copy project files
COPY pyproject.toml .
COPY src/ ./src/
COPY api_server.py .
COPY simple_auth.py .

# Install the package with API dependencies
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
