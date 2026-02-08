#!/usr/bin/env python3
"""
Strategy Manager API Server (FastAPI)

生产环境 REST API 服务器，暴露 Worker 信息和实时日志流地址。

使用方法:
    cd /home/shuyolin/trading/quant-strategy-manager
    uvicorn api_server:app --host 0.0.0.0 --port 5000
"""

from dotenv import load_dotenv

# 加载 .env 文件中的环境变量（优先级：.env > config/.env > 环境变量）
load_dotenv()  # 默认加载当前目录的 .env
load_dotenv('config/.env')  # 也加载 config 目录下的 .env

from fastapi import FastAPI, HTTPException, Depends
from fastapi.responses import HTMLResponse, FileResponse, PlainTextResponse
from typing import Dict, Any, Optional
import sys
import os
import logging
import signal
import atexit
from pathlib import Path
import socket

# 添加项目路径
project_root = Path(__file__).parent / "src"
sys.path.insert(0, str(project_root))

# 添加 vnpy-live-trading 路径
vnpy_path = Path(__file__).parent.parent / "vnpy-live-trading"
if vnpy_path.exists():
    sys.path.insert(0, str(vnpy_path))

# 配置日志（在导入其他模块之前）
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s: %(message)s"
)
logger = logging.getLogger(__name__)

# 导入认证模块（使用本地轻量级实现，不依赖 quantFinance）
try:
    from simple_auth import get_current_active_user
    AUTH_AVAILABLE = True
    logger.info("✅ Authentication enabled (JWT)")
except ImportError as e:
    logger.warning(f"⚠️  Auth module not available: {e}")
    logger.warning("   API will run without authentication (all users see all workers)")
    AUTH_AVAILABLE = False
    # 提供一个空的依赖函数
    async def get_current_active_user():
        return {"id": "anonymous", "username": "anonymous"}

from strategy_manager.core import MultiStrategyOrchestrator
from strategy_manager.adapters.vnpy_adapter import create_vnpy_worker

app = FastAPI(
    title="Strategy Manager API",
    description="Worker 管理和实时日志流 API",
    version="1.0.0"
)

# 全局 orchestrator 实例
orchestrator = None


def get_user_id(current_user: dict) -> str:
    """统一获取用户唯一标识（主键 _id），并转换为字符串"""
    return str(current_user["id"])


def get_public_host():
    """获取公网可访问的主机地址"""
    # 1. 优先使用环境变量
    public_host = os.getenv('PUBLIC_HOST')
    if public_host:
        return public_host
    
    # 2. 自动获取本机 IP
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(('8.8.8.8', 80))
        ip = s.getsockname()[0]
        s.close()
        return ip
    except:
        return '127.0.0.1'


@app.on_event("startup")
async def startup_event():
    """FastAPI 启动时初始化 orchestrator"""
    logger.info("🚀 FastAPI startup - initializing orchestrator...")
    logger.info(f"🔐 Authentication status: {'ENABLED' if AUTH_AVAILABLE else 'DISABLED (mock mode)'}")
    if not AUTH_AVAILABLE:
        logger.warning("⚠️  Running without authentication - all users will be treated as 'anonymous'")
        logger.warning("⚠️  User filtering will NOT work properly!")
    get_orchestrator()  # 触发初始化
    logger.info("✓ Startup complete")


def get_orchestrator():
    """获取或初始化 orchestrator"""
    global orchestrator
    if orchestrator is None:
        logger.info("Initializing MultiStrategyOrchestrator...")
        
        # 构建 worker_factories
        worker_factories = {
            "vnpy": create_vnpy_worker,
        }
        
        # 尝试添加 backtrader（可选）
        try:
            from strategy_manager.adapters.backtrader_adapter import create_backtrader_worker
            worker_factories["backtrader"] = create_backtrader_worker
            logger.info("Backtrader adapter available")
        except ImportError:
            logger.info("Backtrader adapter not available")
        
        # 初始化 orchestrator
        orchestrator = MultiStrategyOrchestrator(
            worker_factories=worker_factories,
            mongo_uri=os.getenv("MONGO_URI", "mongodb://localhost:27017"),
            mongo_db=os.getenv("MONGO_DB", "finance"),
            config_collection="watchlist_strategies",
            auto_reload_interval=int(os.getenv("AUTO_RELOAD_INTERVAL", "30")),
        )
        
        # 启动所有 workers 并开启监控
        logger.info("Starting all workers and monitoring...")
        orchestrator.start_all()
        logger.info(f"✓ {len(orchestrator.workers)} workers active, monitoring enabled")
        
        # 显示 worker 详情
        if orchestrator.workers:
            logger.info("Active workers:")
            for worker_key, worker in orchestrator.workers.items():
                status = "alive" if worker.is_alive() else "stopped"
                logger.info(f"  - {worker_key}: {status}")
        else:
            logger.warning("⚠️  No workers started!")

    
    return orchestrator


