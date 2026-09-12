"""Unit and integration tests for /api/buses and /api/telemetry REST endpoints."""

import pytest
from fastapi.testclient import TestClient
from backend.main import app

client = TestClient(app)


def test_post_telemetry_and_get_buses():
    """Verify POST /api/telemetry registers bus and updates GET /api/buses."""
    payload = {
        "bus_id": "BUS_201",
        "route_id": "216",
        "latitude": 17.385044,
        "longitude": 78.486671,
        "speed": 34.2,
        "heading": 180.0,
        "status": "active",
    }

    # Post telemetry
    post_res = client.post("/api/telemetry", json=payload)
    assert post_res.status_code == 200
    telemetry_data = post_res.json()
    assert telemetry_data["success"] is True
    assert telemetry_data["bus_id"] == "BUS_201"

    # Get all buses
    list_res = client.get("/api/buses")
    assert list_res.status_code == 200
    buses = list_res.json()
    assert isinstance(buses, list)
    bus_ids = [b["bus_id"] for b in buses]
    assert "BUS_201" in bus_ids


def test_get_bus_by_id_and_404():
    """Verify GET /api/buses/{bus_id} returns bus detail or 404."""
    # Register bus
    client.post("/api/telemetry", json={
        "bus_id": "BUS_202",
        "route_id": "100",
        "latitude": 17.4100,
        "longitude": 78.4500,
        "speed": 20.0,
        "heading": 90.0,
        "status": "active",
    })

    # Retrieve valid bus
    res = client.get("/api/buses/BUS_202")
    assert res.status_code == 200
    data = res.json()
    assert data["bus_id"] == "BUS_202"
    assert data["route_id"] == "100"
    assert "active_events_count" in data
    assert "recent_events" in data

    # Retrieve non-existent bus
    bad_res = client.get("/api/buses/NON_EXISTENT_BUS_99999")
    assert bad_res.status_code == 404
    assert "not found" in bad_res.json()["detail"].lower()
