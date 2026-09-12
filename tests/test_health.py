"""Unit tests for health check endpoints."""

from fastapi.testclient import TestClient
from backend.main import app

client = TestClient(app)


def test_root_endpoint():
    """Verify root endpoint returns 200 and /api-info returns project metadata."""
    response = client.get("/")
    assert response.status_code == 200

    api_info_res = client.get("/api-info")
    assert api_info_res.status_code == 200
    data = api_info_res.json()
    assert data["project"] == "BusSense-AI"
    assert data["status"] == "online"
    assert "health_url" in data


def test_health_endpoints_structure():
    """Verify /health and /api/health return structured database diagnostics."""
    for endpoint in ["/health", "/api/health"]:
        response = client.get(endpoint)
        # Should return 200 (if DB is up) or 503 (if DB is disconnected)
        assert response.status_code in [200, 503]
        data = response.json()
        assert "status" in data
        assert "database" in data
        assert "postgis" in data
        assert "app_name" in data
