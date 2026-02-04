"""
Custom logging handlers for the strategy manager framework.
"""
import logging
import re
from datetime import datetime

# To avoid circular import, use TYPE_CHECKING to import LogStreamServer for type hints
from typing import TYPE_CHECKING
if TYPE_CHECKING:
    from .log_stream_server import LogStreamServer


class SymbolLogFilter(logging.Filter):
    """Filter logs by symbol and worker identity (user_id + strategy_key + symbol)."""
    
    def __init__(self, user_id: str, strategy_key: str, symbol: str):
        """
        Initialize filter with complete worker identity.
        
        Args:
            user_id: User identifier
            strategy_key: Strategy identifier  
            symbol: Stock symbol
        """
        super().__init__()
        self.user_id = user_id
        self.strategy_key = strategy_key
        self.symbol = symbol
    
    def filter(self, record: logging.LogRecord) -> bool:
        """
        Filter logic: allow logs that match this worker's symbol.
        
        1. If logger name contains this worker's symbol → allow
        2. If message contains this symbol → allow
        3. If contains other symbols → reject
        4. If no symbols at all → allow (system logs)
        """
        logger_name = record.name
        message = record.getMessage()
        
        # 检查 logger 名字中是否有当前 symbol
        if self.symbol in logger_name:
            return True
        
        # 检查消息内容中的股票代码
        import re
        stock_codes = re.findall(r'\d{6}\.(SZ|SH|BJ)', message)
        
        if stock_codes:
            # 消息包含股票代码
            if self.symbol in stock_codes:
                # 包含当前 symbol → 允许
                return True
            else:
                # 包含其他 symbol → 拒绝
                return False
        else:
            # 没有股票代码 → 允许（系统日志）
            return True


class WebSocketLogHandler(logging.Handler):
    """
    A logging handler that forwards records to a LogStreamServer for broadcasting.
    """
    def __init__(self, log_server: 'LogStreamServer'):
        """
        Initializes the handler.

        Args:
            log_server: An instance of LogStreamServer to which logs will be sent.
        """
        super().__init__()
        self.log_server = log_server

    def emit(self, record: logging.LogRecord):
        """
        Formats the log record and passes it to the server for broadcasting.
        """
        try:
            # Format the log record into a JSON-serializable dictionary
            log_message = {
                "timestamp": datetime.fromtimestamp(record.created).isoformat(),
                "level": record.levelname,
                "message": self.format(record),
                "logger_name": record.name,
                "module": record.module,
                "func_name": record.funcName,
                "line_no": record.lineno,
            }
            # Broadcast the message through the WebSocket server
            self.log_server.broadcast(log_message)
        except Exception:
            # If an error occurs (e.g., formatting), handle it gracefully
            self.handleError(record)
