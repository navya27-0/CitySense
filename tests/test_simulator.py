"""Integration and unit tests for BusSense-AI fleet simulator and telemetry pipeline (Hyderabad Region)."""

import pytest
from pathlib import Path
import pandas as pd
from fastapi.testclient import TestClient
from backend.main import app

client = TestClient(app)
GPS_DIR = Path(__file__).resolve().parent.parent / "data" / "gps"


def test_gps_trajectory_files():
    """Verify all 3 simulated GPS trajectory CSV files exist with valid columns in Hyderabad."""
    required_files = ["BUS_101.csv", "BUS_102.csv", "BUS_103.csv"]
    required_cols = {"timestamp", "latitude", "longitude", "speed", "heading"}

    for filename in required_files:
        csv_path = GPS_DIR / filename
        assert csv_path.exists(), f"Missing trajectory file: {filename}"
        df = pd.read_csv(csv_path)
        assert len(df) > 50, f"Trajectory file {filename} has insufficient waypoints ({len(df)})"
        assert required_cols.issubset(df.columns), f"Missing required columns in {filename}"
        
        # Verify Hyderabad coordinate bounds (17°N, 78°E)
        assert df["latitude"].between(17.0, 18.0).all(), f"Invalid latitude in {filename}"
        assert df["longitude"].between(78.0, 79.0).all(), f"Invalid longitude in {filename}"
        assert (df["speed"] >= 0.0).all(), f"Negative speed found in {filename}"


def test_post_telemetry_endpoint():
    """Test POST /api/telemetry ingestion, PostGIS update, and response contract."""
    payload = {
        "bus_id": "BUS_101",
        "route_id": "216",
        "latitude": 17.3916,
        "longitude": 78.4350,
        "speed": 34.5,
        "heading": 115.0,
        "status": "active",
    }

    response = client.post("/api/telemetry", json=payload)
    assert response.status_code == 200
    data = response.json()
    assert data["success"] is True
    assert data["bus_id"] == "BUS_101"
    assert data["is_simulated"] is True
    assert "SIMULATED TELEMETRY" in data["simulation_notice"]
    assert data["data"]["latitude"] == pytest.approx(17.3916, abs=1e-4)
    assert data["data"]["longitude"] == pytest.approx(78.4350, abs=1e-4)
    assert data["data"]["speed"] == 34.5
    assert data["data"]["heading"] == 115.0


def test_get_all_buses_endpoint():
    """Test GET /api/telemetry/buses returns list of active simulated fleet units."""
    # Ingest for BUS_102 and BUS_103 first
    for bus_id, r_id, lat, lon in [("BUS_102", "10", 17.4340, 78.5015), ("BUS_103", "49", 17.3688, 78.5247)]:
        client.post(
            "/api/telemetry",
            json={
                "bus_id": bus_id,
                "route_id": r_id,
                "latitude": lat,
                "longitude": lon,
                "speed": 26.0,
                "heading": 185.0,
            },
        )

    response = client.get("/api/telemetry/buses")
    assert response.status_code == 200
    buses = response.json()
    assert isinstance(buses, list)
    bus_ids = [b["bus_id"] for b in buses]
    assert "BUS_101" in bus_ids
    assert "BUS_102" in bus_ids
    assert "BUS_103" in bus_ids


def test_websocket_telemetry_broadcast():
    """Test WebSocket receives real-time telemetry updates when posted to API."""
    with client.websocket_connect("/ws") as websocket:
        # 1. Send client handshake
        websocket.send_text("client_ready")
        handshake_resp = websocket.receive_json()
        assert handshake_resp["type"] == "pong"

        # 2. Ingest telemetry via API
        payload = {
            "bus_id": "BUS_102",
            "route_id": "10",
            "latitude": 17.4265,
            "longitude": 78.4900,
            "speed": 31.2,
            "heading": 180.0,
            "status": "active",
        }
        api_resp = client.post("/api/telemetry", json=payload)
        assert api_resp.status_code == 200

        # 3. Read broadcasted WebSocket message
        ws_msg = websocket.receive_json()
        assert ws_msg["type"] == "bus_telemetry"
        assert ws_msg["is_simulated"] is True
        assert ws_msg["data"]["bus_id"] == "BUS_102"
        assert ws_msg["data"]["route_id"] == "10"
        assert ws_msg["data"]["latitude"] == pytest.approx(17.4265, abs=1e-4)
        assert ws_msg["data"]["longitude"] == pytest.approx(78.4900, abs=1e-4)
        assert ws_msg["data"]["speed"] == 31.2
