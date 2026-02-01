"""Multi-strategy orchestrator - engine agnostic.

Manages multiple strategy workers from database configuration.
Works with any StrategyWorker implementation (backtrader, vnpy, etc.)
"""

import logging
import threading
import time
from typing import Dict, Optional, Any, Callable
from dataclasses import dataclass
from pymongo import MongoClient
import os

from .strategy_worker import StrategyWorker


@dataclass
class StrategyConfig:
    """Strategy configuration from database."""
    symbol: str
    strategy_key: str
    params: Dict[str, Any]
    enabled: bool
    user_id: Optional[str] = None
    engine: str = "backtrader"  # "backtrader" or "vnpy"
    engine_class: Optional[str] = None  # For vnpy: full class path
    
    @classmethod
    def from_db_doc(cls, doc: Dict) -> 'StrategyConfig':
        """Create from database document."""
        return cls(
            symbol=doc.get("symbol", ""),
            strategy_key=doc.get("strategy_key", ""),
            params=doc.get("params", {}),
            enabled=doc.get("enabled", True),
            user_id=str(doc.get("user_id")) if doc.get("user_id") is not None else None,
            engine=doc.get("engine", "backtrader"),
            engine_class=doc.get("engine_class"),
        )


class MultiStrategyOrchestrator:
    """
    Engine-agnostic multi-strategy orchestrator.
    
    Manages multiple strategy workers based on database configuration.
    Supports both backtrader and vnpy engines (or any StrategyWorker implementation).
    
    Example:
        # Create orchestrator
        orchestrator = MultiStrategyOrchestrator(
            worker_factories={
                "vnpy": vnpy_factory,
                "backtrader": bt_factory,
            }
        )
        
        # Load from database and start
        orchestrator.load_configurations()
        orchestrator.start_all()
    """
    
    def __init__(
        self,
        worker_factories: Dict[str, Callable],  # engine -> factory function
        mongo_uri: Optional[str] = None,
        mongo_db: Optional[str] = None,
        config_collection: str = "watchlist_strategies",
        user_id: Optional[str] = None,
        auto_reload_interval: int = 60,
    ):
        """
        Initialize orchestrator.
        
        Args:
            worker_factories: Dict mapping engine type to factory function
                             e.g., {"vnpy": create_vnpy_worker, "backtrader": create_bt_worker}
            mongo_uri: MongoDB connection URI
            mongo_db: MongoDB database name
            config_collection: Collection name for strategy configs
            user_id: Filter strategies by user_id (optional)
            auto_reload_interval: Config reload interval in seconds (0 to disable)
        """
        self.worker_factories = worker_factories
        self.mongo_uri = mongo_uri or os.getenv("MONGO_URL", "mongodb://localhost:27017")
        self.mongo_db = mongo_db or os.getenv("MONGO_DB", "finance")
        self.config_collection = config_collection
        self.user_id = user_id
        self.auto_reload_interval = auto_reload_interval
        
        # Setup logging
        self.log = logging.getLogger("MultiStrategyOrchestrator")
        self.log.propagate = False
        if not self.log.handlers:
            h = logging.StreamHandler()
            fmt = logging.Formatter("%(asctime)s %(levelname)s %(name)s: %(message)s")
            h.setFormatter(fmt)
            self.log.addHandler(h)
        self.log.setLevel(logging.INFO)
        
        # MongoDB connection
        self.client = MongoClient(self.mongo_uri)
        self.db = self.client[self.mongo_db]
        self.config_coll = self.db[self.config_collection]
        
        # Worker management
        self.workers: Dict[str, StrategyWorker] = {}  # key: f"{user_id}_{symbol}_{strategy}"
        self.configurations: Dict[str, StrategyConfig] = {}
        
        # Control
        self._stop_event = threading.Event()
        self._monitor_thread: Optional[threading.Thread] = None
        
        self.log.info(
            f"Orchestrator initialized | db={self.mongo_db} collection={self.config_collection}"
        )
    
    def load_configurations(self) -> int:
        """Load strategy configurations from database."""
        self.log.info("Loading strategy configurations from database")
        
        try:
            query = {"enabled": True}
            if self.user_id:
                query["user_id"] = self.user_id
            
            cursor = self.config_coll.find(query)
            
            new_configs = {}
            for doc in cursor:
                config = StrategyConfig.from_db_doc(doc)
                
                if not config.symbol or not config.strategy_key:
                    self.log.warning(f"Skipping invalid config: {doc}")
                    continue
                
                # Validate engine type
                if config.engine not in self.worker_factories:
                    self.log.warning(
                        f"Skipping config with unknown engine '{config.engine}': {config.symbol}"
                    )
                    continue
                
                key = f"{config.user_id}_{config.symbol}_{config.strategy_key}"
                new_configs[key] = config
                
                self.log.info(
                    f"Loaded config: {config.symbol} | strategy={config.strategy_key} | "
                    f"engine={config.engine}"
                )
            
            self.configurations = new_configs
            self.log.info(f"Loaded {len(self.configurations)} enabled strategy configurations")
            
            return len(self.configurations)
            
        except Exception as e:
            self.log.error(f"Failed to load configurations: {e}", exc_info=True)
            return 0
    
    def sync_workers(self):
        """Synchronize workers with current configurations."""
        current_keys = set(self.workers.keys())
        target_keys = set(self.configurations.keys())
        
        # Workers to stop
        to_stop = current_keys - target_keys
        for key in to_stop:
            self.log.info(f"Stopping worker for removed config: {key}")
            self._stop_worker(key)
        
        # Workers to start
        to_start = target_keys - current_keys
        for key in to_start:
            config = self.configurations[key]
            self.log.info(f"Starting new worker: {config.symbol} | {config.engine}")
            self._start_worker(key, config)
        
        self.log.info(
            f"Worker sync complete | running={len(self.workers)} "
            f"stopped={len(to_stop)} started={len(to_start)}"
        )
    
    def _start_worker(self, key: str, config: StrategyConfig):
        """Start a worker for the given configuration."""
        try:
            # Get appropriate factory
            factory = self.worker_factories.get(config.engine)
            if not factory:
                self.log.error(f"No factory for engine '{config.engine}'")
                return
            
            # Resolve account params
            account_params = self._resolve_account_params(config.user_id)
            
            # Build worker config
            worker_config = {
                "symbol": config.symbol,
                "strategy_key": config.strategy_key,
                "params": {**config.params, **account_params},
                "user_id": config.user_id,
                **account_params,
            }
            
            # Add engine-specific config
            if config.engine == "vnpy":
                if not config.engine_class:
                    self.log.error(f"engine_class required for vnpy worker: {config.symbol}")
                    return
                worker_config["engine_class_path"] = config.engine_class
            
            # Create worker
            worker = factory(worker_config)
            worker.load_state()
            worker.start()
            
            self.workers[key] = worker
            self.log.info(f"Worker started: {key}")
            
        except Exception as e:
            self.log.error(f"Failed to start worker {key}: {e}", exc_info=True)
    
    def _stop_worker(self, key: str):
        """Stop a worker."""
        worker = self.workers.get(key)
        if not worker:
            return
        
        try:
            worker.stop(save_state=True)
            worker.join(timeout=5)
            del self.workers[key]
            self.log.info(f"Worker stopped: {key}")
        except Exception as e:
            self.log.error(f"Error stopping worker {key}: {e}", exc_info=True)
    
    def _resolve_account_params(self, user_id: Optional[str]) -> Dict[str, Any]:
        """Resolve securities account for user."""
        account_params = {}
        if user_id:
            try:
                acct_doc = self.db["securities_accounts"].find_one({"user_id": user_id})
                if acct_doc:
                    account_params = {
                        "securities_account_id": str(acct_doc.get("_id")),
                        "broker": acct_doc.get("broker"),
                        "account_id": acct_doc.get("account_id"),
                    }
            except Exception as e:
                self.log.error(f"Failed to load account for user {user_id}: {e}")
        return account_params
    
    def start_all(self):
        """Load configurations and start all workers."""
        self.log.info("Starting all workers")
        
        count = self.load_configurations()
        if count == 0:
            self.log.warning("No active configurations found")
            return
        
        self.sync_workers()
        
        # Start monitoring thread if auto-reload enabled
        if self.auto_reload_interval > 0:
            self._monitor_thread = threading.Thread(
                target=self._monitor_loop,
                daemon=True,
                name="ConfigMonitor"
            )
            self._monitor_thread.start()
            self.log.info(f"Config monitoring started (reload every {self.auto_reload_interval}s)")
    
    def _monitor_loop(self):
        """Monitor configuration changes and sync workers."""
        while not self._stop_event.is_set():
            try:
                if self._stop_event.wait(timeout=self.auto_reload_interval):
                    break
                
                old_count = len(self.configurations)
                new_count = self.load_configurations()
                
                if new_count != old_count:
                    self.log.info(f"Configuration changed: {old_count} -> {new_count}")
                    self.sync_workers()
                
            except Exception as e:
                self.log.error(f"Error in monitor loop: {e}", exc_info=True)
    
    def stop_all(self):
        """Stop all workers and monitoring."""
        self.log.info("Stopping all workers")
        
        self._stop_event.set()
        if self._monitor_thread:
            self._monitor_thread.join(timeout=5)
        
        worker_keys = list(self.workers.keys())
        for key in worker_keys:
            self._stop_worker(key)
        
        self.log.info("All workers stopped")
    
    def get_status(self) -> Dict[str, Any]:
        """Get orchestrator status."""
        return {
            "total_workers": len(self.workers),
            "active_configs": len(self.configurations),
            "workers": {
                key: {
                    "alive": worker.is_alive(),
                    "stats": worker.get_stats()
                }
                for key, worker in self.workers.items()
            }
        }
