#!/bin/bash
# Strategy Manager API Server 启动脚本
# 
# 使用方法：
#   ./start_api_server.sh
#   或
#   bash start_api_server.sh

set -e  # 遇到错误立即退出

# 颜色输出
GREEN='\033[0;32m'
BLUE='\033[0;34m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
NC='\033[0m' # No Color

echo -e "${BLUE}========================================${NC}"
echo -e "${BLUE}Strategy Manager API Server${NC}"
echo -e "${BLUE}========================================${NC}"
echo ""

# 1. 检查 vnpy 虚拟环境
VNPY_VENV="/home/shuyolin/trading/vnpy-live-trading/.venv"

if [ ! -d "$VNPY_VENV" ]; then
    echo -e "${YELLOW}⚠️  vnpy 虚拟环境不存在: $VNPY_VENV${NC}"
    exit 1
fi

echo -e "${GREEN}✓${NC} 找到 vnpy 虚拟环境: $VNPY_VENV"

# 2. 激活虚拟环境（使用绝对路径）
echo -e "${GREEN}✓${NC} 激活虚拟环境..."
source "$VNPY_VENV/bin/activate"

# 3. 验证 Python 环境
PYTHON_PATH=$(which python)
echo -e "${GREEN}✓${NC} Python 路径: $PYTHON_PATH"

# 4. 检查 vnpy-live-trading 依赖
echo -e "${BLUE}检查 vnpy-live-trading 依赖...${NC}"
VNPY_DEPS_MISSING=0

check_package() {
    local pkg=$1
    local display_name=${2:-$1}
    python -c "import $pkg" 2>/dev/null
    if [ $? -eq 0 ]; then
        local version=$(python -c "import $pkg; print(getattr($pkg, '__version__', 'unknown'))" 2>/dev/null)
        echo -e "  ${GREEN}✓${NC} $display_name ${version}"
    else
        echo -e "  ${RED}✗${NC} $display_name (缺失)"
        VNPY_DEPS_MISSING=1
    fi
}

check_package "vnpy" "vnpy"
check_package "vnpy_ctastrategy" "vnpy_ctastrategy"
check_package "pymongo" "pymongo"
check_package "websockets" "websockets"

if [ $VNPY_DEPS_MISSING -eq 1 ]; then
    echo ""
    echo -e "${RED}⚠️  vnpy 环境缺少依赖！${NC}"
    echo -e "${YELLOW}请在 vnpy 环境中安装：${NC}"
    echo -e "  cd ~/trading/vnpy-live-trading"
    echo -e "  source .venv/bin/activate"
    echo -e "  pip install -r requirements.txt"
    exit 1
fi

# 5. 检查 quant-strategy-manager API Server 依赖
echo ""
echo -e "${BLUE}检查 API Server 依赖...${NC}"
API_DEPS_MISSING=0

check_package "fastapi" "fastapi"
check_package "uvicorn" "uvicorn"

if [ $API_DEPS_MISSING -eq 1 ]; then
    echo ""
    echo -e "${RED}⚠️  API Server 依赖缺失！${NC}"
    echo -e "${YELLOW}请安装 API Server 依赖：${NC}"
    echo -e "  cd ~/trading/quant-strategy-manager"
    echo -e "  pip install -r requirements-api.txt"
    exit 1
fi

echo -e "${GREEN}✓${NC} 所有依赖检查通过"
echo ""

# 6. 设置环境变量（可选）
export API_PORT="${API_PORT:-5000}"
export MONGO_URI="${MONGO_URI:-mongodb://localhost:27017}"
export MONGO_DB="${MONGO_DB:-finance}"

echo -e "${GREEN}✓${NC} 环境变量:"
echo "   API_PORT=$API_PORT"
echo "   MONGO_URI=$MONGO_URI"
echo "   MONGO_DB=$MONGO_DB"
echo ""

# 7. 进入 quant-strategy-manager 目录
SCRIPT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"
cd "$SCRIPT_DIR"

echo -e "${GREEN}✓${NC} 工作目录: $(pwd)"
echo ""

# 8. 启动 API Server
echo -e "${BLUE}========================================${NC}"
echo -e "${BLUE}🚀 启动 API Server...${NC}"
echo -e "${BLUE}========================================${NC}"
echo ""

python api_server.py

# 清理（如果 Ctrl+C）
echo ""
echo -e "${GREEN}✓${NC} API Server 已停止"
