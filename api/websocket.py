"""
WebSocket Connection Manager for real-time frontend streaming.
"""

import json
import logging
from typing import Any, Dict, List
from fastapi import WebSocket

logger = logging.getLogger(__name__)


class ConnectionManager:
    """Manages active WebSocket client connections and broadcasts messages."""

    def __init__(self):
        self.active_connections: List[WebSocket] = []

    async def connect(self, websocket: WebSocket):
        await websocket.accept()
        self.active_connections.append(websocket)
        logger.info(f"WebSocket client connected. Total clients: {len(self.active_connections)}")

    def disconnect(self, websocket: WebSocket):
        if websocket in self.active_connections:
            self.active_connections.remove(websocket)
            logger.info(f"WebSocket client disconnected. Remaining clients: {len(self.active_connections)}")

    async def broadcast(self, message: Dict[str, Any]):
        """Broadcasts a JSON-serializable message payload to all connected clients."""
        text = json.dumps(message)
        disconnected = []
        for connection in self.active_connections:
            try:
                await connection.send_text(text)
            except Exception as err:
                logger.warning(f"Error sending message to client: {err}")
                disconnected.append(connection)

        for dead_conn in disconnected:
            self.disconnect(dead_conn)


ws_manager = ConnectionManager()
