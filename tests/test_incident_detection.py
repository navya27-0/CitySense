"""Unit and integration tests for Incident Detection Engine."""

import pytest
import numpy as np
import cv2
import json
from pathlib import Path
from collections import deque

from ai.pipeline.gps_sync import GPSVideoSynchronizer
from ai.incident_detection.config import (
    IncidentConfig,
    IncidentRecord,
    IncidentType,
    IncidentSeverity,
    IncidentStatus,
    DISCLAIMER_TEXT,
)
from ai.incident_detection.rules.base import BaseIncidentRule, IncidentCandidate
from ai.incident_detection.rules.rash_driving import RashDrivingRule
from ai.incident_detection.rules.hit_and_run import HitAndRunRule
from ai.incident_detection.detector import IncidentDetector

PROJECT_ROOT = Path(__file__).resolve().parent.parent
SAMPLE_VIDEO_PATH = PROJECT_ROOT / "data" / "videos" / "sample_bus_feed.mp4"
SAMPLE_GPS_PATH = PROJECT_ROOT / "data" / "gps" / "BUS_101.csv"
OUTPUT_VIDEO_PATH = PROJECT_ROOT / "data" / "outputs" / "test_incident_output.mp4"
OUTPUT_JSON_PATH = PROJECT_ROOT / "data" / "outputs" / "test_incident_records.json"
OUTPUT_INCIDENTS_DIR = PROJECT_ROOT / "data" / "outputs" / "test_incidents"


@pytest.fixture(scope="module")
def gps_sync():
    """Shared GPSVideoSynchronizer fixture."""
    return GPSVideoSynchronizer(gps_source=SAMPLE_GPS_PATH, bus_id="BUS_101")


@pytest.fixture(scope="module")
def incident_detector():
    """Lightweight IncidentDetector fixture for fast unit testing (no OCR)."""
    return IncidentDetector(
        vehicle_model="yolov8n.pt",
        conf_threshold=0.25,
        bus_id="BUS_101",
        device="cpu",
        enable_ocr=False,
    )


# ==============================================================================
# 1. CONFIGURATION & SCHEMA TESTS
# ==============================================================================

def test_incident_config_defaults():
    """Verify default heuristic thresholds are populated correctly."""
    config = IncidentConfig()
    assert config.min_track_history_frames == 8
    assert config.cooldown_frames_per_track == 60
    assert config.rash_speed_threshold_px_s == 520.0
    assert config.rash_avg_speed_threshold_px_s == 350.0
    assert config.rash_min_zero_crossings == 2
    assert config.hit_and_run_proximity_distance_px == 35.0
    assert config.hit_and_run_speed_surge_ratio == 1.80
    assert config.hit_and_run_min_event_confidence == 0.75


def test_incident_record_schema_and_defaults():
    """Verify IncidentRecord default values, required fields, and dictionary serialization."""
    rec = IncidentRecord(
        incident_id="inc_BUS_101_rash_driving_0001_000100",
        incident_type=IncidentType.RASH_DRIVING.value,
        vehicle_tracking_id=1,
        registration_number="TS09EA1234",
        registration_confidence=0.88,
        event_confidence=0.82,
        bus_id="BUS_101",
        timestamp="2026-09-09T08:30:00Z",
        latitude=17.385044,
        longitude=78.486671,
        severity=IncidentSeverity.HIGH.value,
        speed_kmh=42.5,
        heading_deg=180.0,
    )

    assert rec.status == "NEW"
    assert rec.disclaimer == DISCLAIMER_TEXT
    assert "prototype heuristic estimation" in rec.disclaimer

    d = rec.to_dict()
    assert isinstance(d, dict)
    assert d["incident_id"] == "inc_BUS_101_rash_driving_0001_000100"
    assert d["status"] == "NEW"
    assert d["severity"] == "HIGH"
    assert d["latitude"] == 17.385044
    assert d["longitude"] == 78.486671


# ==============================================================================
# 2. RASH DRIVING HEURISTIC RULE TESTS
# ==============================================================================

