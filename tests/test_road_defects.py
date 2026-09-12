"""Unit and integration tests for road defect detection module."""

import pytest
import numpy as np
import cv2
import json
from pathlib import Path

from ai.pipeline.gps_sync import GPSVideoSynchronizer
from ai.road_defect_detection import (
    RoadDefectDetector,
    RoadDefectType,
    RoadDefectSeverity,
    RoadDefectDetection,
    RoadDefectEvent,
)

PROJECT_ROOT = Path(__file__).resolve().parent.parent
SAMPLE_VIDEO_PATH = PROJECT_ROOT / "data" / "videos" / "road_test.mp4"
SAMPLE_GPS_PATH = PROJECT_ROOT / "data" / "gps" / "BUS_101.csv"
OUTPUT_VIDEO_PATH = PROJECT_ROOT / "data" / "outputs" / "test_defect_output.mp4"
OUTPUT_JSON_PATH = PROJECT_ROOT / "data" / "outputs" / "test_defect_events.json"
TEST_EVENTS_DIR = PROJECT_ROOT / "data" / "outputs" / "test_events"


@pytest.fixture(scope="module")
def gps_sync():
    """Shared GPSVideoSynchronizer fixture."""
    return GPSVideoSynchronizer(gps_source=SAMPLE_GPS_PATH, bus_id="BUS_101")


@pytest.fixture(scope="module")
def detector():
    """Shared RoadDefectDetector in demo fallback mode."""
    return RoadDefectDetector(
        model_path="models/road_defects/non_existent_weights.pt",
        conf_threshold=0.25,
        bus_id="BUS_101",
        evidence_dir=TEST_EVENTS_DIR,
        save_evidence=True,
        enable_demo_fallback=True,
        device="cpu",
    )


def test_detector_initialization_demo_mode(detector):
    """Verify detector initializes in demo fallback mode when custom weights are absent."""
    assert detector.custom_model_loaded is False
    assert "DEMO" in detector.model_source_description
    assert detector.bus_id == "BUS_101"


def test_subtype_normalization():
    """Verify raw model class strings are normalized to standard RoadDefectType enum values."""
    det = RoadDefectDetector(enable_demo_fallback=False)

    assert det._normalize_subtype("pothole") == RoadDefectType.POTHOLE.value
    assert det._normalize_subtype("potholes") == RoadDefectType.POTHOLE.value
    assert det._normalize_subtype("d00") == RoadDefectType.POTHOLE.value
    assert det._normalize_subtype("alligator_crack") == RoadDefectType.DAMAGED_ROAD.value
    assert det._normalize_subtype("d20") == RoadDefectType.DAMAGED_ROAD.value
    assert det._normalize_subtype("divider") == RoadDefectType.MISSING_DIVIDER.value
    assert det._normalize_subtype("faded_crosswalk") == RoadDefectType.MISSING_ZEBRA_CROSSING.value
    assert det._normalize_subtype("damaged_sign") == RoadDefectType.DAMAGED_SIGNBOARD.value
    assert det._normalize_subtype("standing_water") == RoadDefectType.WATERLOGGING.value


def test_severity_calculation(detector):
    """Verify severity calculations based on defect type and bounding box area."""
    w, h = 1920, 1080
    frame_area = w * h

    # Large waterlogging / missing divider -> CRITICAL
    large_water_area = int(frame_area * 0.08)
    assert detector.calculate_severity(RoadDefectType.WATERLOGGING.value, large_water_area, 0.90, w, h) == "critical"

    # Large pothole -> HIGH
    large_pothole_area = int(frame_area * 0.05)
    assert detector.calculate_severity(RoadDefectType.POTHOLE.value, large_pothole_area, 0.85, w, h) == "high"

    # Small pothole -> LOW
    small_pothole_area = int(frame_area * 0.005)
    assert detector.calculate_severity(RoadDefectType.POTHOLE.value, small_pothole_area, 0.45, w, h) == "low"


