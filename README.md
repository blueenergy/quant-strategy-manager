# Quant Strategy Manager

**Engine-agnostic strategy orchestration library for quantitative trading.**

Supports multiple execution engines (backtrader, vnpy, and more) through a unified interface.

## Features

- 🔄 **Engine Agnostic**: Works with backtrader, vnpy, or any custom engine
- ⏰ **Lifecycle Management**: Automatic worker start/stop based on trading schedule
- 💾 **State Persistence**: Resume strategies across restarts
- 📊 **Multi-Strategy**: Manage hundreds of strategies from database configuration
- 🔌 **Pluggable**: Easy to add new execution engines via adapter pattern

## Architecture

```
┌─────────────────────────────────────────────────────┐
│         MultiStrategyOrchestrator                   │
│  • Database-driven configuration                    │
│  • Dynamic worker creation/destruction              │
│  • Hot reload support                               │
└─────────────────┬───────────────────────────────────┘
                  │
┌─────────────────▼───────────────────────────────────┐
│          LifecycleManager                           │
│  • Trading schedule monitoring                      │
│  • Auto start/stop workers                          │
│  • State persistence                                │
└─────────────────┬───────────────────────────────────┘
                  │
        ┌─────────┴─────────┐
        │                   │
┌───────▼──────┐    ┌──────▼──────┐
│ VnpyAdapter  │    │ BTAdapter   │
│  (vnpy eng.) │    │ (backtrader)│
└──────────────┘    └─────────────┘
```

## Quick Start

### Quick Start

#### 1. Installation

**注意**：本项目采用环境隔离策略：
- **核心库**：可独立安装
- **API Server**：必须在 vnpy 环境中运行（依赖 vnpy 生态）

##### 方式 1: 独立安装（仅使用核心功能）

```bash
# 安装核心库
pip install -e .

# 或安装开发工具
pip install -e ".[dev]"
```

##### 方式 2: 在 vnpy 环境中安装（运行 API Server）

```bash
# 1. 进入 vnpy 虚拟环境
cd ~/trading/vnpy-live-trading
source .venv/bin/activate

# 2. 安装 API Server 依赖
cd ~/trading/quant-strategy-manager
pip install -r requirements-api.txt

# 注意：vnpy 及其依赖应该已在 vnpy-live-trading/.venv 中安装
```

##### 方式 3: 在 backtrader 环境中使用

```bash
# 1. 创建 backtrader 专用环境（如果还没有）
python -m venv ~/trading/backtrader-env
source ~/trading/backtrader-env/bin/activate

# 2. 安装 backtrader
pip install backtrader>=1.9.76

# 3. 安装 quant-strategy-manager 核心库
cd ~/trading/quant-strategy-manager
pip install -e .
```

**依赖策略说明**：
- **核心库依赖**：`pymongo`、`python-dateutil`、`websockets`（最小化）
- **交易引擎**：`vnpy`/`backtrader` 不作为依赖声明，通过**环境隔离**使用
- **API Server**：`fastapi`、`uvicorn` 按需安装（可选）

**设计理念**：Engine-agnostic（引擎无关）
- 用户可以只使用 vnpy 适配器，不需要安装 backtrader
- 用户可以只使用 backtrader 适配器，不需要安装 vnpy  
- 核心库保持轻量级，交易引擎由用户环境提供

#### 2. Configuration Setup

Framework uses **config directory** for shared configuration.

**Load Priority (highest to lowest):**
1. **Environment Variables** (e.g., `MONGO_URI`, `MONGO_DB`) - for production
2. **`.env` file** (config/.env) - for local development  
3. **`production.json`** (config/production.json) - shared defaults
4. **Hardcoded defaults** - fallback values

**Setup:**

