"""
A WebSocket server that runs in a separate thread within a strategy worker
to stream log messages directly to connected UI clients.
"""
import asyncio
import json
import logging
import threading
from typing import Set

import websockets
from websockets.server import WebSocketServerProtocol

logger = logging.getLogger(__name__)

class LogStreamServer:
    """
    Manages a WebSocket server in a background thread to stream logs.
    """
    def __init__(self, host: str = "0.0.0.0", port: int = 0):
        """
        Initializes the server.

        Args:
            host: The host to bind the server to.
            port: The port to bind to. If 0, an available port will be chosen.
        """
        self.host = host
        self.port = port
        self.server = None
        self.loop = None
        self.thread = None
        self.connected_clients: Set[WebSocketServerProtocol] = set()

    async def _handler(self, websocket: WebSocketServerProtocol):
        """The main WebSocket connection handler."""
        self.connected_clients.add(websocket)
        logger.info(f"Log stream client connected from {websocket.remote_address}")
        try:
            # Keep the connection open and wait for it to close
            await websocket.wait_closed()
        finally:
            self.connected_clients.remove(websocket)
            logger.info(f"Log stream client disconnected: {websocket.remote_address}")

    async def _run_server(self):
        """Starts the WebSocket server."""
        async with websockets.serve(self._handler, self.host, self.port) as server:
            self.server = server
            # If the initial port was 0, get the actual port that was bound
            if self.port == 0 and server.sockets:
                self.port = server.sockets[0].getsockname()[1]
            logger.info(f"Log stream server started on ws://{self.host}:{self.port}")
            await asyncio.Future()  # Run forever

    def start(self):
        """Starts the server in a background thread."""
        if self.thread is not None:
            logger.warning("Log stream server is already running.")
            return

        self.loop = asyncio.new_event_loop()
        self.thread = threading.Thread(target=self._start_loop, daemon=True)
        self.thread.start()

    def _start_loop(self):
        """Sets up and runs the asyncio event loop."""
        asyncio.set_event_loop(self.loop)
        try:
            self.loop.run_until_complete(self._run_server())
        except asyncio.CancelledError:
            logger.info("Log stream server loop cancelled.")

    def stop(self):
        """Stops the server and the background thread."""
        if self.loop and self.server:
            logger.info("Stopping log stream server...")
            self.loop.call_soon_threadsafe(self.server.close)
            self.loop.call_soon_threadsafe(self.loop.stop)
        if self.thread:
            self.thread.join(timeout=5)
            if self.thread.is_alive():
                logger.warning("Log stream server thread did not terminate gracefully.")
        self.thread = None
        self.loop = None
        self.server = None
        logger.info("Log stream server stopped.")

    def broadcast(self, message: dict):
        """
        Broadcasts a log message to all connected clients.

        Args:
            message: A JSON-serializable dictionary representing the log message.
        """
        if not self.connected_clients:
            return

        # Use call_soon_threadsafe because this method will be called
        # from the main application thread, not the server's event loop thread.
        if self.loop:
            self.loop.call_soon_threadsafe(
                asyncio.create_task, self._send_to_all(message)
            )

    async def _send_to_all(self, message: dict):
        """Asynchronously sends a message to all clients."""
        if not self.connected_clients:
            return
        
        # websockets.broadcast is efficient for sending to multiple clients
        try:
            websockets.broadcast(self.connected_clients, json.dumps(message))
        except Exception as e:
            logger.error(f"Error broadcasting log message: {e}")

    def get_address(self) -> (str, int):
        """Returns the host and port the server is running on."""
        return self.host, self.port
