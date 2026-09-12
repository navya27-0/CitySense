"""Tests for AI Video Studio upload resilience, GPS normalization, and job processing."""

import io
import time
from pathlib import Path
import pytest
from fastapi.testclient import TestClient

from backend.main import app
from ai.pipeline.gps_sync import GPSVideoSynchronizer

client = TestClient(app)
PROJECT_ROOT = Path(__file__).resolve().parent.parent


def test_gps_synchronizer_column_alias_normalization():
    """Verify GPSVideoSynchronizer accepts common column aliases like lat, lon, time."""
    csv_content = """time,lat,lng,spd,hdg
2026-09-10T14:30:00.000000+00:00,17.391600,78.435000,28.0,289.0
2026-09-10T14:30:01.000000+00:00,17.391995,78.433800,34.7,289.0
"""
    sync = GPSVideoSynchronizer(gps_source=io.StringIO(csv_content), bus_id="BUS_101")
    pos = sync.get_position(video_timestamp=0.5)
    assert pos["latitude"] is not None
    assert pos["longitude"] is not None
    assert round(pos["latitude"], 2) == 17.39
    assert round(pos["longitude"], 2) == 78.43


def test_upload_video_with_spaces_and_special_characters():
    """Verify uploading a video with spaces or special characters in filename is sanitized and accepted."""
    sample_video = PROJECT_ROOT / "data" / "videos" / "sample_bus_feed.mp4"
    sample_gps = PROJECT_ROOT / "data" / "gps" / "BUS_101.csv"

    assert sample_video.exists()
    assert sample_gps.exists()

    with open(sample_video, "rb") as vf, open(sample_gps, "rb") as gf:
        files = {
            "video": ("Special #1 Video (Front Camera).mp4", vf, "video/mp4"),
            "gps": ("GPS Track #101.csv", gf, "text/csv"),
        }
        data = {
            "bus_id": "BUS_101",
            "route_id": "216",
            "enable_ocr": "false",
        }
        resp = client.post("/api/process-video", files=files, data=data)

    assert resp.status_code == 202
    job_data = resp.json()
    assert "job_id" in job_data
    job_id = job_data["job_id"]

    # Verify status URL responds
    status_resp = client.get(f"/api/process-video/{job_id}")
    assert status_resp.status_code == 200


def test_frontend_studio_elements_and_methods():
    """Verify HTML and JavaScript contain dropzones, onStudioGpsFileChange, and setupStudioDropzones."""
    # Check index.html
    html_resp = client.get("/")
    assert html_resp.status_code == 200
    html_text = html_resp.text
    assert 'id="dropzone-video"' in html_text
    assert 'id="dropzone-gps"' in html_text
    assert 'id="studio-toggle-density"' in html_text
    assert 'onStudioGpsFileChange' in html_text

    # Check app.js
    js_path = PROJECT_ROOT / "frontend" / "js" / "app.js"
    assert js_path.exists()
    js_content = js_path.read_text(encoding="utf-8")
    assert "onStudioGpsFileChange" in js_content
    assert "setupStudioDropzones" in js_content
    assert "runClientStudioPipeline" in js_content
    assert "customVideoBlobUrl" in js_content
    assert "enable_density" in js_content


def test_studio_upload_and_pipeline_cleanup(tmp_path):
    """Verify submitted studio upload runs pipeline, exports annotated video and JSON, and cleans up raw upload."""
    import cv2
    import numpy as np

    # Generate a lightweight 5-frame video to verify full end-to-end pipeline execution fast
    fast_vid_path = tmp_path / "studio_fast_feed.mp4"
    w, h = 320, 240
    fourcc = cv2.VideoWriter_fourcc(*"mp4v")
    vw = cv2.VideoWriter(str(fast_vid_path), fourcc, 10.0, (w, h))
    for _ in range(5):
        frame = np.zeros((h, w, 3), dtype=np.uint8)
        vw.write(frame)
    vw.release()

    sample_gps = PROJECT_ROOT / "data" / "gps" / "BUS_101.csv"
    assert sample_gps.exists()

    with open(fast_vid_path, "rb") as vf, open(sample_gps, "rb") as gf:
        files = {
            "video": ("studio_fast_feed.mp4", vf, "video/mp4"),
            "gps": ("BUS_101.csv", gf, "text/csv"),
        }
        data = {
            "bus_id": "BUS_101",
            "route_id": "216",
            "enable_ocr": "false",
            "enable_density": "true",
        }
        resp = client.post("/api/process-video", files=files, data=data)

    assert resp.status_code == 202
    job_id = resp.json()["job_id"]

    # Poll until complete (timeout 45s)
    start_t = time.time()
    completed = False
    status_data = {}
    while time.time() - start_t < 45:
        st_res = client.get(f"/api/process-video/{job_id}")
        if st_res.status_code == 200:
            status_data = st_res.json()
            if status_data.get("status") == "completed":
                completed = True
                break
        time.sleep(0.5)

    assert completed, f"Job did not complete in time: {status_data}"
    assert status_data["status"] == "completed"
    assert status_data["progress_pct"] == 100.0
    assert status_data["output_video"] is not None

    # Check output video file exists
    out_video_path = PROJECT_ROOT / "data" / "outputs" / status_data["output_video"]
    assert out_video_path.exists(), f"Output video missing: {out_video_path}"

    # Check results endpoint
    res_resp = client.get(f"/api/process-video/{job_id}/results")
    assert res_resp.status_code == 200
    results = res_resp.json()
    assert "events" in results
    assert "unique_vehicles_counted" in results

    # Verify temporary raw upload in data/uploads was unlinked
    raw_upload_candidates = list((PROJECT_ROOT / "data" / "uploads").glob("*studio_fast_feed*"))
    assert len(raw_upload_candidates) == 0, f"Raw uploads not cleaned up: {raw_upload_candidates}"

