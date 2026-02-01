"""Abstract strategy worker interface - engine agnostic.

This defines the contract that all strategy workers must implement,
regardless of underlying execution engine (backtrader, vnpy, etc.)
"""

from abc import ABC, abstractmethod
from typing import Dict, Any, Optional
from enum import Enum
import threading


class WorkerState(Enum):
    """Worker lifecycle states."""
    CREATED = "created"
    RUNNING = "running"
    PAUSED = "paused"
    STOPPED = "stopped"
    ERROR = "error"


class StrategyWorker(ABC, threading.Thread):
    """
    Abstract base class for all strategy workers.
    
    Provides a unified interface for different execution engines.
    Each concrete implementation wraps a specific engine (backtrader, vnpy, etc.)
    """
    
    def __init__(
        self,
        symbol: str,
        strategy_key: str,
        user_id: Optional[str] = None,
        **kwargs
    ):
        super().__init__(daemon=True, name=f"Worker-{symbol}-{strategy_key}")
        self.symbol = symbol
        self.strategy_key = strategy_key
        self.user_id = user_id
        self._state = WorkerState.CREATED
        self._stop_event = threading.Event()
    
    @abstractmethod
    def run(self):
        """Main worker thread loop - must be implemented by subclass."""
        pass
    
    @abstractmethod
    def stop(self, save_state: bool = True):
        """
        Stop the worker gracefully.
        
        Args:
            save_state: Whether to persist state before stopping
        """
        pass
    
    @abstractmethod
    def get_stats(self) -> Dict[str, Any]:
        """
        Get current worker statistics.
        
        Returns:
            Dict containing worker metrics (position, PnL, bars processed, etc.)
        """
        pass
    
    @abstractmethod
    def get_position(self) -> int:
        """Get current position size."""
        pass
    
    @abstractmethod
    def save_state(self) -> bool:
        """Persist worker state for recovery."""
        pass
    
    @abstractmethod
    def load_state(self) -> bool:
        """Restore worker state from persistence."""
        pass
    
    @property
    def state(self) -> WorkerState:
        """Get current worker state."""
        return self._state
    
    def is_running(self) -> bool:
        """Check if worker is currently running."""
        return self._state == WorkerState.RUNNING and self.is_alive()
    
    def get_worker_info(self) -> Dict[str, Any]:
        """Get worker metadata."""
        return {
            "symbol": self.symbol,
            "strategy_key": self.strategy_key,
            "user_id": self.user_id,
            "state": self._state.value,
            "thread_alive": self.is_alive(),
        }
