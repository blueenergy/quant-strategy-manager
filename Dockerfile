# Stage 1: Build all Python packages
FROM python:3.10-slim AS builder

WORKDIR /app

# Install build tools
RUN apt-get update && apt-get install -y --no-install-recommends \
        build-essential \
    && rm -rf /var/lib/apt/lists/*

# 1. Install data-access-lib
COPY data-access-lib/ /app/data-access-lib/
WORKDIR /app/data-access-lib
RUN pip install --no-cache-dir --prefix=/install -e .

# 2. Install strategy-cores (framework-free strategy logic shared with the
# backtest shell). Dependency-free, so it installs in any order.
WORKDIR /app
COPY strategy-cores/ /app/strategy-cores/
WORKDIR /app/strategy-cores
RUN pip install --no-cache-dir --prefix=/install -e .

# 3. Install vnpy-live-trading
# ta-lib 上界：0.8.2 只发了 cp315 的 wheel，cp39 上 pip 会回落到 sdist，而编译它
# 需要 ta-lib 的 C 头文件 —— 这个镜像里没有 ⇒ 构建失败（2026-10-16 实测）。
# 0.8.1 是最后一个带 cp39/cp310 manylinux wheel 的版本，上游恢复 wheel 后可以撤掉。
WORKDIR /app
COPY vnpy-live-trading/ /app/vnpy-live-trading/
WORKDIR /app/vnpy-live-trading
RUN pip install --no-cache-dir --prefix=/install -e . "ta-lib<0.8.2"

# 4. Install quant-strategy-manager
WORKDIR /app
COPY quant-strategy-manager/pyproject.toml quant-strategy-manager/README.md quant-strategy-manager/api_server.py quant-strategy-manager/simple_auth.py ./
COPY quant-strategy-manager/src ./src
RUN pip install --no-cache-dir --prefix=/install -e ".[api]"

# Stage 2: Runtime image (no build tools)
FROM python:3.10-slim

WORKDIR /app

# Copy installed packages from builder
COPY --from=builder /install /usr/local

# Copy application source
COPY data-access-lib/ /app/data-access-lib/
COPY strategy-cores/ /app/strategy-cores/
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