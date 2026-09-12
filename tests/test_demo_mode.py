"""Unit and integration tests for SIH Demo Mode and Video Studio endpoints."""

import os
import pytest
from pathlib import Path
from fastapi.testclient import TestClient

from backend.main import app
from scripts.seed_demo_dataset import seed_all_demo_data

client = TestClient(app)


def test_seed_demo_dataset_generates_files():
    """Verify seed_all_demo_data creates real visual evidence frames and outputs JSON."""
    records = seed_all_demo_data()
    assert len(records) >= 8

    # Verify evidence files exist
    for r in records:
        assert "event_id" in r
        assert "image_path" in r
        assert r["image_path"].startswith("/evidence/")
        
        # Check actual file on disk
        rel_path = r["image_path"].replace("/evidence/", "data/outputs/")
        assert Path(rel_path).exists(), f"Evidence file not found on disk: {rel_path}"


def test_analytics_time_range_filters_respond():
    """Verify analytics endpoints respond to 24h, 7d, 30d, all filters."""
    for tr in ["24h", "7d", "30d", "all"]:
        resp = client.get(f"/api/analytics/summary?time_range={tr}")
        assert resp.status_code == 200
        data = resp.json()
        assert "meta" in data
        assert data["meta"]["time_range"] == tr


def test_video_studio_elements_in_html():
    """Verify AI Video Studio components exist in the HTML dashboard."""
    resp = client.get("/")
    assert resp.status_code == 200
    assert 'data-view="view-studio"' in resp.text
    assert 'id="view-studio"' in resp.text
    assert "bench-clip-pothole" in resp.text
    assert "bench-clip-rash" in resp.text
    assert "bench-clip-plate" in resp.text
    assert "studio-video-player" in resp.text
    assert "studio-json-viewer" in resp.text
    assert "runStudioPipeline" in resp.text


def test_edge_metrics_endpoint():
    """Verify GET /api/edge-metrics returns bandwidth estimation figures."""
    resp = client.get("/api/edge-metrics")
    assert resp.status_code == 200
    data = resp.json()
    assert data["bandwidth_reduction_pct"] >= 95.0
    assert "disclaimer" in data
