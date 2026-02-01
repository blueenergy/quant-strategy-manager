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

```bash
# Basic installation
pip install quant-strategy-manager

# With vnpy support
pip install quant-strategy-manager[vnpy]

# With backtrader support
pip install quant-strategy-manager[backtrader]

# With all engines
pip install quant-strategy-manager[all]
```

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
  "strategy_key": "hidden_dragon",
  "enabled": true,
  
  // Specify engine
  "engine": "vnpy",
  "engine_class": "scripts.single_stream_hidden_dragon.SingleStreamRealTimeEngine",
  
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
