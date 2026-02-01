"""
Custom logging handlers for the strategy manager framework.
"""
import logging
from datetime import datetime

# To avoid circular import, use TYPE_CHECKING to import LogStreamServer for type hints
from typing import TYPE_CHECKING
if TYPE_CHECKING:
    from .log_stream_server import LogStreamServer


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