def get_public_websocket_url(worker_ws_url):
    """将 Worker 的直接 WebSocket URL 转换为通过 Nginx 的 URL"""
    import re
    
    # 提取端口号
    match = re.search(r':(\d+)', worker_ws_url)
    if not match:
        return worker_ws_url
    
    port = match.group(1)
    public_host = os.getenv('PUBLIC_HOST', '115.190.254.11')
    
    # 生产环境使用 Nginx 代理路径
    use_nginx = os.getenv('USE_NGINX_WEBSOCKET', 'false').lower() == 'true'
    
    # 检查是否使用 HTTPS（决定使用 ws:// 还是 wss://）
    use_https = os.getenv('USE_HTTPS', 'false').lower() == 'true'
    ws_protocol = 'wss' if use_https else 'ws'
    
    if use_nginx:
        # 通过 Nginx /ws/{port} 路径
        return f"{ws_protocol}://{public_host}/ws/{port}"
    else:
        # 直接 WebSocket（开发环境）
        return worker_ws_url.replace('0.0.0.0', public_host).replace('localhost', public_host)


@app.get("/api/workers")
async def list_workers(current_user: dict = Depends(get_current_active_user)) -> Dict[str, Any]:
    """获取当前用户的 Workers（根据 user_id 过滤）"""
    orch = get_orchestrator()
    workers_info = {}
    
    user_id = get_user_id(current_user)
    public_host = get_public_host()
    
    logger.info(f"User {current_user.get('username')} ({user_id}) requesting workers")
    
    # 只返回属于当前用户的 workers
    for key, worker in orch.workers.items():
        config = orch.configurations.get(key)
        
        if config:
            config_user_id = str(config.user_id) if hasattr(config, 'user_id') else None
            
            # 严格匹配：只返回属于当前用户的 workers
            if config_user_id and config_user_id == user_id:
                worker_data = {
                    "alive": worker.is_alive(),
                    "stats": worker.get_stats() if hasattr(worker, 'get_stats') else {}
                }
                
                # 添加 log stream URL
                if hasattr(worker, 'get_log_stream_url'):
                    log_url = worker.get_log_stream_url()
                    if log_url:
                        worker_data["log_stream_url"] = get_public_websocket_url(log_url)
                
                workers_info[key] = worker_data
    
    logger.info(f"Returning {len(workers_info)} workers for user {current_user.get('username')}")
    return {"workers": workers_info}


@app.get("/api/workers/{worker_key}")
async def get_worker(worker_key: str, current_user: dict = Depends(get_current_active_user)) -> Dict[str, Any]:
    """获取单个 Worker 的详细信息（需要验证所有权）"""
    orch = get_orchestrator()
    worker = orch.workers.get(worker_key)
    
    if not worker:
        raise HTTPException(status_code=404, detail="Worker not found")
    
    # 验证 worker 是否属于当前用户
    user_id = get_user_id(current_user)
    config = orch.configurations.get(worker_key)
    if not config or not hasattr(config, 'user_id') or str(config.user_id) != user_id:
        raise HTTPException(status_code=403, detail="Access denied: This worker does not belong to you")
    
    worker_info = {
        "alive": worker.is_alive(),
        "stats": worker.get_stats() if hasattr(worker, 'get_stats') else {}
    }
    
    # 添加 log stream URL
    if hasattr(worker, 'get_log_stream_url'):
        log_url = worker.get_log_stream_url()
        if log_url:
            worker_info["log_stream_url"] = get_public_websocket_url(log_url)
    
    return worker_info


