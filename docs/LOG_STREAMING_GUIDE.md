# WebSocket 日志流功能使用指南

## 概述

类似 **Jenkins Console Output**，每个 StrategyWorker 都会暴露一个 WebSocket 服务，用于实时查看日志输出，**无需将日志写入数据库**。

## 架构

```
┌─────────────────────────────────────────────────┐
│  StrategyWorker (002050.SZ - hidden_dragon)     │
│  ┌──────────────────────────────────────────┐   │
│  │  LogStreamServer                         │   │
│  │  ws://0.0.0.0:54321 (动态端口)           │   │
│  └──────────────────────────────────────────┘   │
│         ↑                                        │
│         │ WebSocketLogHandler                    │
│         │                                        │
│  ┌──────┴──────────────────────────────────┐    │
│  │  Logger: VnpyWorker[002050.SZ]          │    │
│  │  • StreamHandler (console)              │    │
│  │  • WebSocketLogHandler (WebSocket)      │    │
│  └─────────────────────────────────────────┘    │
└─────────────────────────────────────────────────┘
         │ WebSocket Protocol
         ↓
┌─────────────────────────────────────────────────┐
│  前端浏览器                                      │
│  • log_viewer.html (单个 Worker)                │
│  • dashboard.html (多个 Workers)                │
└─────────────────────────────────────────────────┘
```

## 特性

- ✅ **独立端口**: 每个 Worker 使用独立的动态端口，避免冲突
- ✅ **实时流式传输**: 日志实时通过 WebSocket 推送到浏览器
- ✅ **双重输出**: 同时输出到控制台和 WebSocket
- ✅ **无数据库依赖**: 不需要将日志写入 MongoDB
- ✅ **自动清理**: Worker 停止时自动关闭 WebSocket 服务
- ✅ **颜色编码**: 不同日志级别使用不同颜色显示

## 快速开始

### 1. 测试单个 Worker 的日志流

```bash
# 启动测试脚本
python examples/test_log_streaming.py

# 输出示例：
# ✅ 日志流服务器已启动
#    WebSocket URL: ws://0.0.0.0:54321
```

在浏览器中打开 `examples/log_viewer.html`，输入 WebSocket URL 并点击"连接"。

### 2. 测试多个 Workers

```bash
# 启动多 Worker 测试
python examples/test_log_streaming.py multi

# 输出示例：
# ✅ Worker[002050.SZ] - ws://0.0.0.0:54321
# ✅ Worker[600132.SH] - ws://0.0.0.0:54322
# ✅ Worker[000002.SZ] - ws://0.0.0.0:54323
```

在浏览器中打开多个标签页，分别连接到不同的 Worker。

### 3. 实际使用：通过 REST API

```bash
# 启动 API 服务器（示例）
python examples/api_with_log_streaming.py

# 在浏览器中打开 Dashboard
open examples/dashboard.html
```

Dashboard 会自动从 API 获取所有 Workers 及其 WebSocket URLs。

## 实际集成

### 在你的 FastAPI/Flask 后端

```python
from strategy_manager.core import MultiStrategyOrchestrator

# 初始化 orchestrator
orchestrator = MultiStrategyOrchestrator(...)
orchestrator.start_all()

# REST API 端点
@app.get("/api/workers")
def list_workers():
    status = orchestrator.get_status()
    return status
    # 返回格式:
    # {
    #   "workers": {
    #     "user123_002050.SZ_hidden_dragon": {
    #       "alive": true,
    #       "stats": {...},
    #       "log_stream_url": "ws://localhost:54321"  # 👈 包含这个！
    #     }
    #   }
    # }

@app.get("/api/workers/{worker_key}/console")
def get_console_url(worker_key: str):
    worker = orchestrator.workers.get(worker_key)
    if not worker:
        raise HTTPException(404)
    
    return {
        "worker_key": worker_key,
        "log_stream_url": worker.get_log_stream_url()
    }
```

### 在你的前端（React/Vue/原生 JS）

```javascript
// 1. 获取 Worker 列表
fetch('/api/workers')
  .then(r => r.json())
  .then(data => {
    Object.entries(data.workers).forEach(([key, worker]) => {
      console.log(`${key}: ${worker.log_stream_url}`);
      
      // 2. 连接到 WebSocket
      connectToWorkerLogs(worker.log_stream_url);
    });
  });

// 3. WebSocket 连接
function connectToWorkerLogs(wsUrl) {
  const ws = new WebSocket(wsUrl);
  
  ws.onmessage = (event) => {
    const logData = JSON.parse(event.data);
    // {
    //   "timestamp": "2026-02-01T14:30:25.123456",
    //   "level": "INFO",
    //   "message": "Bar processed: #1234",
    //   "logger_name": "VnpyWorker[002050.SZ]",
    //   "module": "vnpy_adapter",
    //   "func_name": "run",
    //   "line_no": 95
    // }
    
    displayLog(logData);
  };
}
```

## 消息格式

### WebSocket 消息格式

```json
{
  "timestamp": "2026-02-01T14:30:25.123456",
  "level": "INFO",
  "message": "Starting vnpy engine for 002050.SZ",
  "logger_name": "VnpyWorker[002050.SZ]",
  "module": "vnpy_adapter",
  "func_name": "run",
  "line_no": 95
}
```

### 日志级别

- `DEBUG` - 调试信息（绿色）
- `INFO` - 一般信息（蓝色）
- `WARNING` - 警告（黄色）
- `ERROR` - 错误（橙色）
- `CRITICAL` - 严重错误（红色）