```bash
# 1. Copy example .env
cp config/.env.example config/.env

# 2. Edit config/.env with your local values (for development)
# Note: .env is in .gitignore and should NOT be committed
cat > config/.env << EOF
MONGO_URI=mongodb://localhost:27017
MONGO_DB=finance
ENABLE_VNPY=true
EOF

# 3. Edit config/production.json with non-sensitive defaults
# This file IS committed to Git
cat > config/production.json << EOF
{
  "mongo_uri": "mongodb://localhost:27017",
  "mongo_db": "finance",
  "import_paths": [
    "/home/user/trading/vnpy-live-trading"
  ]
}
EOF
```

**Environment Variables (Production):**

In production, inject via environment (Docker, Kubernetes, systemd, etc):

```bash
# Docker
docker run -e MONGO_URI="mongodb://prod-host:27017" strategy-manager:latest

# Kubernetes
kubectl set env deployment/strategy-manager MONGO_URI="mongodb://prod-host:27017"

# systemd
export MONGO_URI="mongodb://prod-host:27017"
systemctl start strategy-manager
```

**Check Configuration Sources:**

```bash
# See where config is loaded from
strategy-manager config

# Show actual loaded values
strategy-manager config --show
```

#### 3. Database Configuration

Store strategy configurations in MongoDB:

```javascript
// Collection: watchlist_strategies
{
  "user_id": "user123",
  "symbol": "002050.SZ",
  "strategy_key": "hidden_dragon",  // 策略标识符
  "enabled": true,
  
  // engine 字段会由 API 自动添加，前端不需要设置
  // "engine": "vnpy"  ← 后端自动添加（实盘策略仅支持 vnpy）
  
  // Strategy parameters
  "params": {
    "limit_up_rate": 0.090,
    "max_callback_days": 20,
    "stop_loss_pct": 0.05,
    "take_profit_pct": 0.15,
    ...
  }
}
```

**前端保存示例**：

```javascript
// 前端只需要提供这些字段
const data = {
  symbol: "002050.SZ",
  strategy: "hidden_dragon",  // strategy_key
  params: { /* ... */ }
}

// POST /api/user/watchlist/strategy
// 后端会自动添加 engine: "vnpy"
```

**支持的策略类型** (strategy_key):

| strategy_key | 说明 | 引擎类（自动解析） |
|--------------|------|-------------------|
| `hidden_dragon` | 潜龙出海策略 | SingleStreamRealTimeEngine |
| `turtle` | 海龟交易策略 | TurtleRealTimeEngine |
| `single_yang` | 单阳不破策略 | SingleYangRealTimeEngine |
| `grid` | 网格交易策略 | GridRealTimeEngine |

**工作流程**：

1. **前端提交**：只需要 `symbol` + `strategy_key` + `params`
2. **后端自动添加**：`engine: "vnpy"`（因为实盘策略目前仅支持 vnpy）
3. **系统自动解析**：根据 `strategy_key` 从注册表查找对应的引擎类
4. **Worker 启动**：使用解析出的引擎类创建策略实例

**注意**：
- ✅ 前端不需要关心 `engine` 字段（后端自动设置）
- ✅ 前端不需要关心 `engine_class` 字段（系统自动解析）
- ✅ 只需要选择 `strategy_key` 即可
    "max_callback_days": 20,
    "stop_loss_pct": 0.05,
    "take_profit_pct": 0.15,
    ...
  }
}
```

## Real-Time Log Streaming 🔥

Each worker exposes a **WebSocket console output** (like Jenkins) for real-time log monitoring - **no database writes needed**!

### How It Works

```
┌─────────────────────────────────────┐
│  StrategyWorker (002050.SZ)         │
│  • Runs strategy logic              │
│  • Logs to console + WebSocket      │
│  • ws://localhost:8765 (dynamic)    │
└─────────────────────────────────────┘
         │ WebSocket
         ↓
┌─────────────────────────────────────┐
│  Browser (log_viewer.html)          │
│  • Real-time log output             │
│  • Color-coded by level             │
│  • No database needed               │
└─────────────────────────────────────┘
```

### Usage

```python
# Start strategy manager
python -m strategy_manager.cli start

