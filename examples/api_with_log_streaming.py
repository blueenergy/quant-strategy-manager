"""
REST API 示例 - 展示如何暴露 Worker 的 WebSocket URL

此示例展示如何通过 REST API 让前端获取 Worker 的日志流地址。

使用方法:
    python examples/api_with_log_streaming.py
    
然后访问:
    GET http://localhost:5000/api/workers
    GET http://localhost:5000/api/workers/user123_002050.SZ_hidden_dragon
"""

from flask import Flask, jsonify
from typing import Dict, Any
import sys
from pathlib import Path

# Add project root to path
project_root = Path(__file__).parent.parent / "src"
sys.path.insert(0, str(project_root))

app = Flask(__name__)

# 模拟 orchestrator（实际使用中应该是全局单例）
# from strategy_manager.core import MultiStrategyOrchestrator
# orchestrator = MultiStrategyOrchestrator(...)


@app.route('/api/workers', methods=['GET'])
def list_workers():
    """获取所有 Workers 及其日志流地址
    
    Returns:
        {
            "total_workers": 3,
            "workers": {
                "user123_002050.SZ_hidden_dragon": {
                    "symbol": "002050.SZ",
                    "strategy": "hidden_dragon",
                    "state": "running",
                    "log_stream_url": "ws://localhost:54321",
                    "stats": {...}
                },
                ...
            }
        }
    """
    # 实际代码：
    # status = orchestrator.get_status()
    # return jsonify(status)
    
    # 示例数据
    return jsonify({
        "total_workers": 3,
        "active_configs": 3,
        "workers": {
            "user123_002050.SZ_hidden_dragon": {
                "alive": True,
                "stats": {
                    "symbol": "002050.SZ",
                    "strategy": "hidden_dragon",
                    "engine": "vnpy",
                    "state": "running",
                    "position": 500,
                    "bars_processed": 1234
                },
                "log_stream_url": "ws://localhost:54321"
            },
            "user123_600132.SH_turtle": {
                "alive": True,
                "stats": {
                    "symbol": "600132.SH",
                    "strategy": "turtle",
                    "engine": "vnpy",
                    "state": "running",
                    "position": 0,
                    "bars_processed": 5678
                },
                "log_stream_url": "ws://localhost:54322"
            },
            "user123_000002.SZ_single_yang": {
                "alive": True,
                "stats": {
                    "symbol": "000002.SZ",
                    "strategy": "single_yang",
                    "engine": "vnpy",
                    "state": "running",
                    "position": 1000,
                    "bars_processed": 9012
                },
                "log_stream_url": "ws://localhost:54323"
            }
        }
    })


@app.route('/api/workers/<worker_key>', methods=['GET'])
def get_worker(worker_key: str):
    """获取单个 Worker 的详细信息
    
    Args:
        worker_key: Worker 标识 (e.g., "user123_002050.SZ_hidden_dragon")
    
    Returns:
        {
            "symbol": "002050.SZ",
            "strategy": "hidden_dragon",
            "state": "running",
            "log_stream_url": "ws://localhost:54321",
            "stats": {...}
        }
    """
    # 实际代码：
    # worker = orchestrator.workers.get(worker_key)
    # if not worker:
    #     return jsonify({"error": "Worker not found"}), 404
    # 
    # return jsonify({
    #     "symbol": worker.symbol,
    #     "strategy": worker.strategy_key,
    #     "state": worker.state.value,
    #     "log_stream_url": worker.get_log_stream_url(),
    #     "stats": worker.get_stats()
    # })
    
    # 示例数据
    if worker_key == "user123_002050.SZ_hidden_dragon":
        return jsonify({
            "symbol": "002050.SZ",
            "strategy": "hidden_dragon",
            "state": "running",
            "log_stream_url": "ws://localhost:54321",
            "stats": {
                "position": 500,
                "bars_processed": 1234,
                "entry_price": 48.50,
                "boom_day": 5,
                "callback_days": 2
            }
        })
    else:
        return jsonify({"error": "Worker not found"}), 404


@app.route('/api/workers/<worker_key>/console', methods=['GET'])
def get_worker_console_url(worker_key: str):
    """快速获取 Worker 的控制台 URL（重定向用）
    
    前端可以用这个接口直接获取 WebSocket URL 并连接
    
    Returns:
        {
            "worker_key": "user123_002050.SZ_hidden_dragon",
            "log_stream_url": "ws://localhost:54321"
        }
    """
    # 实际代码：
    # worker = orchestrator.workers.get(worker_key)
    # if not worker:
    #     return jsonify({"error": "Worker not found"}), 404
    # 
    # ws_url = worker.get_log_stream_url()
    # if not ws_url:
    #     return jsonify({"error": "Log streaming not enabled"}), 404
    # 
    # return jsonify({
    #     "worker_key": worker_key,
    #     "log_stream_url": ws_url
    # })
    
    # 示例数据
    if worker_key == "user123_002050.SZ_hidden_dragon":
        return jsonify({
            "worker_key": worker_key,
            "log_stream_url": "ws://localhost:54321"
        })
    else:
        return jsonify({"error": "Worker not found"}), 404


@app.route('/')
def index():
    """API 文档首页"""
    return """
    <h1>Strategy Manager API - with Log Streaming</h1>
    <p>类似 Jenkins 的实时日志流功能</p>
    
    <h2>Endpoints:</h2>
    <ul>
        <li><code>GET /api/workers</code> - 获取所有 Workers（包含 WebSocket URLs）</li>
        <li><code>GET /api/workers/{worker_key}</code> - 获取单个 Worker 详情</li>
        <li><code>GET /api/workers/{worker_key}/console</code> - 获取 Worker 控制台 URL</li>
    </ul>
    
    <h2>前端使用示例:</h2>
    <pre>
// 1. 获取 Worker 列表
fetch('/api/workers')
  .then(r => r.json())
  .then(data => {
    const workers = data.workers;
    
    // 2. 显示 Worker 列表，每个有 "查看日志" 按钮
    for (const [key, worker] of Object.entries(workers)) {
      console.log(`${key}: ${worker.log_stream_url}`);
      
      // 3. 点击按钮时，在新窗口打开日志查看器
      window.open(`/log_viewer.html?ws=${worker.log_stream_url}`);
    }
  });
  
// 或者直接连接 WebSocket
const ws = new WebSocket('ws://localhost:54321');
ws.onmessage = (event) => {
  const logData = JSON.parse(event.data);
  console.log(logData.message);
};
    </pre>
    
    <h2>测试:</h2>
    <pre>
curl http://localhost:5000/api/workers
curl http://localhost:5000/api/workers/user123_002050.SZ_hidden_dragon
curl http://localhost:5000/api/workers/user123_002050.SZ_hidden_dragon/console
    </pre>
    """


if __name__ == '__main__':
    print("=" * 80)
    print("Strategy Manager API with Log Streaming")
    print("=" * 80)
    print("\nAPI Server: http://localhost:5000")
    print("\nEndpoints:")
    print("  • GET  /api/workers")
    print("  • GET  /api/workers/{worker_key}")
    print("  • GET  /api/workers/{worker_key}/console")
    print("\n" + "=" * 80 + "\n")
    
    app.run(host='0.0.0.0', port=5000, debug=True)
