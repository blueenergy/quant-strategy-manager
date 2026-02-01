"""Strategy manager package - engine-agnostic orchestration."""

from .core.strategy_worker import StrategyWorker, WorkerState
from .core.lifecycle_manager import LifecycleManager, LifecycleEvent
from .core.multi_strategy_orchestrator import MultiStrategyOrchestrator, StrategyConfig
from .core.trading_scheduler import TradingScheduler

__version__ = "0.1.0"

__all__ = [
    "StrategyWorker",
    "WorkerState",
    "LifecycleManager",
    "LifecycleEvent",
    "MultiStrategyOrchestrator",
    "StrategyConfig",
    "TradingScheduler",
]