# Get worker status (includes WebSocket URLs)
orchestrator.get_status()
# {
#   "workers": {
#     "user123_002050.SZ_hidden_dragon": {
#       "log_stream_url": "ws://localhost:54321",
#       ...
#     }
#   }
# }
```

## Development: Linting & Formatting

We use `ruff` for fast linting/auto-fix and `black` for canonical formatting.

Install the tools (developer environment):

```bash
# inside your dev venv
pip install ruff black pre-commit
```

Run checks:

```bash
# Lint (ruff)
ruff check .

# Format check (black)
black --check .
```

Auto-fix / format:

```bash
# Auto-fix lint issues and apply simple fixes
ruff check --fix .

# Or use ruff format
ruff format .

# Format code with black
black .
```

Add to git hooks with `pre-commit` (recommended):

1. Create a `.pre-commit-config.yaml` with `ruff` and `black` hooks.
2. Install: `pre-commit install`.

Example minimal `.pre-commit-config.yaml`:

```yaml
repos:
  - repo: https://github.com/charliermarsh/ruff-pre-commit
    rev: "stable"
    hooks:
      - id: ruff

  - repo: https://github.com/psf/black
    rev: 23.9.1
    hooks:
      - id: black
```

This gives fast feedback and enforces consistent formatting across contributors.


### View Logs in Browser

1. Open `examples/log_viewer.html` in browser
2. Enter WebSocket URL (e.g., `ws://localhost:54321`)
3. Click "连接" to see real-time logs

**Features:**
- ✅ Real-time streaming (no database writes)
- ✅ Color-coded log levels (DEBUG/INFO/WARNING/ERROR)
- ✅ Auto-scroll with manual override
- ✅ Independent console per worker
- ✅ Similar to Jenkins console output

### Test It

```bash
# Single worker test
python examples/test_log_streaming.py

# Multi-worker test
python examples/test_log_streaming.py multi
```

Then open `examples/log_viewer.html` in your browser.

## Custom Engine Adapter

Easily add support for new engines:

```python
from strategy_manager.core import StrategyWorker, WorkerState

class MyEngineAdapter(StrategyWorker):
    def __init__(self, symbol, strategy_key, params, **kwargs):
        super().__init__(symbol, strategy_key)
        self.engine = MyEngine(symbol, params)
    
    def run(self):
        self._state = WorkerState.RUNNING
        self.engine.start()
        while not self._stop_event.is_set():
            self._stop_event.wait(timeout=1)
        self._state = WorkerState.STOPPED
    
    def stop(self, save_state=True):
        if save_state:
            self.save_state()
        self.engine.stop()
        self._stop_event.set()
    
    def get_stats(self) -> dict:
        return {"position": self.engine.position}
    
    # Implement other required methods...
```

## Components

### StrategyWorker (Abstract Base)
Defines the contract all workers must implement. Engine-agnostic interface.

### LifecycleManager
Handles automatic worker start/stop based on trading schedule. Works with any `StrategyWorker`.

### MultiStrategyOrchestrator
Manages multiple workers from database configuration. Supports hot reload and dynamic scaling.

### Adapters
- `VnpyWorkerAdapter`: Wraps vnpy `RealTimeEngine`
- `BacktraderWorkerAdapter`: Wraps backtrader `Cerebro`

## Benefits

### For vnpy-live-trading
```python
# Before: Manual lifecycle management
engine = SingleStreamRealTimeEngine(...)
engine.start()

# After: Automatic management
orchestrator.add_strategy("002050.SZ", "hidden_dragon", engine="vnpy")
# Handles start/stop/state automatically
```

### For stock-execution-system
```python
# Before: Tightly coupled to backtrader
worker = UnifiedWorker(...)  # Backtrader only

# After: Engine-agnostic
orchestrator.add_strategy("600990.SH", "turtle", engine="backtrader")
orchestrator.add_strategy("002050.SZ", "dragon", engine="vnpy")
# Mix and match engines
```

## License

MIT License

## Contributing

Contributions welcome! Please see CONTRIBUTING.md for details.
