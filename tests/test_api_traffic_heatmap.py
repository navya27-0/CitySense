"""Unit and integration tests for /api/traffic and /api/heatmap REST endpoints."""

import pytest
from fastapi.testclient import TestClient
from backend.main import app

client = TestClient(app)


def test_get_traffic_measurements_endpoint():
    """Verify GET /api/traffic returns paginated traffic measurements."""
    response = client.get("/api/traffic")
    assert response.status_code == 200
    data = response.json()
    assert "total" in data
    assert "measurements" in data
    assert isinstance(data["measurements"], list)
    assert data["is_simulated"] is True


def test_get_heatmap_endpoint():
    """Verify GET /api/heatmap returns weighted points for GIS layer."""
    response = client.get("/api/heatmap")
    assert response.status_code == 200
    data = response.json()
    assert "total_points" in data
    assert "points" in data
    assert isinstance(data["points"], list)
    assert len(data["points"]) > 0
    first_pt = data["points"][0]
    assert "latitude" in first_pt
    assert "longitude" in first_pt
    assert "weight" in first_pt
    assert "event_type" in first_pt
    assert data["is_simulated"] is True


def test_heatmap_category_filter():
    """Verify GET /api/heatmap supports category and min_weight filters."""
    response = client.get("/api/heatmap?category=DEFECTS&min_weight=1.5")
    assert response.status_code == 200
    data = response.json()
    assert "points" in data
    for pt in data["points"]:
        assert pt["weight"] >= 1.5
