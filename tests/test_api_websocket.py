"""Unit and integration tests for WebSocket channels (/ws/events, /ws/buses, /ws)."""

import pytest
from fastapi.testclient import TestClient
from backend.main import app

client = TestClient(app)


def test_websocket_events_connection_and_heartbeat():
    """Verify WS /ws/events connects and responds to messages."""
    with client.websocket_connect("/ws/events") as ws:
        ws.send_text("ping_events")
        data = ws.receive_json()
        assert data["type"] == "pong"
        assert data["channel"] == "events"
        assert data["received"] == "ping_events"


def test_websocket_buses_connection_and_heartbeat():
    """Verify WS /ws/buses connects and responds to messages."""
    with client.websocket_connect("/ws/buses") as ws:
        ws.send_text("ping_buses")
        data = ws.receive_json()
        assert data["type"] == "pong"
        assert data["channel"] == "buses"
        assert data["received"] == "ping_buses"


def test_websocket_general_connection_and_heartbeat():
    """Verify WS /ws connects and responds to messages."""
    with client.websocket_connect("/ws") as ws:
        ws.send_text("ping_general")
        data = ws.receive_json()
        assert data["type"] == "pong"
        assert data["channel"] == "general"
        assert data["received"] == "ping_general"