@app.get("/api/workers/{worker_key}/console")
async def get_worker_console_url(worker_key: str, current_user: dict = Depends(get_current_active_user)) -> Dict[str, Any]:
    """获取 Worker 的控制台 WebSocket URL（需要验证所有权）"""
    orch = get_orchestrator()
    worker = orch.workers.get(worker_key)
    
    if not worker:
        raise HTTPException(status_code=404, detail="Worker not found")
    
    # 验证 worker 是否属于当前用户
    user_id = get_user_id(current_user)
    config = orch.configurations.get(worker_key)
    if not config or not hasattr(config, 'user_id') or str(config.user_id) != user_id:
        raise HTTPException(status_code=403, detail="Access denied: This worker does not belong to you")
    
    ws_url = None
    if hasattr(worker, 'get_log_stream_url'):
        ws_url = worker.get_log_stream_url()
    
    if not ws_url:
        raise HTTPException(status_code=404, detail="Log streaming not enabled")
    
    return {
        "worker_key": worker_key,
        "log_stream_url": ws_url
    }


@app.get("/api/workers/{worker_key}/logs")
@app.head("/api/workers/{worker_key}/logs")
async def get_worker_log_file(worker_key: str, current_user: dict = Depends(get_current_active_user), tail: Optional[int] = None):
    """获取 Worker 的历史日志文件（需要验证所有权）
    
    Args:
        worker_key: Worker 键值
        current_user: 当前认证用户
        tail: 如果提供，只返回最后 N 行日志（默认返回全部）
    """
    orch = get_orchestrator()
    worker = orch.workers.get(worker_key)
    
    if not worker:
        raise HTTPException(
            status_code=404,
            detail=f"❌ Worker '{worker_key}' 不存在"
        )
    
    # 验证 worker 是否属于当前用户
    user_id = get_user_id(current_user)
    config = orch.configurations.get(worker_key)
    if not config or not hasattr(config, 'user_id') or str(config.user_id) != user_id:
        raise HTTPException(status_code=403, detail="Access denied: This worker does not belong to you")
    
    # 获取日志文件路径
    log_file = None
    if hasattr(worker, 'log_file'):
        log_file = worker.log_file
    
    if not log_file:
        raise HTTPException(
            status_code=404,
            detail="📝 此 Worker 未配置文件日志。请查看实时日志（WebSocket）"
        )
    
    if not Path(log_file).exists():
        raise HTTPException(
            status_code=404,
            detail=f"📂 历史日志文件尚未生成\n\n" 
                   f"可能原因：\n"
                   f"• Worker 刚启动，还没有写入日志\n"
                   f"• 日志目录权限问题\n"
                   f"• 日志文件路径：{log_file}\n\n"
                   f"💡 建议：请先查看实时日志（WebSocket），或等待几秒后重试"
        )
    
    # 如果指定了 tail，返回最后 N 行
    if tail:
        try:
            with open(log_file, 'r', encoding='utf-8') as f:
                lines = f.readlines()
                content = ''.join(lines[-tail:])
            return PlainTextResponse(content)
        except Exception as e:
            raise HTTPException(status_code=500, detail=f"Error reading log: {str(e)}")
    
    # 否则返回整个文件
    return FileResponse(
        log_file,
        media_type="text/plain",
        filename=f"{worker_key}.log"
    )


@app.get("/api/status")
async def get_status() -> Dict[str, Any]:
    """获取 orchestrator 整体状态"""
    orch = get_orchestrator()
    return {
        "total_workers": len(orch.workers),
        "active_configs": len(orch.configurations),
        "worker_keys": list(orch.workers.keys())
    }


@app.get("/health")
async def health_check() -> Dict[str, str]:
    """健康检查"""
    return {"status": "ok"}


@app.get("/api/debug/auth")
async def debug_auth(current_user: dict = Depends(get_current_active_user)) -> Dict[str, Any]:
    """调试认证状态（仅用于开发）"""
    return {
        "auth_available": AUTH_AVAILABLE,
        "current_user": current_user,
        "user_id": get_user_id(current_user)
    }


