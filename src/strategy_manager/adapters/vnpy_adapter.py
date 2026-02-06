"""Vnpy engine adapter for strategy manager.

Wraps vnpy RealTimeEngine to conform to StrategyWorker interface.
"""

import logging
from typing import Dict, Any, Optional
import importlib
from pathlib import Path
from logging.handlers import RotatingFileHandler

from ..core.strategy_worker import StrategyWorker, WorkerState
from ..log_stream_server import LogStreamServer
from ..log_handlers import WebSocketLogHandler, SymbolLogFilter
from ..log_config import LogConfig


class VnpyWorkerAdapter(StrategyWorker):
    """
    Adapter to make vnpy engines compatible with StrategyWorker interface.
    
    Wraps any vnpy RealTimeEngine to provide unified worker interface.
    
    Example:
        worker = VnpyWorkerAdapter(
            symbol="002050.SZ",
            strategy_key="hidden_dragon",
            engine_class_path="scripts.single_stream_hidden_dragon.SingleStreamRealTimeEngine",
            params={...},
            user_id="user123"
        )
        worker.start()
    """
    
    def __init__(
        self,
        symbol: str,
        strategy_key: str,
        engine_class_path: str,
        params: Dict[str, Any],
        user_id: Optional[str] = None,
        securities_account_id: Optional[str] = None,
        broker: Optional[str] = None,
        account_id: Optional[str] = None,
        warmup_days: int = 90,
        **kwargs
    ):
        """
        Initialize vnpy worker adapter.
        
        Args:
            symbol: Stock symbol (e.g., "002050.SZ")
            strategy_key: Strategy identifier
            engine_class_path: Fully qualified path to vnpy engine class
                               e.g., "scripts.single_stream_hidden_dragon.SingleStreamRealTimeEngine"
            params: Strategy parameters dict
            user_id: User identifier
            securities_account_id: Securities account ID
            broker: Broker name
            account_id: Broker account ID
            warmup_days: Days of historical data for warmup
        """
        super().__init__(symbol=symbol, strategy_key=strategy_key, user_id=user_id)
        
        self.params = params
        self.warmup_days = warmup_days
        
        # Import vnpy engine class dynamically
        module_path, class_name = engine_class_path.rsplit(".", 1)
        module = importlib.import_module(module_path)
        engine_class = getattr(module, class_name)
        
        # Create vnpy engine instance
        self.engine = engine_class(
            symbol=symbol,
            securities_account_id=securities_account_id,
            broker=broker,
            account_id=account_id,
            user_id=user_id,
            warmup_days=warmup_days,
            strategy_params=params
        )
        
        # Setup logging with flexible backend (local file, ELK, Loki, etc.)
        # 🎯 Logger name：包含完整标识（user_id + strategy_key + symbol）确保唯一
        self.log = logging.getLogger(f"scripts.{user_id or 'unknown'}_{strategy_key}_{symbol}")
        self.log.propagate = False  # Avoid duplicate logs
        
        # Determine log file path for file backend
        current_file = Path(__file__)
        vnpy_root = None
        
        # Search upwards for vnpy-live-trading directory
        for parent in [current_file] + list(current_file.parents):
            vnpy_dir = parent.parent / "vnpy-live-trading"
            if vnpy_dir.exists() and vnpy_dir.is_dir():
                vnpy_root = vnpy_dir
                break
        
        # Fallback: use current directory's parent
        if not vnpy_root:
            vnpy_root = current_file.parent.parent.parent.parent / "vnpy-live-trading"
        
        log_dir = vnpy_root / "logs" / "workers"
        log_filename = f"{user_id or 'unknown'}_{symbol}_{strategy_key}.log"
        self.log_file = log_dir / log_filename
        
        if not self.log.handlers:
            fmt = logging.Formatter("%(asctime)s %(levelname)s %(name)s: %(message)s")
            
            # Setup file or remote backend based on configuration (do this FIRST)
            try:
                # Create logger with LogConfig (returns logger with handlers)
                config_logger = LogConfig.setup_logger(
                    logger_name=self.log.name,
                    log_file=str(self.log_file)
                )
                
                # Get the backend handler from config logger
                backend_handlers = [h for h in config_logger.handlers if not isinstance(h, logging.StreamHandler)]
                
                if backend_handlers:
                    # Use the configured handler(s)
                    for backend_handler in backend_handlers:
                        # Add filter to backend handler
                        symbol_filter = SymbolLogFilter(
                            user_id=user_id or 'unknown',
                            strategy_key=strategy_key,
                            symbol=symbol
                        )
                        backend_handler.addFilter(symbol_filter)
                        self.log.addHandler(backend_handler)
                else:
                    # Fallback to file handler if config fails
                    file_handler = RotatingFileHandler(
                        self.log_file,
                        maxBytes=10*1024*1024,
                        backupCount=5,
                        encoding='utf-8'
                    )
                    file_handler.setFormatter(fmt)
                    
                    symbol_filter = SymbolLogFilter(
                        user_id=user_id or 'unknown',
                        strategy_key=strategy_key,
                        symbol=symbol
                    )
                    file_handler.addFilter(symbol_filter)
                    self.log.addHandler(file_handler)
                
                self.log.info(f"Logging configured")
            except Exception as e:
                self.log.warning(f"Failed to setup logging backend: {e}")
                # Ensure at least file handler exists
                try:
                    file_handler = RotatingFileHandler(
                        self.log_file,
                        maxBytes=10*1024*1024,
                        backupCount=5,
                        encoding='utf-8'
                    )
                    file_handler.setFormatter(fmt)
                    self.log.addHandler(file_handler)
                except Exception as fallback_error:
                    self.log.error(f"Fallback file handler also failed: {fallback_error}")
            
            # Console handler (add AFTER LogConfig to avoid interfering)
            console_handler = logging.StreamHandler()
            console_handler.setFormatter(fmt)
            self.log.addHandler(console_handler)
            
            # WebSocket log streaming (dynamic port) for real-time monitoring
            try:
                self._log_server = LogStreamServer(host="0.0.0.0", port=0, symbol=symbol)
                self._log_server.start()
                
                ws_handler = WebSocketLogHandler(self._log_server)
                ws_handler.setFormatter(fmt)
                
                # 🎯 Add symbol filter to WebSocket handler
                symbol_filter = SymbolLogFilter(
                    user_id=user_id or 'unknown',
                    strategy_key=strategy_key,
                    symbol=symbol
                )
                ws_handler.addFilter(symbol_filter)
                
                self.log.addHandler(ws_handler)
                self.log.info(f"Log stream available at {self.get_log_stream_url()}")
            except Exception as e:
                self.log.warning(f"Failed to start log stream server: {e}")
                self._log_server = None
        
        self.log.setLevel(logging.INFO)
        
        # 🔗 Link vnpy engine logger to Worker handlers
        if hasattr(self.engine, 'logger') and isinstance(self.engine.logger, logging.Logger):
            vnpy_logger = self.engine.logger
            
            for handler in self.log.handlers:
                if handler not in vnpy_logger.handlers:
                    if isinstance(handler, RotatingFileHandler):
                        # Add filter to file handler
                        if not any(isinstance(f, SymbolLogFilter) for f in handler.filters):
                            symbol_filter = SymbolLogFilter(
                                user_id=user_id or 'unknown',
                                strategy_key=strategy_key,
                                symbol=symbol
                            )
                            handler.addFilter(symbol_filter)
                        vnpy_logger.addHandler(handler)
                        self.log.info(f"Added file handler to vnpy logger for {symbol}")
                        
                    elif isinstance(handler, WebSocketLogHandler):
                        # Create new WebSocket handler with filter
                        vnpy_ws_handler = WebSocketLogHandler(handler.log_server)
                        vnpy_ws_handler.setFormatter(handler.formatter if handler.formatter else fmt)
                        
                        symbol_filter = SymbolLogFilter(
                            user_id=user_id or 'unknown',
                            strategy_key=strategy_key,
                            symbol=symbol
                        )
                        vnpy_ws_handler.addFilter(symbol_filter)
                        
                        vnpy_logger.addHandler(vnpy_ws_handler)
                        self.log.info(f"Added WebSocket handler to vnpy logger for {symbol}")
            
            vnpy_logger.setLevel(self.log.level)
            self.log.info(f"✓ Linked vnpy engine logger to Worker handlers ({len(self.log.handlers)} handlers)")
        else:
            self.log.warning("⚠️ vnpy engine does not have a logger attribute")
        
        self.bars_processed = 0
    
    def run(self):
        """Main thread loop - start vnpy engine."""
        try:
            self._state = WorkerState.RUNNING
            self.log.info(f"Starting vnpy engine for {self.symbol}")
            
            # Start vnpy engine with polling
            self.engine.start_with_polling()
            
            # Keep running until stop requested
            while not self._stop_event.is_set():
                self._stop_event.wait(timeout=1)
                
        except Exception as e:
            self._state = WorkerState.ERROR
            self.log.error(f"Error in vnpy engine: {e}", exc_info=True)
        finally:
            self._state = WorkerState.STOPPED
            self.engine.stop()
    
    def stop(self, save_state: bool = True):
        """Stop the vnpy engine."""
        self.log.info(f"Stopping vnpy engine for {self.symbol}")
        self._stop_event.set()
        
        if save_state:
            self.save_state()
        
        self.engine.stop()
        
        # Stop log stream server
        if self._log_server:
            try:
                self._log_server.stop()
            except Exception as e:
                self.log.warning(f"Error stopping log stream server: {e}")
        
        self._state = WorkerState.STOPPED
    
    def get_stats(self) -> Dict[str, Any]:
        """Get worker statistics."""
        stats = {
            "symbol": self.symbol,
            "strategy": self.strategy_key,
            "engine": "vnpy",
            "state": self._state.value,
            "bars_processed": self.bars_processed,
        }
        
        # Get strategy-specific stats if available
        if hasattr(self.engine, 'strategy') and self.engine.strategy:
            strategy = self.engine.strategy
            stats.update({
                "position": getattr(strategy, 'pos', 0),
                "entry_price": getattr(strategy, 'entry_price', 0.0),
                "boom_day": getattr(strategy, 'boom_day', -1),
                "callback_days": getattr(strategy, 'callback_days', -1),
            })
        
        return stats
    
    def get_position(self) -> int:
        """Get current position size."""
        if hasattr(self.engine, 'strategy') and self.engine.strategy:
            return getattr(self.engine.strategy, 'pos', 0)
        return 0
    
    def save_state(self) -> bool:
        """Persist worker state."""
        try:
            if hasattr(self.engine, 'strategy') and self.engine.strategy:
                return self.engine.strategy.save_state()
            return False
        except Exception as e:
            self.log.error(f"Failed to save state: {e}")
            return False
    
    def load_state(self) -> bool:
        """Restore worker state."""
        try:
            if hasattr(self.engine, 'strategy') and self.engine.strategy:
                return self.engine.strategy.load_state()
            return False
        except Exception as e:
            self.log.error(f"Failed to load state: {e}")
            return False


def create_vnpy_worker(config: Dict[str, Any]) -> VnpyWorkerAdapter:
    """
    Factory function to create vnpy workers.
    
    Args:
        config: Worker configuration dict with keys:
            - symbol: Stock symbol
            - strategy_key: Strategy identifier
            - engine_class_path: Path to vnpy engine class
            - params: Strategy parameters
            - user_id: User identifier
            - securities_account_id, broker, account_id: Account info
    
    Returns:
        VnpyWorkerAdapter instance
    """
    return VnpyWorkerAdapter(
        symbol=config['symbol'],
        strategy_key=config['strategy_key'],
        engine_class_path=config['engine_class_path'],
        params=config.get('params', {}),
        user_id=config.get('user_id'),
        securities_account_id=config.get('securities_account_id'),
        broker=config.get('broker'),
        account_id=config.get('account_id'),
        warmup_days=config.get('warmup_days', 90),
    )
