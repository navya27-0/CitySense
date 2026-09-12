"""Unit and integration tests for /api/process-video asynchronous processing endpoints."""

import time
import pytest
from pathlib import Path
from fastapi.testclient import TestClient
from backend.main import app

client = TestClient(app)

PROJECT_ROOT = Path(__file__).resolve().parent.parent
SAMPLE_VIDEO_PATH = PROJECT_ROOT / "data" / "videos" / "sample_bus_feed.mp4"
SAMPLE_GPS_PATH = PROJECT_ROOT / "data" / "gps" / "BUS_101.csv"


def test_submit_process_video_endpoint_success():
    """Verify POST /api/process-video accepts video and mandatory GPS CSV and returns 202 with job_id."""
    assert SAMPLE_VIDEO_PATH.exists(), f"Sample video not found: {SAMPLE_VIDEO_PATH}"
    assert SAMPLE_GPS_PATH.exists(), f"Sample GPS log not found: {SAMPLE_GPS_PATH}"

    with open(SAMPLE_VIDEO_PATH, "rb") as vf, open(SAMPLE_GPS_PATH, "rb") as gf:
        files = {
            "video": ("sample_bus_feed.mp4", vf, "video/mp4"),
            "gps": ("BUS_101.csv", gf, "text/csv"),
        }
        data = {
            "bus_id": "BUS_101",
            "route_id": "216",
            "enable_ocr": "false",  # Fast execution for testing
        }
        response = client.post("/api/process-video", files=files, data=data)

    assert response.status_code == 202
    resp_data = response.json()
    assert "job_id" in resp_data
    assert resp_data["status"] in ["queued", "processing"]
    assert resp_data["bus_id"] == "BUS_101"
    assert "status_url" in resp_data
    assert resp_data["is_simulated"] is True

    job_id = resp_data["job_id"]

    # Poll status endpoint
    status_res = client.get(f"/api/process-video/{job_id}")
    assert status_res.status_code == 200
    status_data = status_res.json()
    assert status_data["job_id"] == job_id
    assert status_data["bus_id"] == "BUS_101"
    assert "status" in status_data
    assert "progress_pct" in status_data


def test_submit_process_video_without_gps_fails():
    """Verify POST /api/process-video rejects request when mandatory GPS is missing."""
    with open(SAMPLE_VIDEO_PATH, "rb") as vf:
        files = {
            "video": ("sample_bus_feed.mp4", vf, "video/mp4"),
        }
        data = {
            "bus_id": "BUS_101",
            "route_id": "216",
        }
        response = client.post("/api/process-video", files=files, data=data)

    assert response.status_code in [400, 422]


def test_get_invalid_job_id_returns_404():
    """Verify GET /api/process-video/{job_id} returns 404 for non-existent job."""
    res = client.get("/api/process-video/non_existent_job_999999")
    assert res.status_code == 404
    assert "not found" in res.json()["detail"].lower()


def test_list_all_jobs_endpoint():
    """Verify GET /api/process-video returns list of submitted jobs."""
    res = client.get("/api/process-video")
    assert res.status_code == 200
    data = res.json()
    assert isinstance(data, list)
