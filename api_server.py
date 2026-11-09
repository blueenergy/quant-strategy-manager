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
from fastapi.concurrency import run_in_threadpool
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
from strategy_manager.core.position_guard import (
    DEFAULT_STATE_DIR,
    build_reset_state,
    market_session,
    read_state,
    resolve_account,
    resolve_managed_position,
    strategy_capabilities,
    summarize_pending_signals,
    write_state,
)
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


def _safe_int(value: Any, default: int = 0) -> int:
    try:
        return int(value or 0)
    except (TypeError, ValueError):
        return default


def _safe_float(value: Any, default: float = 0.0) -> float:
    try:
        return float(value or 0)
    except (TypeError, ValueError):
        return default


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
    
    # 只返回属于当前用户的 workers（snapshot 避免与 sync/reload 并发迭代）
    for key, worker in orch.snapshot_workers().items():
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


@app.get("/api/configs/position-guard")
async def get_position_guard_config(
    symbol: str,
    strategy_key: str,
    current_user: dict = Depends(get_current_active_user),
) -> Dict[str, Any]:
    """Return the position a strategy manages, without starting a worker.

    Read-only. Used by the disable flow so a strategy is not stopped while it
    still holds shares nobody else will manage.
    """
    orch = get_orchestrator()
    db = orch.db
    user_id = get_user_id(current_user)
    config = orch.config_coll.find_one(
        {"user_id": user_id, "symbol": symbol, "strategy_key": strategy_key}
    )
    if not config:
        raise HTTPException(status_code=404, detail="strategy config not found")

    params = config.get("params") or {}
    capabilities = strategy_capabilities(strategy_key)
    account = resolve_account(db, user_id, config)
    account_payload = {
        "bound": account is not None,
        "securities_account_id": str(account.get("_id")) if account else None,
        "account_id": account.get("account_id") if account else None,
        "broker": account.get("broker") if account else None,
    }

    position_doc = None
    if account:
        position_doc = db["trader_positions"].find_one(
            {"symbol": symbol, "securities_account_id": str(account["_id"])},
            sort=[("updated_at", -1)],
        )
    broker_qty = _safe_int(
        (position_doc or {}).get("qty") or (position_doc or {}).get("volume") or 0
    )
    if position_doc and "can_use_volume" in position_doc:
        can_use = _safe_int(position_doc.get("can_use_volume"))
    else:
        can_use = broker_qty

    state_prefix = params.get("state_prefix") or "single_stream"
    state_dir = params.get("state_dir") or DEFAULT_STATE_DIR
    state_data = read_state(state_dir, symbol, state_prefix)
    state_pos: Optional[int] = None
    if state_data is not None and state_data.get("pos") is not None:
        state_pos = _safe_int(state_data.get("pos"))

    resolution = resolve_managed_position(
        capabilities=capabilities,
        broker_qty=broker_qty,
        managed_shares=_safe_int(params.get("managed_shares")),
        core_shares=_safe_int(params.get("core_shares")),
        state_pos=state_pos,
    )
    managed_qty = resolution.get("managed_qty")
    pending = summarize_pending_signals(
        db, user_id, account_payload["securities_account_id"], symbol
    )

    pending_sell_qty = _safe_int((pending.get("sell") or {}).get("qty"))
    clear_qty: Optional[int] = None
    if managed_qty is not None:
        clear_qty = max(0, min(max(0, managed_qty - pending_sell_qty), max(0, can_use)))
    can_auto_clear = bool(
        managed_qty is not None
        and clear_qty is not None
        and clear_qty > 0
        and resolution.get("source") != "unknown"
    )

    source = str(resolution.get("source") or "unknown")
    warnings: list[str] = []
    if not account:
        warnings.append("该策略未绑定证券账户，只产生观察信号，不会下单")
    if source == "unknown":
        warnings.append("无法自动确认该策略的独立持仓，请人工核对后再决定")
    if source == "state_file":
        warnings.append(f"持仓量来自 state 文件（{managed_qty} 股）；该策略不接管券商持仓")
    if source == "state_file_missing":
        if broker_qty > 0:
            warnings.append(f"state 文件无持仓记录；券商 {broker_qty} 股不被该策略管理")
        else:
            warnings.append("state 文件无持仓记录")
    if source == "broker_sleeve" and _safe_int(resolution.get("core_qty")) > 0:
        warnings.append(
            f"core_shares={_safe_int(params.get('core_shares'))} 为底仓，"
            f"清仓只会卖出策略管理的 {managed_qty} 股"
        )
    if source == "broker_position" and broker_qty > 0 and managed_qty == broker_qty:
        warnings.append(f"managed_shares=0：停止后账户全部 {broker_qty} 股将无人管理")
    if source == "broker_sync_position" and managed_qty:
        warnings.append("该策略按券商持仓同步；停止后这些持仓将无人管理")
    if managed_qty is not None and managed_qty > broker_qty:
        warnings.append(
            f"state 显示 {managed_qty} 股，但券商快照只有 {broker_qty} 股；可能已人工卖出"
        )
    if source == "state_file" and managed_qty is not None and broker_qty > managed_qty:
        warnings.append(
            f"券商持仓 {broker_qty} 股，其中 {broker_qty - managed_qty} 股不在该策略管理范围内"
        )
    if _safe_int((pending.get("buy") or {}).get("count")):
        warnings.append(
            f"有 {_safe_int((pending.get('buy') or {}).get('count'))} 笔在途买单"
            f"（{_safe_int((pending.get('buy') or {}).get('qty'))} 股），停止后仍可能成交"
        )
    if pending_sell_qty:
        warnings.append(f"已有 {pending_sell_qty} 股在途卖单，清仓只会补足差额")
    if managed_qty is not None and can_use < managed_qty:
        warnings.append(
            f"今日可卖 {can_use} 股，剩余 {managed_qty - can_use} 股受 T+1 限制"
        )

    return {
        "ok": True,
        "symbol": symbol,
        "strategy_key": strategy_key,
        "strategy_name": capabilities.get("name") or strategy_key,
        "enabled": bool(config.get("enabled", True)),
        "account": account_payload,
        "position": {
            "source": source,
            "broker_qty": broker_qty,
            "can_use_volume": can_use,
            "managed_qty": managed_qty,
            "core_qty": resolution.get("core_qty"),
            "avg_price": _safe_float((position_doc or {}).get("avg_price")),
            "last_price": _safe_float((position_doc or {}).get("last_price")),
            "market_value": _safe_float((position_doc or {}).get("market_value")),
            "unrealized_pnl": _safe_float((position_doc or {}).get("unrealized_pnl")),
            "unrealized_pnl_pct": _safe_float((position_doc or {}).get("unrealized_pnl_pct")),
            "entry_price": _safe_float((state_data or {}).get("entry_price")),
            "entry_date": (state_data or {}).get("entry_date"),
            "snapshot_at": (position_doc or {}).get("updated_at"),
        },
        "pending": pending,
        "session": market_session(),
        "can_auto_clear": can_auto_clear,
        "clear_qty": clear_qty,
        "warnings": warnings,
    }


