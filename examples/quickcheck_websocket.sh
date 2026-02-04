#!/bin/bash

# WebSocket 连接快速检查脚本
# 在远程服务器和本地机器都可以运行

set -e

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

echo -e "${BLUE}========================================${NC}"
echo -e "${BLUE}  WebSocket 连接快速检查${NC}"
echo -e "${BLUE}========================================${NC}"
echo ""

# 参数说明
if [ $# -lt 2 ]; then
    echo -e "${YELLOW}使用方法:${NC}"
    echo "  $0 <服务器地址> <API端口> [WebSocket端口1] [WebSocket端口2] ..."
    echo ""
    echo -e "${YELLOW}示例:${NC}"
    echo "  # 检查本地服务器"
    echo "  $0 localhost 5000"
    echo ""
    echo "  # 检查远程服务器"
    echo "  $0 192.168.1.100 5000 54321 54322"
    echo ""
    echo "  # 检查 SSH 隧道转发"
    echo "  $0 127.0.0.1 5000 8765"
    echo ""
    exit 1
fi

HOST=$1
API_PORT=$2
shift 2
WS_PORTS=("$@")

# 如果没有指定 WebSocket 端口，使用常见的
if [ ${#WS_PORTS[@]} -eq 0 ]; then
    WS_PORTS=(54321 54322 54323 54324 54325)
fi

# ========== 检查 1: 网络连接 ==========
echo -e "${YELLOW}[检查 1] 网络连接${NC}"
if ping -c 1 "$HOST" &>/dev/null; then
    echo -e "${GREEN}✓ 主机 $HOST 可达${NC}"
else
    echo -e "${RED}✗ 主机 $HOST 无法连接${NC}"
    if [ "$HOST" != "localhost" ] && [ "$HOST" != "127.0.0.1" ]; then
        echo "  建议检查:"
        echo "  - IP 地址是否正确?"
        echo "  - 网络连接是否正常?"
        echo "  - 是否需要 VPN?"
        echo ""
    fi
fi
echo ""

# ========== 检查 2: API 端口 ==========
echo -e "${YELLOW}[检查 2] API 端口 (${API_PORT})${NC}"

# 尝试 nc (netcat)
if command -v nc &>/dev/null; then
    if nc -zv "$HOST" "$API_PORT" 2>/dev/null; then
        echo -e "${GREEN}✓ API 端口 ${API_PORT} 已开放${NC}"
    else
        echo -e "${RED}✗ API 端口 ${API_PORT} 无法连接${NC}"
        echo "  可能原因:"
        echo "  - 防火墙阻止"
        echo "  - API 服务未启动"
        echo "  - 端口不正确"
        echo ""
    fi
else
    # 使用 /dev/tcp 作为备选
    if timeout 2 bash -c "echo >/dev/tcp/$HOST/$API_PORT" 2>/dev/null; then
        echo -e "${GREEN}✓ API 端口 ${API_PORT} 已开放${NC}"
    else
        echo -e "${RED}✗ API 端口 ${API_PORT} 无法连接${NC}"
    fi
fi
echo ""

# ========== 检查 3: API 响应 ==========
echo -e "${YELLOW}[检查 3] API 响应${NC}"

API_URL="http://$HOST:$API_PORT/api/workers"
HTTP_CODE=$(curl -s -o /dev/null -w "%{http_code}" "$API_URL" 2>/dev/null || echo "000")

if [ "$HTTP_CODE" = "200" ]; then
    echo -e "${GREEN}✓ API 返回 HTTP 200${NC}"
    
    # 获取并显示 API 数据
    API_RESPONSE=$(curl -s "$API_URL" 2>/dev/null || echo "{}")
    
    # 解析 JSON 中的 worker 数量
    if command -v jq &>/dev/null; then
        WORKER_COUNT=$(echo "$API_RESPONSE" | jq '.total_workers // 0' 2>/dev/null || echo "0")
        echo "  Workers 数量: $WORKER_COUNT"
        
        if [ "$WORKER_COUNT" -gt 0 ]; then
            echo "  Worker 列表:"
            echo "$API_RESPONSE" | jq '.workers | keys[]' 2>/dev/null | while read -r worker; do
                echo "    - $(echo $worker | tr -d '"')"
            done
        fi
    else
        echo "  API 响应: ${API_RESPONSE:0:100}..."
    fi
elif [ "$HTTP_CODE" = "000" ]; then
    echo -e "${RED}✗ 无法连接到 API${NC}"
    echo "  检查步骤:"
    echo "  1. curl -v http://$HOST:$API_PORT/api/workers"
    echo "  2. 查看错误信息"
else
    echo -e "${RED}✗ API 返回错误代码: $HTTP_CODE${NC}"
    echo "  可能原因:"
    echo "  - 404: 路由不存在"
    echo "  - 500: 服务器错误"
    echo "  - 503: 服务不可用"
fi
echo ""

# ========== 检查 4: WebSocket 端口 ==========
echo -e "${YELLOW}[检查 4] WebSocket 端口${NC}"

if [ ${#WS_PORTS[@]} -gt 0 ]; then
    for ws_port in "${WS_PORTS[@]}"; do
        if command -v nc &>/dev/null; then
            if nc -zv "$HOST" "$ws_port" 2>/dev/null; then
                echo -e "${GREEN}✓ WebSocket 端口 ${ws_port} 已开放${NC}"
            else
                echo -e "${YELLOW}⚠ WebSocket 端口 ${ws_port} 无法连接${NC}"
            fi
        else
            if timeout 2 bash -c "echo >/dev/tcp/$HOST/$ws_port" 2>/dev/null; then
                echo -e "${GREEN}✓ WebSocket 端口 ${ws_port} 已开放${NC}"
            else
                echo -e "${YELLOW}⚠ WebSocket 端口 ${ws_port} 无法连接${NC}"
            fi
        fi
    done
    echo ""
fi

# ========== 检查 5: 防火墙状态（仅适用于本地 Linux）==========
if [ "$HOST" = "localhost" ] || [ "$HOST" = "127.0.0.1" ]; then
    echo -e "${YELLOW}[检查 5] 防火墙状态${NC}"
    
    if command -v firewall-cmd &>/dev/null; then
        echo "检测到 firewalld..."
        
        # 检查是否启用
        if sudo firewall-cmd --state 2>/dev/null | grep -q "running"; then
            echo -e "${GREEN}✓ firewalld 正在运行${NC}"
            
            # 列出开放的端口
            OPEN_PORTS=$(sudo firewall-cmd --list-ports 2>/dev/null || echo "无权限")
            echo "  已开放端口: $OPEN_PORTS"
            
            # 检查特定端口
            if echo "$OPEN_PORTS" | grep -q "$API_PORT"; then
                echo -e "${GREEN}✓ API 端口 $API_PORT 已开放${NC}"
            else
                echo -e "${YELLOW}⚠ API 端口 $API_PORT 未在防火墙中开放${NC}"
                echo "    运行: sudo firewall-cmd --add-port=$API_PORT/tcp --permanent && sudo firewall-cmd --reload"
            fi
        else
            echo -e "${GREEN}✓ firewalld 未运行（防火墙未激活）${NC}"
        fi
    elif command -v ufw &>/dev/null; then
        echo "检测到 ufw..."
        if sudo ufw status 2>/dev/null | grep -q "Status: active"; then
            echo -e "${GREEN}✓ ufw 正在运行${NC}"
        else
            echo -e "${GREEN}✓ ufw 未激活${NC}"
        fi
    else
        echo -e "${YELLOW}ℹ 未检测到 firewalld 或 ufw${NC}"
    fi
    echo ""
fi

# ========== 总结 ==========
echo -e "${BLUE}========================================${NC}"
echo -e "${BLUE}  检查完成${NC}"
echo -e "${BLUE}========================================${NC}"
echo ""
echo -e "${YELLOW}后续步骤:${NC}"
echo "1. 在浏览器中打开诊断工具:"
echo "   file:///home/shuyolin/trading/quantFinance-dashboard/diagnose_integrated.html"
echo ""
echo "2. 在浏览器中输入 API 地址:"
echo "   http://$HOST:$API_PORT/api/workers"
echo ""
echo "3. 如果仍有问题，运行调试命令:"
echo "   curl -v http://$HOST:$API_PORT/api/workers"
echo ""
echo "4. 检查远程服务器是否运行了必要的服务:"
echo "   ps aux | grep -E '(strategy_manager|api_with_log_streaming)'"
echo ""
