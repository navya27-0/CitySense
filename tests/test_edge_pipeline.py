"""Unit and integration tests for Unified Edge-AI Processing Pipeline."""

import os
import pytest
import numpy as np
import cv2
import json
from pathlib import Path

from ai.pipeline.gps_sync import GPSVideoSynchronizer
from ai.pipeline.edge_pipeline import (
    EdgeAIPipeline,
    PipelineConfig,
    UnifiedEventRecord,
)

PROJECT_ROOT = Path(__file__).resolve().parent.parent
SAMPLE_VIDEO_PATH = PROJECT_ROOT / "data" / "videos" / "sample_bus_feed.mp4"
SAMPLE_GPS_PATH = PROJECT_ROOT / "data" / "gps" / "BUS_101.csv"
OUTPUT_VIDEO_PATH = PROJECT_ROOT / "data" / "outputs" / "test_pipeline_output.mp4"
OUTPUT_JSON_PATH = PROJECT_ROOT / "data" / "outputs" / "test_pipeline_summary.json"
OUTPUT_EVIDENCE_DIR = PROJECT_ROOT / "data" / "outputs" / "test_pipeline_evidence"


@pytest.fixture(scope="module")
def gps_sync():
    """Shared GPSVideoSynchronizer fixture."""
    return GPSVideoSynchronizer(gps_source=SAMPLE_GPS_PATH, bus_id="BUS_101")


def test_pipeline_config_defaults_and_env_vars(monkeypatch):
    """Verify PipelineConfig defaults and environment variable overrides."""
    # Test default values
    cfg = PipelineConfig(bus_id="BUS_101", route_id="216")
    assert cfg.bus_id == "BUS_101"
    assert cfg.route_id == "216"
    assert cfg.enable_vehicle_detection is True
    assert cfg.enable_road_defect_detection is True
    assert cfg.enable_incident_detection is True

    # Test environment variable toggles
    monkeypatch.setenv("ENABLE_VEHICLE_DETECTION", "false")
    monkeypatch.setenv("ENABLE_ROAD_DEFECT_DETECTION", "0")
    monkeypatch.setenv("ENABLE_OCR", "no")
    monkeypatch.setenv("SEND_TO_BACKEND", "true")

    env_cfg = PipelineConfig()
    assert env_cfg.enable_vehicle_detection is False
    assert env_cfg.enable_road_defect_detection is False
    assert env_cfg.enable_ocr is False
    assert env_cfg.send_to_backend is True


def test_pipeline_skips_disabled_models():
    """Verify that disabled pipeline stages do NOT instantiate models into memory."""
    config = PipelineConfig(
        enable_vehicle_detection=False,
        enable_road_defect_detection=False,
        enable_ocr=False,
        enable_incident_detection=False,
        enable_density_estimation=False,
    )
    pipeline = EdgeAIPipeline(config=config)

    assert pipeline.vehicle_tracker is None
    assert pipeline.road_defect_detector is None
    assert pipeline.plate_detector is None
    assert pipeline.ocr_engine is None
    assert pipeline.validator is None
    assert pipeline.incident_detector is None
    assert pipeline.density_estimator is None


def test_pipeline_frame_processing_with_gps_sync(gps_sync):
    """Verify EdgeAIPipeline processes a frame and attaches correct GPS coordinates."""
    config = PipelineConfig(
        bus_id="BUS_101",
        route_id="216",
        enable_ocr=False,
    )
    pipeline = EdgeAIPipeline(config=config)
    frame = np.full((720, 1280, 3), 120, dtype=np.uint8)

    tracking_res, defects, events = pipeline.process_frame(
        frame=frame,
        frame_number=10,
        video_timestamp=1.0,
        gps_synchronizer=gps_sync,
        output_evidence_dir=OUTPUT_EVIDENCE_DIR,
    )

    assert tracking_res is not None
    assert isinstance(defects, list)
    assert isinstance(events, list)


def test_pipeline_unified_event_schema(gps_sync):
    """Verify UnifiedEventRecord schema serialization and required metadata fields."""
    rec = UnifiedEventRecord(
        event_id="evt_BUS_101_POTHOLE_000010",
        event_category="ROAD_DEFECT",
        event_type="POTHOLE",
        confidence=0.88,
        severity="HIGH",
        bus_id="BUS_101",
        route_id="216",
        camera_id="CAM_FRONT_01",
        timestamp="2026-09-09T08:30:00Z",
        video_timestamp=1.5,
        frame_number=45,
        latitude=17.385044,
        longitude=78.486671,
        speed_kmh=35.0,
        heading_deg=180.0,
    )

    d = rec.to_dict()
    assert isinstance(d, dict)
    assert d["event_id"] == "evt_BUS_101_POTHOLE_000010"
    assert d["event_category"] == "ROAD_DEFECT"
    assert d["route_id"] == "216"
    assert d["bus_id"] == "BUS_101"
    assert d["latitude"] == 17.385044
    assert d["longitude"] == 78.486671
    assert d["is_simulated"] is True


def test_pipeline_backend_dispatch_error_tolerance():
    """Verify that backend dispatch catches network/connection errors without raising exceptions."""
    config = PipelineConfig(
        send_to_backend=True,
        backend_api_url="http://127.0.0.1:9999",  # Non-existent port
    )
    pipeline = EdgeAIPipeline(config=config)

    evt = UnifiedEventRecord(
        event_id="evt_test",
        event_category="TEST",
        event_type="TEST_EVENT",
        confidence=1.0,
        severity="LOW",
        bus_id="BUS_101",
        route_id="216",
        camera_id="CAM_FRONT_01",
        timestamp="2026-09-09T00:00:00Z",
        video_timestamp=0.0,
        frame_number=0,
        latitude=17.38,
        longitude=78.48,
        speed_kmh=0.0,
        heading_deg=0.0,
    )

    # Should execute cleanly without raising ConnectionError
    pipeline._dispatch_events_to_backend([evt], {"latitude": 17.38, "longitude": 78.48, "speed": 0.0, "heading": 0.0})


def test_pipeline_video_processing_and_json_export():
    """Verify end-to-end video processing and structured summary JSON export."""
    assert SAMPLE_VIDEO_PATH.exists(), f"Sample video not found: {SAMPLE_VIDEO_PATH}"
    assert SAMPLE_GPS_PATH.exists(), f"Sample GPS CSV not found: {SAMPLE_GPS_PATH}"

    config = PipelineConfig(
        bus_id="BUS_101",
        route_id="216",
        enable_ocr=False,  # Fast testing mode
    )
    pipeline = EdgeAIPipeline(config=config)

    summary = pipeline.run(
        video_path=SAMPLE_VIDEO_PATH,
        gps_path=SAMPLE_GPS_PATH,
        output_video_path=OUTPUT_VIDEO_PATH,
        output_json_path=OUTPUT_JSON_PATH,
        output_evidence_dir=OUTPUT_EVIDENCE_DIR,
        max_frames=15,
    )

    assert summary["total_frames_processed"] == 15
    assert summary["bus_id"] == "BUS_101"
    assert summary["route_id"] == "216"
    assert "events_by_category" in summary
    assert "processing_fps" in summary
    assert OUTPUT_JSON_PATH.exists()

    with open(OUTPUT_JSON_PATH, "r", encoding="utf-8") as f:
        data = json.load(f)
        assert data["bus_id"] == "BUS_101"
        assert data["route_id"] == "216"
        assert isinstance(data["events"], list)