@app.post("/api/configs/reset-position")
async def reset_position_state(
    symbol: str,
    strategy_key: str,
    current_user: dict = Depends(get_current_active_user),
) -> Dict[str, Any]:
    """Zero a stopped strategy's state file after its position was cleared.

    The worker, if still alive, is stopped first so its final ``save_state``
    cannot overwrite the reset. The config must already be disabled.
    """
    orch = get_orchestrator()
    user_id = get_user_id(current_user)
    config = orch.config_coll.find_one(
        {"user_id": user_id, "symbol": symbol, "strategy_key": strategy_key}
    )
    if not config:
        raise HTTPException(status_code=404, detail="strategy config not found")
    if bool(config.get("enabled", True)):
        raise HTTPException(
            status_code=409,
            detail="stop the strategy before resetting its state",
        )

    params = config.get("params") or {}
    account_key = (
        config.get("securities_account_id")
        or params.get("securities_account_id")
        or "no_account"
    )
    worker_key = f"{user_id}_{account_key}_{symbol}_{strategy_key}"
    # stop_worker_now joins the worker thread (up to 5s); keep it off the event
    # loop so concurrent guard/worker reads stay responsive.
    stopped = await run_in_threadpool(orch.stop_worker_now, worker_key)

    state_dir = params.get("state_dir") or DEFAULT_STATE_DIR
    state_prefix = params.get("state_prefix") or "single_stream"
    state = read_state(state_dir, symbol, state_prefix)
    if state is None:
        return {
            "ok": True,
            "reset": False,
            "reason": "no_state_file",
            "worker_stopped": stopped,
        }

    pos_before = _safe_int(state.get("pos"))
    path = write_state(state_dir, symbol, state_prefix, build_reset_state(state))
    return {
        "ok": True,
        "reset": True,
        "pos_before": pos_before,
        "pos_after": 0,
        "worker_stopped": stopped,
        "state_path": str(path),
    }


@app.post("/api/reload")
async def reload_configs(
    current_user: dict = Depends(get_current_active_user),
) -> Dict[str, Any]:
    """Re-read ``watchlist_strategies`` and start/stop workers immediately.

    Idempotent; any authenticated user can trigger a sync. The 60-second
    monitor thread remains the fallback if this call is missed.
    """
    orch = get_orchestrator()
    result = await run_in_threadpool(orch.reload_now)
    return {"ok": True, **(result or {})}


@app.get("/api/status")
async def get_status() -> Dict[str, Any]:
    """获取 orchestrator 整体状态"""
    orch = get_orchestrator()
    workers = orch.snapshot_workers()
    return {
        "total_workers": len(workers),
        "active_configs": len(orch.configurations),
        "worker_keys": list(workers.keys())
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