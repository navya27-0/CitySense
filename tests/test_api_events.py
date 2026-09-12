"""Unit and integration tests for /api/events REST endpoints."""

import pytest
from fastapi.testclient import TestClient
from backend.main import app

client = TestClient(app)


def test_create_event_endpoint_success():
    """Verify POST /api/events creates and returns an event with 201 Created."""
    payload = {
        "bus_id": "BUS_101",
        "route_id": "216",
        "event_type": "POTHOLE",
        "event_category": "ROAD_DEFECT",
        "confidence": 0.89,
        "latitude": 17.385044,
        "longitude": 78.486671,
        "severity": "HIGH",
        "status": "detected",
        "image_path": "/evidence/road_defects/defect_BUS_101_POTHOLE_000010.jpg",
        "video_timestamp": 2.5,
        "details": {"bounding_box": [100, 150, 300, 350], "area": 40000},
    }

    response = client.post("/api/events", json=payload)
    assert response.status_code == 201
    data = response.json()
    assert data["bus_id"] == "BUS_101"
    assert data["event_type"] == "POTHOLE"
    assert data["severity"] == "HIGH"
    assert "event_id" in data
    assert data["is_simulated"] is True
    assert "prototype" in data["disclaimer"].lower()


def test_create_event_validation_failure():
    """Verify POST /api/events returns 422 for invalid/missing coordinates."""
    bad_payload = {
        "bus_id": "BUS_101",
        "event_type": "POTHOLE",
        # Missing latitude and longitude
    }
    response = client.post("/api/events", json=bad_payload)
    assert response.status_code == 422


def test_list_events_and_filtering():
    """Verify GET /api/events lists records and supports category/type filtering."""
    # Seed events
    client.post("/api/events", json={
        "bus_id": "BUS_101",
        "event_type": "POTHOLE",
        "event_category": "ROAD_DEFECT",
        "latitude": 17.3850,
        "longitude": 78.4866,
        "severity": "HIGH",
    })
    client.post("/api/events", json={
        "bus_id": "BUS_102",
        "event_type": "RASH_DRIVING",
        "event_category": "TRAFFIC_INCIDENT",
        "latitude": 17.3900,
        "longitude": 78.4800,
        "severity": "CRITICAL",
    })

    # List all
    res = client.get("/api/events")
    assert res.status_code == 200
    all_data = res.json()
    assert "total" in all_data
    assert "events" in all_data
    assert isinstance(all_data["events"], list)
    assert len(all_data["events"]) >= 2

    # Filter by event_type
    res_filtered = client.get("/api/events?event_type=RASH_DRIVING")
    assert res_filtered.status_code == 200
    filtered_data = res_filtered.json()
    for e in filtered_data["events"]:
        assert "RASH_DRIVING" in e["event_type"]


def test_get_event_by_id_found_and_not_found():
    """Verify GET /api/events/{event_id} retrieves event or returns 404."""
    # Create event
    create_res = client.post("/api/events", json={
        "bus_id": "BUS_103",
        "event_type": "WATERLOGGING",
        "latitude": 17.4000,
        "longitude": 78.5000,
        "severity": "MEDIUM",
    })
    evt_id = create_res.json()["event_id"]

    # Retrieve valid
    get_res = client.get(f"/api/events/{evt_id}")
    assert get_res.status_code == 200
    assert get_res.json()["event_id"] == evt_id
    assert get_res.json()["event_type"] == "WATERLOGGING"

    # Retrieve non-existent
    bad_res = client.get("/api/events/non_existent_event_999999")
    assert bad_res.status_code == 404
    assert "not found" in bad_res.json()["detail"].lower()
