"""WebSocket communication package for real-time telemetry and event updates."""

from backend.websocket.manager import ConnectionManager

manager = ConnectionManager()

__all__ = ["manager", "ConnectionManager"]