@app.get("/", response_class=HTMLResponse)
async def index():
    """API 文档"""
    auth_note = "" if AUTH_AVAILABLE else "<p style='color: orange;'>⚠️ Authentication is disabled - running in open mode</p>"
    return f"""
    <html>
    <head><title>Strategy Manager API</title></head>
    <body>
        <h1>Strategy Manager API Server</h1>
        {auth_note}
        <p>查看自动生成的 API 文档：<a href="/docs">/docs</a></p>
        <h2>Endpoints:</h2>
        <ul>
            <li><code>GET /api/workers</code> - 获取当前用户的 Workers（需要JWT认证）</li>
            <li><code>GET /api/workers/{{worker_key}}</code> - 获取单个 Worker（需要JWT认证和所有权验证）</li>
            <li><code>GET /api/workers/{{worker_key}}/console</code> - 获取控制台 URL（需要JWT认证和所有权验证）</li>
            <li><code>GET /api/workers/{{worker_key}}/logs</code> - 获取历史日志文件（需要JWT认证和所有权验证）</li>
            <li><code>GET /api/workers/{{worker_key}}/logs?tail=100</code> - 获取最后 N 行日志（需要JWT认证和所有权验证）</li>
            <li><code>GET /api/status</code> - 获取整体状态</li>
            <li><code>GET /health</code> - 健康检查</li>
        </ul>
        <h2>Authentication:</h2>
        <p>所有 worker 相关接口都需要 JWT Bearer Token 认证。</p>
        <pre>Authorization: Bearer YOUR_JWT_TOKEN</pre>
        <p>用户只能访问自己的 workers，无法查看或操作其他用户的 workers。</p>
    </body>
    </html>
    """


@app.on_event("shutdown")
async def shutdown_event():
    """FastAPI 关闭时清理 orchestrator"""
    logger.info("🛑 FastAPI shutdown event triggered")
    cleanup_orchestrator()
    logger.info("✓ Shutdown complete")


def cleanup_orchestrator():
    """清理 orchestrator 资源"""
    global orchestrator
    if orchestrator:
        logger.info("🛑 Shutting down orchestrator...")
        try:
            orchestrator.stop_all()
            logger.info("✓ Orchestrator stopped gracefully")
        except KeyboardInterrupt:
            # 忽略清理过程中的 KeyboardInterrupt
            logger.info("⚠️  Cleanup interrupted, forcing shutdown...")
        except Exception as e:
            logger.error(f"Error during orchestrator shutdown: {e}", exc_info=True)
        finally:
            orchestrator = None


if __name__ == '__main__':
    import uvicorn
    
    port = int(os.getenv('API_PORT', '5001'))
    
    print("=" * 80)
    print("Strategy Manager API Server (FastAPI)")
    print("=" * 80)
    print(f"\nMongoDB: {os.getenv('MONGO_URI', 'mongodb://localhost:27017')}")
    print(f"Database: {os.getenv('MONGO_DB', 'finance')}")
    print(f"\nAuthentication: {'✅ Enabled (JWT)' if AUTH_AVAILABLE else '⚠️  Disabled (Open Mode)'}")
    if AUTH_AVAILABLE:
        print("  All worker endpoints require JWT Bearer token authentication")
        print("  Users can only access their own workers")
    print(f"\nAPI Server: http://0.0.0.0:{port}")
    print(f"API Docs: http://0.0.0.0:{port}/docs")
    print("\nEndpoints:")
    print("  • GET  /api/workers                         (JWT required)")
    print("  • GET  /api/workers/{worker_key}            (JWT required)")
    print("  • GET  /api/workers/{worker_key}/console    (JWT required)")
    print("  • GET  /api/workers/{worker_key}/logs       (JWT required)")
    print("  • GET  /api/workers/{worker_key}/logs?tail=100 (JWT required)")
    print("  • GET  /api/status")
    print("  • GET  /health")
    print("\n" + "=" * 80 + "\n")
    
    try:
        uvicorn.run(app, host="0.0.0.0", port=port)
    except KeyboardInterrupt:
        logger.info("\n🛑 KeyboardInterrupt received, shutting down...")
        cleanup_orchestrator()
    finally:
        logger.info("👋 API Server stopped")