## 配置

### 禁用日志流（如果需要）

如果你想禁用某个 Worker 的日志流功能，可以在创建 Worker 时传入参数：

```python
class VnpyWorkerAdapter(StrategyWorker):
    def __init__(self, ..., enable_log_stream=True):
        super().__init__(...)
        
        if enable_log_stream:
            # 启用 LogStreamServer
            self._log_server = LogStreamServer(...)
        else:
            self._log_server = None
```

### 自定义端口范围

默认使用动态端口（port=0），系统会自动分配。如果需要固定端口范围：

```python
# 在 vnpy_adapter.py 中
self._log_server = LogStreamServer(
    host="0.0.0.0",
    port=0  # 改为具体端口，如 8765
)
```

## 生产环境建议

### 1. 端口管理

- 使用动态端口（推荐）：避免端口冲突
- 或者预分配端口池：例如 Worker ID → 端口映射

### 2. 安全性

```python
# 只监听本地地址
self._log_server = LogStreamServer(host="127.0.0.1", port=0)

# 或者使用 Nginx 反向代理 + 认证
# nginx.conf
location /ws/worker/ {
    proxy_pass http://localhost:54321;
    proxy_http_version 1.1;
    proxy_set_header Upgrade $http_upgrade;
    proxy_set_header Connection "upgrade";
    
    # 添加认证
    auth_basic "Worker Console";
    auth_basic_user_file /etc/nginx/.htpasswd;
}
```

### 3. 资源限制

- WebSocket 连接数限制：建议在 LogStreamServer 中添加连接数限制
- 日志缓冲区：可以添加环形缓冲区，保留最近 N 条日志

```python
# 改进版 LogStreamServer
class LogStreamServer:
    def __init__(self, host, port, max_clients=10, buffer_size=1000):
        self.max_clients = max_clients
        self.log_buffer = deque(maxlen=buffer_size)  # 环形缓冲区
    
    async def _handler(self, websocket):
        if len(self.connected_clients) >= self.max_clients:
            await websocket.close(1008, "Too many connections")
            return
        
        # 新连接时，发送历史日志
        for log in self.log_buffer:
            await websocket.send(json.dumps(log))
        
        # 继续处理新日志...
```

## 故障排查

### 问题: WebSocket 连接失败

**检查项:**
1. Worker 是否正在运行？
2. 防火墙是否阻止了端口？
3. WebSocket URL 是否正确？

```bash
# 测试 WebSocket 端口是否开放
nc -zv localhost 54321

# 或使用 wscat
npm install -g wscat
wscat -c ws://localhost:54321
```

### 问题: 看不到日志输出

**检查项:**
1. Logger 级别是否正确？
2. WebSocketLogHandler 是否已添加？
3. 是否有日志产生？

```python
# 调试模式
logger.setLevel(logging.DEBUG)
logger.debug("Test message")
```

### 问题: 端口冲突

```python
# 确保使用动态端口
self._log_server = LogStreamServer(host="0.0.0.0", port=0)

# 或者捕获异常，重试其他端口
for port in range(8000, 9000):
    try:
        self._log_server = LogStreamServer(host="0.0.0.0", port=port)
        self._log_server.start()
        break
    except OSError:
        continue
```

## 高级用法

### 1. 添加日志过滤器

```python
class LogLevelFilter(logging.Filter):
    def __init__(self, min_level):
        self.min_level = min_level
    
    def filter(self, record):
        return record.levelno >= self.min_level

# 只发送 WARNING 及以上到 WebSocket
ws_handler = WebSocketLogHandler(log_server)
ws_handler.addFilter(LogLevelFilter(logging.WARNING))
```

### 2. 日志搜索和过滤（前端）

```javascript
// 在浏览器中过滤日志
function filterLogs(keyword) {
    const entries = document.querySelectorAll('.log-entry');
    entries.forEach(entry => {
        if (entry.textContent.includes(keyword)) {
            entry.style.display = 'block';
        } else {
            entry.style.display = 'none';
        }
    });
}
```

### 3. 导出日志

```javascript
function exportLogs() {
    const consoleEl = document.getElementById('console');
    const logs = consoleEl.innerText;
    
    const blob = new Blob([logs], { type: 'text/plain' });
    const url = URL.createObjectURL(blob);
    
    const a = document.createElement('a');
    a.href = url;
    a.download = `worker-logs-${Date.now()}.txt`;
    a.click();
}
```

## 性能优化

### 1. 批量发送日志

```python
# 改进 WebSocketLogHandler
class BatchWebSocketLogHandler(logging.Handler):
    def __init__(self, log_server, batch_size=10, flush_interval=1.0):
        super().__init__()
        self.log_server = log_server
        self.batch = []
        self.batch_size = batch_size
        # 定时刷新...
    
    def emit(self, record):
        self.batch.append(self.format_record(record))
        if len(self.batch) >= self.batch_size:
            self.flush()
```

### 2. 压缩传输

```javascript
// 使用 permessage-deflate 扩展
const ws = new WebSocket('ws://localhost:54321', {
    perMessageDeflate: true
});
```

## 总结

**优势：**
- 🚀 实时日志，无延迟
- 💾 不占用数据库存储
- 🎨 前端友好，易于展示
- 🔧 易于调试和监控

**适用场景：**
- 开发环境：实时查看策略运行状态
- 测试环境：快速定位问题
- 生产环境：运维监控（配合认证和访问控制）

**不适用场景：**
- 长期日志归档（建议使用文件或数据库）
- 合规审计（需要持久化存储）