def test_rash_driving_rule_triggers_on_erratic_trajectory():
    """Verify RashDrivingRule triggers on severe lateral weaving and sudden acceleration."""
    rule = RashDrivingRule()
    config = IncidentConfig()

    # Synthetic erratic trajectory: rapid slalom weaving at high speed across 16 frames
    centroids = [
        (100, 100), (160, 140), (100, 180), (170, 220),
        (90, 260),  (180, 300), (80, 340),  (190, 380),
        (70, 420),  (200, 460), (60, 500),  (210, 540),
        (50, 580),  (220, 620), (50, 660),  (230, 700),
    ]
    timestamps = [i * 0.033 for i in range(len(centroids))]

    track_state = {
        "centroids": centroids,
        "timestamps": timestamps,
        "boxes": [[c[0] - 20, c[1] - 20, c[0] + 20, c[1] + 20] for c in centroids],
        "velocities": [400.0] * len(centroids),
        "vehicle_type": "car",
        "last_seen_frame": len(centroids),
    }

    frame_meta = {"width": 1280, "height": 720, "fps": 30.0, "frame_number": 16}
    candidate = rule.evaluate(
        track_id=1,
        track_state=track_state,
        all_tracks_state={1: track_state},
        frame_meta=frame_meta,
        config=config,
    )

    assert candidate is not None
    assert candidate.incident_type == IncidentType.RASH_DRIVING
    assert candidate.event_confidence >= 0.70
    assert candidate.severity in (IncidentSeverity.MEDIUM, IncidentSeverity.HIGH)
    assert "triggered_indicators" in candidate.details


def test_rash_driving_rule_ignores_smooth_linear_trajectory():
    """Verify RashDrivingRule does not trigger on normal, steady straight-line driving."""
    rule = RashDrivingRule()
    config = IncidentConfig()

    # Steady forward motion at normal speed (zero lateral deviation)
    centroids = [(200, 100 + i * 15) for i in range(16)]
    timestamps = [i * 0.033 for i in range(16)]

    track_state = {
        "centroids": centroids,
        "timestamps": timestamps,
        "boxes": [[c[0] - 20, c[1] - 20, c[0] + 20, c[1] + 20] for c in centroids],
        "velocities": [150.0] * len(centroids),
        "vehicle_type": "car",
        "last_seen_frame": len(centroids),
    }

    frame_meta = {"width": 1280, "height": 720, "fps": 30.0, "frame_number": 16}
    candidate = rule.evaluate(
        track_id=1,
        track_state=track_state,
        all_tracks_state={1: track_state},
        frame_meta=frame_meta,
        config=config,
    )

    assert candidate is None


# ==============================================================================
# 3. SUSPECTED HIT AND RUN HEURISTIC RULE TESTS
# ==============================================================================

def test_hit_and_run_rule_triggers_on_collision_and_escape():
    """Verify HitAndRunRule detects close proximity encounter followed by rapid escape."""
    rule = HitAndRunRule()
    config = IncidentConfig()

    # Vehicle 1 (suspect): approaches at low speed (100 px/s), collides near vehicle 2 at (510, 325), then surges to 600 px/s toward frame boundary
    v1_centroids = [
        (480, 320), (490, 321), (498, 322),  # slow approach (10 px / 0.05s = 200 px/s)
        (505, 323), (508, 324),              # collision / encounter point with overlap at (510, 325)
        (580, 290), (700, 240), (860, 180), (1040, 100), (1220, 30), # rapid speed surge & boundary escape
    ]
    v1_timestamps = [i * 0.05 for i in range(len(v1_centroids))]
    v1_boxes = [[c[0] - 30, c[1] - 30, c[0] + 30, c[1] + 30] for c in v1_centroids]

    # Vehicle 2 (victim): stationary at (510, 325)
    v2_box = [480, 300, 540, 350]
    v2_state = {
        "centroids": [(510, 325)] * len(v1_centroids),
        "timestamps": v1_timestamps,
        "boxes": [v2_box] * len(v1_centroids),
        "velocities": [0.0] * len(v1_centroids),
        "vehicle_type": "car",
        "last_seen_frame": len(v1_centroids),
    }

    v1_state = {
        "centroids": v1_centroids,
        "timestamps": v1_timestamps,
        "boxes": v1_boxes,
        "velocities": [100.0, 100.0, 100.0, 50.0, 50.0, 300.0, 500.0, 600.0, 600.0, 600.0],
        "vehicle_type": "car",
        "last_seen_frame": len(v1_centroids),
    }

    all_tracks = {1: v1_state, 2: v2_state}
    frame_meta = {"width": 1280, "height": 720, "fps": 30.0, "frame_number": 10}

    candidate = rule.evaluate(
        track_id=1,
        track_state=v1_state,
        all_tracks_state=all_tracks,
        frame_meta=frame_meta,
        config=config,
    )

    assert candidate is not None
    assert candidate.incident_type == IncidentType.SUSPECTED_HIT_AND_RUN
    assert candidate.event_confidence >= 0.70
    assert candidate.severity in (IncidentSeverity.HIGH, IncidentSeverity.CRITICAL)


