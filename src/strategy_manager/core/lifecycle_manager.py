"""Engine-agnostic worker lifecycle manager.

Handles automatic start/stop based on trading schedule.
Works with any StrategyWorker implementation (backtrader, vnpy, etc.)
"""

import threading
import time
import logging
from datetime import datetime
from typing import List, Dict, Any, Optional, Callable
from enum import Enum

from .strategy_worker import StrategyWorker, WorkerState
from .trading_scheduler import TradingScheduler


class LifecycleEvent(Enum):
    """Worker lifecycle events."""
    PRE_MARKET_OPEN = "pre_market_open"
    MARKET_OPEN = "market_open"
    PRE_MARKET_CLOSE = "pre_market_close"
    MARKET_CLOSE = "market_close"
    POST_MARKET_CLOSE = "post_market_close"


class LifecycleManager(threading.Thread):
    """
    Engine-agnostic worker lifecycle manager.
    
    Automatically manages worker lifecycle based on trading schedule:
    - Stops workers after market close to save memory
    - Recreates workers before market open
    - Handles state persistence across sessions
    
    Works with any StrategyWorker implementation.
    
    Example:
        manager = LifecycleManager()
        manager.add_worker(vnpy_worker, factory=vnpy_factory)
        manager.add_worker(bt_worker, factory=bt_factory)
        manager.start()
    """
    
    # Event timings (hour, minute)
    PRE_MARKET_OPEN_TIME = (9, 25)
    POST_MARKET_CLOSE_TIME = (15, 5)
    CLEANUP_TIME = (15, 10)
    
    def __init__(
        self,
        auto_start: bool = True,
        auto_stop: bool = True,
        check_interval_sec: int = 30,
        scheduler: Optional[TradingScheduler] = None,
    ):
        super().__init__(daemon=True, name="LifecycleManager")
        
        self.auto_start = auto_start
        self.auto_stop = auto_stop
        self.check_interval_sec = check_interval_sec
        self.scheduler = scheduler or TradingScheduler()
        
        # Worker registry: worker_key -> (worker, factory, config)
        self.workers: Dict[str, StrategyWorker] = {}
        self.worker_factories: Dict[str, Callable] = {}
        self.worker_configs: Dict[str, Dict[str, Any]] = {}
        
        self._stop_event = threading.Event()
        self._last_event_time: Dict[LifecycleEvent, Optional[datetime]] = {
            event: None for event in LifecycleEvent
        }
        
        self.log = logging.getLogger("LifecycleManager")
        if not self.log.handlers:
            h = logging.StreamHandler()
            fmt = logging.Formatter("%(asctime)s %(levelname)s %(name)s: %(message)s")
            h.setFormatter(fmt)
            self.log.addHandler(h)
        self.log.setLevel(logging.INFO)
    
    def add_worker(
        self,
        worker: StrategyWorker,
        factory: Optional[Callable] = None,
        config: Optional[Dict[str, Any]] = None
    ) -> str:
        """
        Register a worker for lifecycle management.
        
        Args:
            worker: StrategyWorker instance
            factory: Factory function to recreate worker (required for auto-restart)
                     Signature: factory(config) -> StrategyWorker
            config: Configuration to recreate worker
        
        Returns:
            Worker key for tracking
        """
        worker_key = f"{worker.user_id}_{worker.symbol}_{worker.strategy_key}"
        
        self.workers[worker_key] = worker
        
        if factory and config:
            self.worker_factories[worker_key] = factory
            self.worker_configs[worker_key] = config
            self.log.info(f"Added worker {worker_key} with recreation capability")
        else:
            self.log.info(f"Added worker {worker_key} (no auto-restart)")
        
        return worker_key
    
    def remove_worker(self, worker_key: str) -> None:
        """Remove worker from lifecycle management."""
        if worker_key in self.workers:
            del self.workers[worker_key]
            self.worker_factories.pop(worker_key, None)
            self.worker_configs.pop(worker_key, None)
            self.log.info(f"Removed worker {worker_key}")
    
    def stop(self) -> None:
        """Stop lifecycle manager."""
        self._stop_event.set()
        self.log.info("Lifecycle manager stopping")
    
    def run(self) -> None:
        """Main lifecycle management loop."""
        self.log.info("Lifecycle manager started")
        
        while not self._stop_event.is_set():
            try:
                now = datetime.now()
                current_time = (now.hour, now.minute)
                
                # Skip non-trading days
                if not self.scheduler.is_trading_day(now):
                    time.sleep(self.check_interval_sec)
                    continue
                
                # Pre-market open (09:25)
                if self.auto_start and current_time >= self.PRE_MARKET_OPEN_TIME and current_time < (9, 30):
                    if not self._is_event_triggered_today(LifecycleEvent.PRE_MARKET_OPEN):
                        self.log.info("⏰ Pre-market open - starting workers")
                        self._on_pre_market_open()
                        self._mark_event_triggered(LifecycleEvent.PRE_MARKET_OPEN)
                
                # Post-market close (15:05)
                if self.auto_stop and current_time >= self.POST_MARKET_CLOSE_TIME and current_time < (15, 10):
                    if not self._is_event_triggered_today(LifecycleEvent.POST_MARKET_CLOSE):
                        self.log.info("⏰ Post-market close - stopping workers")
                        self._on_post_market_close()
                        self._mark_event_triggered(LifecycleEvent.POST_MARKET_CLOSE)
                
                # Cleanup (15:10)
                if current_time >= self.CLEANUP_TIME and current_time < (15, 15):
                    if not self._is_event_triggered_today(LifecycleEvent.MARKET_CLOSE):
                        self.log.info("⏰ Cleanup time")
                        self._on_cleanup()
                        self._mark_event_triggered(LifecycleEvent.MARKET_CLOSE)
                
            except Exception as e:
                self.log.error(f"Error in lifecycle loop: {e}", exc_info=True)
            
            time.sleep(self.check_interval_sec)
        
        self.log.info("Lifecycle manager stopped")
    
    def _is_event_triggered_today(self, event: LifecycleEvent) -> bool:
        """Check if event already triggered today."""
        last_time = self._last_event_time.get(event)
        if last_time is None:
            return False
        now = datetime.now()
        return last_time.date() == now.date()
    
    def _mark_event_triggered(self, event: LifecycleEvent) -> None:
        """Mark event as triggered."""
        self._last_event_time[event] = datetime.now()
    
    def _on_pre_market_open(self) -> None:
        """Handle pre-market open - recreate stopped workers."""
        self.log.info("=" * 60)
        self.log.info("PRE-MARKET OPEN EVENT")
        self.log.info("=" * 60)
        
        active = [k for k, w in self.workers.items() if w.is_running()]
        stopped = [k for k, w in self.workers.items() if not w.is_running()]
        
        self.log.info(f"Workers: {len(active)} active, {len(stopped)} stopped")
        
        # Recreate stopped workers
        if stopped and self.worker_factories:
            self.log.info(f"Recreating {len(stopped)} stopped workers")
            
            for worker_key in stopped:
                if worker_key in self.worker_factories:
                    try:
                        factory = self.worker_factories[worker_key]
                        config = self.worker_configs[worker_key]
                        
                        # Create new worker instance
                        new_worker = factory(config)
                        new_worker.load_state()
                        new_worker.start()
                        
                        # Replace old worker
                        self.workers[worker_key] = new_worker
                        
                        self.log.info(f"✅ Recreated worker {worker_key}")
                        
                    except Exception as e:
                        self.log.error(f"Failed to recreate worker {worker_key}: {e}")
            
            self.log.info("Worker recreation complete")
    
    def _on_post_market_close(self) -> None:
        """Handle post-market close - stop all workers."""
        self.log.info("=" * 60)
        self.log.info("POST-MARKET CLOSE EVENT")
        self.log.info("=" * 60)
        
        active = [k for k, w in self.workers.items() if w.is_running()]
        
        if not active:
            self.log.info("No active workers to stop")
            return
        
        self.log.info(f"Stopping {len(active)} active workers")
        
        for worker_key in active:
            try:
                worker = self.workers[worker_key]
                worker.stop(save_state=True)
                self.log.info(f"✅ Stopped worker {worker_key}")
            except Exception as e:
                self.log.error(f"Failed to stop worker {worker_key}: {e}")
        
        time.sleep(2)  # Wait for graceful shutdown
    
    def _on_cleanup(self) -> None:
        """Handle cleanup - force stop any lingering workers."""
        active = [k for k, w in self.workers.items() if w.is_running()]
        
        if active:
            self.log.warning(f"{len(active)} workers still active - forcing stop")
            for worker_key in active:
                try:
                    self.workers[worker_key].stop(save_state=False)
                except Exception as e:
                    self.log.error(f"Failed to force-stop worker {worker_key}: {e}")
        else:
            self.log.info("All workers cleanly stopped")
    
    def get_status(self) -> Dict[str, Any]:
        """Get lifecycle manager status."""
        active = sum(1 for w in self.workers.values() if w.is_running())
        stopped = len(self.workers) - active
        
        return {
            "total_workers": len(self.workers),
            "active_workers": active,
            "stopped_workers": stopped,
            "auto_start": self.auto_start,
            "auto_stop": self.auto_stop,
            "is_trading_time": self.scheduler.is_trading_time(),
            "last_events": {
                event.value: last_time.isoformat() if last_time else None
                for event, last_time in self._last_event_time.items()
            },
        }