def test_detect_frame_demo_mode(detector):
    """Verify detect_frame generates valid detections in demo fallback mode."""
    frame = np.full((1080, 1920, 3), (60, 60, 65), dtype=np.uint8)
    dets = detector.detect_frame(frame, frame_number=25, video_timestamp=1.0)

    assert isinstance(dets, list)
    if len(dets) > 0:
        first = dets[0]
        assert isinstance(first, RoadDefectDetection)
        assert first.defect_type in [t.value for t in RoadDefectType]
        assert len(first.bounding_box) == 4
        assert first.area > 0


def test_create_urban_event_with_gps(detector, gps_sync):
    """Verify create_urban_event attaches GPS coordinates and enforces deduplication."""
    frame = np.full((1080, 1920, 3), (60, 60, 65), dtype=np.uint8)
    det = RoadDefectDetection(
        defect_type=RoadDefectType.POTHOLE.value,
        confidence=0.88,
        bounding_box=[800, 600, 1100, 850],
        area=75000,
        severity="high",
        centroid=(950, 725),
    )

    detector.last_event_timestamps.clear()

    # 1. First trigger creates event
    ev = detector.create_urban_event(
        detection=det,
        frame_number=30,
        video_timestamp=1.0,
        frame=frame,
        gps_synchronizer=gps_sync,
    )

    assert ev is not None
    assert isinstance(ev, RoadDefectEvent)
    assert ev.event_type == "POTHOLE"
    assert ev.latitude > 0.0
    assert ev.longitude > 0.0
    assert ev.severity == "high"
    assert "roaddefect_BUS101_POTHOLE_000030.jpg" in ev.image_path

    # 2. Duplicate trigger within dedup window (0.5s later) must be skipped (returns None)
    dup_ev = detector.create_urban_event(
        detection=det,
        frame_number=45,
        video_timestamp=1.5,
        frame=frame,
        gps_synchronizer=gps_sync,
    )
    assert dup_ev is None


def test_evidence_image_export(detector):
    """Verify evidence images are saved in data/outputs/events/ matching naming convention."""
    frame = np.full((1080, 1920, 3), (60, 60, 65), dtype=np.uint8)
    det = RoadDefectDetection(
        defect_type=RoadDefectType.POTHOLE.value,
        confidence=0.91,
        bounding_box=[500, 500, 700, 700],
        area=40000,
        severity="medium",
        centroid=(600, 600),
    )

    img_path = detector.save_evidence_image(
        frame=frame,
        detection=det,
        bus_id="BUS_101",
        frame_number=123,
        timestamp_str="2026-09-09T14:30:00Z",
        gps_coords=(17.3850, 78.4867),
    )

    saved_p = Path(img_path)
    assert saved_p.exists()
    assert saved_p.name == "roaddefect_BUS101_POTHOLE_000123.jpg"

    # Verify saved image can be opened and is valid
    read_img = cv2.imread(str(saved_p))
    assert read_img is not None
    assert read_img.shape == frame.shape


def test_video_processing_and_json_export(detector, gps_sync):
    """Verify full video processing and structured JSON events export."""
    # Use road_test.mp4 or sample video
    vid_p = SAMPLE_VIDEO_PATH if SAMPLE_VIDEO_PATH.exists() else PROJECT_ROOT / "data" / "videos" / "sample_bus_feed.mp4"

    summary = detector.process_video(
        video_path=vid_p,
        gps_synchronizer=gps_sync,
        output_video_path=OUTPUT_VIDEO_PATH,
        output_json_path=OUTPUT_JSON_PATH,
        max_frames=30,
        show_progress=False,
    )

    assert "metadata" in summary
    assert "aggregate_statistics" in summary
    assert "events" in summary
    assert summary["metadata"]["is_simulated"] is True

    assert OUTPUT_JSON_PATH.exists()
    with open(OUTPUT_JSON_PATH, "r", encoding="utf-8") as f:
        data = json.load(f)
        assert "events" in data
        assert "events_by_subtype" in data["aggregate_statistics"]