def test_hit_and_run_rule_ignores_parallel_traffic():
    """Verify HitAndRunRule does not trigger on vehicles cruising smoothly at safe distance."""
    rule = HitAndRunRule()
    config = IncidentConfig()

    v1_centroids = [(200, 100 + i * 20) for i in range(12)]
    v2_centroids = [(600, 100 + i * 20) for i in range(12)]  # 400px away
    ts = [i * 0.1 for i in range(12)]

    v1_state = {
        "centroids": v1_centroids,
        "timestamps": ts,
        "boxes": [[c[0] - 25, c[1] - 25, c[0] + 25, c[1] + 25] for c in v1_centroids],
        "velocities": [100.0] * 12,
        "vehicle_type": "car",
        "last_seen_frame": 12,
    }
    v2_state = {
        "centroids": v2_centroids,
        "timestamps": ts,
        "boxes": [[c[0] - 25, c[1] - 25, c[0] + 25, c[1] + 25] for c in v2_centroids],
        "velocities": [100.0] * 12,
        "vehicle_type": "car",
        "last_seen_frame": 12,
    }

    candidate = rule.evaluate(
        track_id=1,
        track_state=v1_state,
        all_tracks_state={1: v1_state, 2: v2_state},
        frame_meta={"width": 1280, "height": 720, "fps": 30.0, "frame_number": 12},
        config=config,
    )

    assert candidate is None


# ==============================================================================
# 4. EVIDENCE IMAGE & DETECTOR INTEGRATION TESTS
# ==============================================================================

def test_incident_evidence_image_generation(incident_detector):
    """Verify composite tri-panel diagnostic evidence card generation."""
    frame = np.full((720, 1280, 3), 100, dtype=np.uint8)
    # Draw simulated vehicle
    cv2.rectangle(frame, (400, 250), (600, 450), (0, 0, 255), -1)
    
    candidate = IncidentCandidate(
        incident_type=IncidentType.RASH_DRIVING,
        event_confidence=0.88,
        severity=IncidentSeverity.HIGH,
        reasoning="Erratic lateral lane weaving; Excessive speed (290 px/s)",
        details={"max_speed_px_s": 290.0, "triggered_indicators": ["Excessive speed (290 px/s)", "Erratic lateral lane weaving"]},
    )

    card = incident_detector.create_evidence_image(
        frame=frame,
        candidate=candidate,
        track_id=1,
        vehicle_type="car",
        vehicle_box=[400, 250, 600, 450],
        vehicle_crop=frame[250:450, 400:600],
        reg_num="TS09EA1234",
        reg_conf=0.92,
        timestamp_str="2026-09-09T08:30:00Z",
        lat=17.385044,
        lon=78.486671,
        speed_kmh=45.0,
        heading_deg=180.0,
        frame_number=150,
    )

    assert isinstance(card, np.ndarray)
    assert card.shape == (720, 1280, 3)


def test_incident_detector_frame_and_gps_sync(incident_detector, gps_sync):
    """Verify IncidentDetector processes a single frame with GPSVideoSynchronizer."""
    frame = np.full((720, 1280, 3), 120, dtype=np.uint8)
    
    track_res, incidents = incident_detector.process_frame(
        frame=frame,
        frame_number=10,
        video_timestamp=1.5,
        gps_synchronizer=gps_sync,
        output_evidence_dir=OUTPUT_INCIDENTS_DIR,
    )

    assert track_res is not None
    assert isinstance(incidents, list)


def test_incident_detector_video_processing_and_json_export(incident_detector):
    """Verify IncidentDetector processes video stream and exports valid JSON records."""
    assert SAMPLE_VIDEO_PATH.exists(), f"Missing sample video: {SAMPLE_VIDEO_PATH}"

    summary = incident_detector.process_video(
        video_path=SAMPLE_VIDEO_PATH,
        output_video_path=OUTPUT_VIDEO_PATH,
        output_json_path=OUTPUT_JSON_PATH,
        output_evidence_dir=OUTPUT_INCIDENTS_DIR,
        gps_csv_path=SAMPLE_GPS_PATH,
        max_frames=15,
    )

    assert summary["total_frames_processed"] == 15
    assert "incidents_by_type" in summary
    assert OUTPUT_JSON_PATH.exists()

    with open(OUTPUT_JSON_PATH, "r", encoding="utf-8") as f:
        records = json.load(f)
        assert isinstance(records, list)
