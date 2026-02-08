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

# 获取脚本所在目录
SCRIPT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"

# 1. 检查 quant-strategy-manager 虚拟环境
API_VENV="$SCRIPT_DIR/.venv"

if [ ! -d "$API_VENV" ]; then
    echo -e "${RED}❌ quant-strategy-manager 虚拟环境不存在: $API_VENV${NC}"
    echo -e "${YELLOW}请先运行初始化脚本：${NC}"
    echo -e "  cd $SCRIPT_DIR"
    echo -e "  bash init_env.sh"
    exit 1
fi

echo -e "${GREEN}✓${NC} 找到虚拟环境: $API_VENV"

# 2. 激活虚拟环境
echo -e "${GREEN}✓${NC} 激活虚拟环境..."
source "$API_VENV/bin/activate"

# 3. 验证 Python 环境
PYTHON_PATH=$(which python)
echo -e "${GREEN}✓${NC} Python 路径: $PYTHON_PATH"

# 4. 检查关键依赖
echo -e "${BLUE}检查依赖...${NC}"
DEPS_MISSING=0

check_package() {
    local pkg=$1
    local display_name=${2:-$1}
    python -c "import $pkg" 2>/dev/null
    if [ $? -eq 0 ]; then
        local version=$(python -c "import $pkg; print(getattr($pkg, '__version__', 'unknown'))" 2>/dev/null)
        echo -e "  ${GREEN}✓${NC} $display_name ${version}"
    else
        echo -e "  ${RED}✗${NC} $display_name (缺失)"
        DEPS_MISSING=1
    fi
}

check_package "fastapi" "fastapi"
check_package "uvicorn" "uvicorn"
check_package "jwt" "PyJWT"
check_package "pymongo" "pymongo"
check_package "strategy_manager" "vnpy-live-trading"

if [ $DEPS_MISSING -eq 1 ]; then
    echo ""
    echo -e "${RED}⚠️  依赖缺失！${NC}"
    echo -e "${YELLOW}请运行初始化脚本：${NC}"
    echo -e "  bash init_env.sh"
    exit 1
fi

echo -e "${GREEN}✓${NC} 所有依赖检查通过"
echo ""

# 5. 加载 .env 文件
if [ -f "$SCRIPT_DIR/.env" ]; then
    echo -e "${GREEN}✓${NC} 加载 .env 文件..."
    # 使用 set -a 自动导出所有变量
    set -a
    source <(grep -v '^#' "$SCRIPT_DIR/.env" | grep -v '^$' | sed 's/\r$//')
    set +a
    echo -e "${GREEN}✓${NC} .env 文件加载完成"
else
    echo -e "${YELLOW}⚠️${NC}  未找到 .env 文件，使用默认配置"
fi
echo ""

# 6. 设置环境变量（可选，提供默认值）
export API_PORT="${API_PORT:-5000}"
export MONGO_URI="${MONGO_URI:-mongodb://localhost:27017}"
export MONGO_DB="${MONGO_DB:-finance}"

echo -e "${GREEN}✓${NC} 环境变量:"
echo "   API_PORT=$API_PORT"
echo "   MONGO_URI=$MONGO_URI"
echo "   MONGO_DB=$MONGO_DB"
echo ""

# 7. 进入工作目录
cd "$SCRIPT_DIR"

echo -e "${GREEN}✓${NC} 工作目录: $(pwd)"
echo ""

# 8. 启动 API Server
echo -e "${BLUE}========================================${NC}"
echo -e "${BLUE}🚀 启动 API Server (开发模式 - 自动重载)${NC}"
echo -e "${BLUE}========================================${NC}"
echo ""
echo -e "${GREEN}✓${NC} 启动命令: uvicorn api_server:app --host 0.0.0.0 --port $API_PORT --reload"
echo -e "${YELLOW}💡 提示: 修改代码后会自动重启服务器${NC}"
echo ""

uvicorn api_server:app --host 0.0.0.0 --port $API_PORT --reload

# 清理（如果 Ctrl+C）
echo ""
echo -e "${GREEN}✓${NC} API Server 已停止"
