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

from fastapi import FastAPI, HTTPException
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

from strategy_manager.core import MultiStrategyOrchestrator
from strategy_manager.adapters.vnpy_adapter import create_vnpy_worker

# 配置日志
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s: %(message)s"
)
logger = logging.getLogger(__name__)

app = FastAPI(
    title="Strategy Manager API",
    description="Worker 管理和实时日志流 API",
    version="1.0.0"
)

# 全局 orchestrator 实例
orchestrator = None


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
            auto_reload_interval=int(os.getenv("AUTO_RELOAD_INTERVAL", "60")),
        )
        
        # 加载配置并启动 workers
        logger.info("Loading strategy configurations from database...")
        config_count = orchestrator.load_configurations()
        logger.info(f"✓ Loaded {config_count} strategy configurations")
        
        # 显示配置详情
        if config_count > 0:
            logger.info("Configuration details:")
            for key, config in orchestrator.configurations.items():
                logger.info(f"  - {key}: {config.symbol} | {config.strategy_key} | engine={config.engine}")
        else:
            logger.warning("⚠️  No enabled configurations found in database!")
        
        # 同步 workers
        logger.info("Syncing workers...")
        orchestrator.sync_workers()
        logger.info(f"✓ {len(orchestrator.workers)} workers active")
        
        # 显示 worker 详情
        if orchestrator.workers:
            logger.info("Active workers:")
            for worker_key, worker in orchestrator.workers.items():
                status = "alive" if worker.is_alive() else "stopped"
                logger.info(f"  - {worker_key}: {status}")
        else:
            logger.warning("⚠️  No workers started!")
    
    return orchestrator


@app.get("/api/workers")
async def list_workers() -> Dict[str, Any]:
    """获取所有 Workers 及其日志流地址"""
    orch = get_orchestrator()
    workers_info = {}
    
    public_host = get_public_host()  # ← 获取公网 IP
    
    for key, worker in orch.workers.items():
        worker_data = {
            "alive": worker.is_alive(),
            "stats": worker.get_stats() if hasattr(worker, 'get_stats') else {}
        }
        
        # 添加 log stream URL
        if hasattr(worker, 'get_log_stream_url'):
            log_url = worker.get_log_stream_url()
            if log_url:
                # 🔧 替换 0.0.0.0/localhost 为公网 IP
                import re
                log_url = re.sub(
                    r'ws://(0\.0\.0\.0|localhost|127\.0\.0\.1)',
                    f'ws://{public_host}',
                    log_url
                )
                worker_data["log_stream_url"] = log_url
        
        workers_info[key] = worker_data
    
    return {"workers": workers_info}


@app.get("/api/workers/{worker_key}")
async def get_worker(worker_key: str) -> Dict[str, Any]:
    """获取单个 Worker 的详细信息"""
    orch = get_orchestrator()
    worker = orch.workers.get(worker_key)
    
    if not worker:
        raise HTTPException(status_code=404, detail="Worker not found")
    
    worker_info = {
        "alive": worker.is_alive(),
        "stats": worker.get_stats() if hasattr(worker, 'get_stats') else {}
    }
    
    # 添加 log stream URL
    if hasattr(worker, 'get_log_stream_url'):
        log_url = worker.get_log_stream_url()
        if log_url:
            # 🔧 替换主机名
            public_host = get_public_host()
            import re
            log_url = re.sub(
                r'ws://(0\.0\.0\.0|localhost|127\.0\.0\.1)',
                f'ws://{public_host}',
                log_url
            )
            worker_info["log_stream_url"] = log_url
    
    return worker_info


@app.get("/api/workers/{worker_key}/console")
async def get_worker_console_url(worker_key: str) -> Dict[str, Any]:
    """获取 Worker 的控制台 WebSocket URL"""
    orch = get_orchestrator()
    worker = orch.workers.get(worker_key)
    
    if not worker:
        raise HTTPException(status_code=404, detail="Worker not found")
    
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
async def get_worker_log_file(worker_key: str, tail: Optional[int] = None):
    """获取 Worker 的历史日志文件
    
    Args:
        worker_key: Worker 键值
        tail: 如果提供，只返回最后 N 行日志（默认返回全部）
    """
    orch = get_orchestrator()
    worker = orch.workers.get(worker_key)
    
    if not worker:
        raise HTTPException(
            status_code=404,
            detail=f"❌ Worker '{worker_key}' 不存在"
        )
    
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


@app.get("/", response_class=HTMLResponse)
async def index():
    """API 文档"""
    return """
    <html>
    <head><title>Strategy Manager API</title></head>
    <body>
        <h1>Strategy Manager API Server</h1>
        <p>查看自动生成的 API 文档：<a href="/docs">/docs</a></p>
        <h2>Endpoints:</h2>
        <ul>
            <li><code>GET /api/workers</code> - 获取所有 Workers</li>
            <li><code>GET /api/workers/{worker_key}</code> - 获取单个 Worker</li>
            <li><code>GET /api/workers/{worker_key}/console</code> - 获取控制台 URL</li>
            <li><code>GET /api/workers/{worker_key}/logs</code> - 获取历史日志文件</li>
            <li><code>GET /api/workers/{worker_key}/logs?tail=100</code> - 获取最后 N 行日志</li>
            <li><code>GET /api/status</code> - 获取整体状态</li>
            <li><code>GET /health</code> - 健康检查</li>
        </ul>
    </body>
    </html>
    """


def cleanup_orchestrator():
    """清理 orchestrator 资源"""
    global orchestrator
    if orchestrator:
        logger.info("🛑 Shutting down orchestrator...")
        try:
            orchestrator.stop_all()  # ✅ 正确的方法名
            logger.info("✓ Orchestrator stopped gracefully")
        except Exception as e:
            logger.error(f"Error during orchestrator shutdown: {e}")
        orchestrator = None


def signal_handler(signum, frame):
    """信号处理器 - 优雅关闭"""
    sig_name = signal.Signals(signum).name
    logger.info(f"\n🛑 Received signal {sig_name} ({signum}), shutting down...")
    cleanup_orchestrator()
    sys.exit(0)


# 注册信号处理器
signal.signal(signal.SIGINT, signal_handler)   # Ctrl+C
signal.signal(signal.SIGTERM, signal_handler)  # kill
atexit.register(cleanup_orchestrator)          # 进程退出时


if __name__ == '__main__':
    import uvicorn
    
    port = int(os.getenv('API_PORT', '5000'))
    
    print("=" * 80)
    print("Strategy Manager API Server (FastAPI)")
    print("=" * 80)
    print(f"\nMongoDB: {os.getenv('MONGO_URI', 'mongodb://localhost:27017')}")
    print(f"Database: {os.getenv('MONGO_DB', 'finance')}")
    print(f"\nAPI Server: http://0.0.0.0:{port}")
    print(f"API Docs: http://0.0.0.0:{port}/docs")
    print("\nEndpoints:")
    print("  • GET  /api/workers")
    print("  • GET  /api/workers/{worker_key}")
    print("  • GET  /api/workers/{worker_key}/console")
    print("  • GET  /api/workers/{worker_key}/logs")
    print("  • GET  /api/workers/{worker_key}/logs?tail=100")
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