"""WebSocket connection manager for broadcasting real-time urban sensing events and bus fleet telemetry."""

import logging
from typing import List, Dict, Optional, Set
from fastapi import WebSocket

logger = logging.getLogger("WebSocketManager")


class ConnectionManager:
    """Manages active WebSocket connections across dedicated event and bus telemetry channels."""

    def __init__(self):
        # Dedicated subscriber lists
        self.event_subscribers: Set[WebSocket] = set()
        self.bus_subscribers: Set[WebSocket] = set()
        self.general_subscribers: Set[WebSocket] = set()

    async def connect(self, websocket: WebSocket, channel: str = "general"):
        """Accepts a WebSocket connection and registers it with the specified channel."""
        await websocket.accept()
        if channel == "events":
            self.event_subscribers.add(websocket)
        elif channel == "buses":
            self.bus_subscribers.add(websocket)
        else:
            self.general_subscribers.add(websocket)
        logger.debug(f"Client connected to channel '{channel}'. Total subscribers: "
                     f"events={len(self.event_subscribers)}, buses={len(self.bus_subscribers)}, general={len(self.general_subscribers)}")

    def disconnect(self, websocket: WebSocket):
        """Unregisters a WebSocket from all channel subscriber sets."""
        self.event_subscribers.discard(websocket)
        self.bus_subscribers.discard(websocket)
        self.general_subscribers.discard(websocket)

    async def broadcast_events(self, data: dict):
        """Broadcasts an event payload to both /ws/events and general /ws subscribers."""
        targets = list(self.event_subscribers | self.general_subscribers)
        for connection in targets:
            try:
                await connection.send_json(data)
            except Exception:
                self.disconnect(connection)

    async def broadcast_buses(self, data: dict):
        """Broadcasts bus telemetry updates to both /ws/buses and general /ws subscribers."""
        targets = list(self.bus_subscribers | self.general_subscribers)
        for connection in targets:
            try:
                await connection.send_json(data)
            except Exception:
                self.disconnect(connection)

    async def broadcast_json(self, data: dict, channel: Optional[str] = None):
        """Broadcasts JSON payload to target channel or all active subscribers."""
        if channel == "events":
            targets = list(self.event_subscribers | self.general_subscribers)
        elif channel == "buses":
            targets = list(self.bus_subscribers | self.general_subscribers)
        else:
            targets = list(self.event_subscribers | self.bus_subscribers | self.general_subscribers)

        for connection in targets:
            try:
                await connection.send_json(data)
            except Exception:
                self.disconnect(connection)


# Global singleton connection manager
manager = ConnectionManager()
