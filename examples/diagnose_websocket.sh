#!/bin/bash
# 快速诊断脚本 - 检查 WebSocket 连接问题

echo "=========================================="
echo "quantFinance Dashboard - WebSocket 诊断"
echo "=========================================="

# 配置
REMOTE_SERVER="${1:-localhost}"
API_PORT="${2:-5000}"
WS_PORT="${3:-54321}"

echo ""
echo "🔍 诊断信息："
echo "  远程服务器: $REMOTE_SERVER"
echo "  API 端口: $API_PORT"
echo "  WebSocket 端口范围: $WS_PORT (示例)"
echo ""

# 第 1 步：检查基本网络连接
echo "✅ 第 1 步：检查网络连接..."
if ping -c 1 $REMOTE_SERVER > /dev/null 2>&1; then
    echo "  ✅ 可以 ping 通 $REMOTE_SERVER"
else
    echo "  ❌ 无法 ping 通 $REMOTE_SERVER（可能是防火墙或网络问题）"
fi

# 第 2 步：检查 API 服务端口
echo ""
echo "✅ 第 2 步：检查 API 服务端口..."
if nc -z -w2 $REMOTE_SERVER $API_PORT 2>/dev/null; then
    echo "  ✅ API 端口 $API_PORT 开放"
else
    echo "  ❌ API 端口 $API_PORT 无响应（服务可能未启动）"
fi

# 第 3 步：尝试调用 API
echo ""
echo "✅ 第 3 步：尝试调用 API..."
API_URL="http://$REMOTE_SERVER:$API_PORT/api/workers"
echo "  URL: $API_URL"

RESPONSE=$(curl -s -w "\n%{http_code}" $API_URL 2>/dev/null)
HTTP_CODE=$(echo "$RESPONSE" | tail -n1)
BODY=$(echo "$RESPONSE" | head -n-1)

if [ "$HTTP_CODE" = "200" ]; then
    echo "  ✅ API 响应成功 (HTTP 200)"
    echo "  📦 返回数据预览："
    echo "$BODY" | head -c 500
    echo ""
else
    echo "  ❌ API 返回异常 (HTTP $HTTP_CODE)"
    echo "  响应内容："
    echo "$BODY" | head -c 200
fi

# 第 4 步：检查 WebSocket 端口
echo ""
echo "✅ 第 4 步：检查 WebSocket 端口..."
if nc -z -w2 $REMOTE_SERVER $WS_PORT 2>/dev/null; then
    echo "  ✅ WebSocket 端口 $WS_PORT 开放"
else
    echo "  ℹ️  WebSocket 端口 $WS_PORT 未开放（可能还未启动 Worker，这是正常的）"
fi

# 第 5 步：检查防火墙
echo ""
echo "✅ 第 5 步：检查防火墙..."
if command -v firewall-cmd &> /dev/null; then
    echo "  检测到 firewalld..."
    firewall-cmd --list-ports | grep -q "$API_PORT/tcp" && \
        echo "  ✅ 端口 $API_PORT 已开放" || \
        echo "  ❌ 端口 $API_PORT 未开放（需要运行: sudo firewall-cmd --add-port=$API_PORT/tcp --permanent）"
elif command -v ufw &> /dev/null; then
    echo "  检测到 ufw..."
    ufw status | grep -q "$API_PORT" && \
        echo "  ✅ 端口 $API_PORT 已开放" || \
        echo "  ❌ 端口 $API_PORT 未开放"
else
    echo "  ℹ️  未检测到防火墙管理工具"
fi

echo ""
echo "=========================================="
echo "诊断完成"
echo "=========================================="
