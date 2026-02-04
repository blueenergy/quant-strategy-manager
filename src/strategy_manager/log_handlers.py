"""
Custom logging handlers for the strategy manager framework.
"""
import logging
from datetime import datetime

# To avoid circular import, use TYPE_CHECKING to import LogStreamServer for type hints
from typing import TYPE_CHECKING
if TYPE_CHECKING:
    from .log_stream_server import LogStreamServer


class SymbolLogFilter(logging.Filter):
    """
    过滤器：只允许包含特定股票代码的日志通过
    用于防止多个 Worker 的日志混合发送到同一个 WebSocket
    """
    def __init__(self, symbol: str):
        super().__init__()
        self.symbol = symbol
    
    def filter(self, record: logging.LogRecord) -> bool:
        """
        检查日志是否属于当前股票
        
        策略：
        1. 如果 logger name 包含股票代码，只匹配 logger name
        2. 如果消息内容包含股票代码，检查是否匹配
        3. 如果都不包含，允许通过（通用日志）
        """
        # 检查 logger name（如 scripts.single_stream_hidden_dragon.300347.SZ）
        if self.symbol in record.name:
            return True
        
        # 检查消息内容
        msg = record.getMessage()
        if self.symbol in msg:
            return True
        
        # 如果日志中包含其他股票代码，拒绝
        import re
        stock_codes = re.findall(r'\d{6}\.(SZ|SH|BJ)', msg)
        if stock_codes:
            # 有股票代码但不是当前股票，拒绝
            return False
        
        # 通用日志，允许通过
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
