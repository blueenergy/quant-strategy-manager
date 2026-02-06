#!/bin/bash
# quant-strategy-manager 环境初始化脚本

set -e

GREEN='\033[0;32m'
BLUE='\033[0;34m'
YELLOW='\033[1;33m'
NC='\033[0m'

echo -e "${BLUE}========================================${NC}"
echo -e "${BLUE}初始化 quant-strategy-manager 环境${NC}"
echo -e "${BLUE}========================================${NC}"
echo ""

# 1. 创建虚拟环境
if [ -d ".venv" ]; then
    echo -e "${YELLOW}⚠️  虚拟环境已存在，跳过创建${NC}"
else
    echo -e "${GREEN}✓${NC} 创建虚拟环境..."
    python -m venv .venv
fi

# 2. 激活环境
echo -e "${GREEN}✓${NC} 激活虚拟环境..."
source .venv/bin/activate

# 3. 升级 pip
echo -e "${GREEN}✓${NC} 升级 pip..."
pip install --upgrade pip

# 4. 安装本项目及依赖
echo -e "${GREEN}✓${NC} 安装 quant-strategy-manager 核心依赖..."
pip install -e .

echo -e "${GREEN}✓${NC} 安装 API 服务器依赖..."
pip install -e ".[api]"

echo -e "${GREEN}✓${NC} 安装日志管理依赖（可选）..."
pip install -e ".[logging]"

echo -e "${GREEN}✓${NC} 安装 vnpy-live-trading 包（可编辑模式）..."
pip install -e ../vnpy-live-trading

echo ""
echo -e "${BLUE}========================================${NC}"
echo -e "${GREEN}✅ 环境初始化完成！${NC}"
echo -e "${BLUE}========================================${NC}"
echo ""
echo -e "使用方法："
echo -e "  ${GREEN}source .venv/bin/activate${NC}  # 激活环境"
echo -e "  ${GREEN}./start_api_server.sh${NC}      # 启动 API Server"
echo ""
