"""Unit and integration tests for vehicle tracking and prototype traffic density estimation."""

import pytest
import numpy as np
import cv2
import json
from pathlib import Path

from ai.pipeline.gps_sync import GPSVideoSynchronizer
from ai.tracking.density_estimator import (
    TrafficDensityEstimator,
    TrafficDensity,
    IntervalTrafficMeasurement,
    DEFAULT_LOW_DENSITY_MAX,
    DEFAULT_MEDIUM_DENSITY_MAX,
)
from ai.tracking.tracker import (
    VehicleTracker,
    TrackedVehicleDetection,
    FrameTrackingResult,
    TARGET_VEHICLE_CLASSES,
)

PROJECT_ROOT = Path(__file__).resolve().parent.parent
SAMPLE_VIDEO_PATH = PROJECT_ROOT / "data" / "videos" / "sample_bus_feed.mp4"
SAMPLE_GPS_PATH = PROJECT_ROOT / "data" / "gps" / "BUS_101.csv"
OUTPUT_VIDEO_PATH = PROJECT_ROOT / "data" / "outputs" / "test_tracking_output.mp4"
OUTPUT_JSON_PATH = PROJECT_ROOT / "data" / "outputs" / "test_density_measurements.json"


@pytest.fixture(scope="module")
def tracker():
    """Shared lightweight VehicleTracker fixture."""
    return VehicleTracker(model_path="yolov8n.pt", conf_threshold=0.25, device="cpu")


@pytest.fixture(scope="module")
def gps_sync():
    """Shared GPSVideoSynchronizer fixture."""
    return GPSVideoSynchronizer(gps_source=SAMPLE_GPS_PATH, bus_id="BUS_101")


def test_density_classification_thresholds():
    """Verify traffic density classification follows configured threshold boundaries."""
    estimator = TrafficDensityEstimator(low_max=2, medium_max=5)

    # 0, 1, 2 -> LOW
    assert estimator.classify_density(0) == TrafficDensity.LOW
    assert estimator.classify_density(1) == TrafficDensity.LOW
    assert estimator.classify_density(2) == TrafficDensity.LOW

    # 3, 4, 5 -> MEDIUM
    assert estimator.classify_density(3) == TrafficDensity.MEDIUM
    assert estimator.classify_density(4) == TrafficDensity.MEDIUM
    assert estimator.classify_density(5) == TrafficDensity.MEDIUM

    # 6+ -> HIGH
    assert estimator.classify_density(6) == TrafficDensity.HIGH
    assert estimator.classify_density(20) == TrafficDensity.HIGH


def test_custom_density_thresholds():
    """Verify custom configured thresholds are respected."""
    custom_estimator = TrafficDensityEstimator(low_max=4, medium_max=10)
    assert custom_estimator.classify_density(4) == TrafficDensity.LOW
    assert custom_estimator.classify_density(5) == TrafficDensity.MEDIUM
    assert custom_estimator.classify_density(10) == TrafficDensity.MEDIUM
    assert custom_estimator.classify_density(11) == TrafficDensity.HIGH


def test_invalid_density_thresholds_raises_error():
    """Verify invalid threshold order (low_max >= medium_max) raises ValueError."""
    with pytest.raises(ValueError, match="must be strictly less than"):
        TrafficDensityEstimator(low_max=5, medium_max=3)


def test_interval_measurement_gps_synchronization(gps_sync):
    """Verify create_interval_measurement imports and integrates with GPSVideoSynchronizer."""
    estimator = TrafficDensityEstimator(gps_synchronizer=gps_sync, low_max=2, medium_max=5)

    meas = estimator.create_interval_measurement(
        interval_index=1,
        start_time=0.0,
        end_time=1.0,
        car_count=2,
        bus_count=1,
        truck_count=0,
        motorcycle_count=0,
        bicycle_count=1,
        active_track_ids=[1, 2, 3, 4],
        unique_interval_track_ids=[1, 2, 3, 4],
    )

    assert isinstance(meas, IntervalTrafficMeasurement)
    assert meas.interval_index == 1
    assert meas.total_vehicle_count == 4
    assert meas.traffic_density == "MEDIUM"
    assert meas.latitude > 0.0
    assert meas.longitude > 0.0
    assert meas.is_simulated is True
    assert "prototype traffic-density estimation" in meas.disclaimer.lower()


def test_tracker_initialization(tracker):
    """Verify VehicleTracker registers all required classes and model is loaded."""
    expected = {"car", "bus", "truck", "motorcycle", "bicycle"}
    assert expected.issubset(set(tracker.target_classes.values()))
    assert tracker.model is not None


def test_recount_prevention_logic(tracker):
    """Verify that a vehicle observed across multiple frames is counted only once."""
    tracker.reset_state()

    # Create dummy detections with the same track ID across 5 simulated frames
    for f in range(5):
        det = TrackedVehicleDetection(
            track_id=42,
            class_id=2,
            vehicle_type="car",
            confidence=0.85,
            bounding_box=[100, 100, 200, 200],
            area=10000,
            centroid=(150, 150),
        )
        tracker.track_class_votes[det.track_id]["car"] += det.confidence
        tracker.all_seen_track_ids.add(det.track_id)

    # Despite 5 frame observations, unique car count must strictly equal 1
    assert len(tracker.seen_track_ids_by_type["car"]) == 1
    assert len(tracker.all_seen_track_ids) == 1
    assert tracker.get_cumulative_unique_counts_by_type()["car"] == 1
    assert sum(tracker.get_cumulative_unique_counts_by_type().values()) == 1


def test_track_consensus_majority_voting(tracker):
    """Verify track consensus resolves class flickering to dominant vehicle class."""
    tracker.reset_state()

    # Track 1: Car with momentary truck flicker (4 car observations @ 0.80, 1 truck @ 0.35)
    for _ in range(4):
        tracker.track_class_votes[1]["car"] += 0.80
    tracker.track_class_votes[1]["truck"] += 0.35
    tracker.all_seen_track_ids.add(1)

    # Track 2: Bus with truck ambiguity (3 bus observations @ 0.70, 2 truck @ 0.40)
    for _ in range(3):
        tracker.track_class_votes[2]["bus"] += 0.70
    for _ in range(2):
        tracker.track_class_votes[2]["truck"] += 0.40
    tracker.all_seen_track_ids.add(2)

    # Track 3: Clear Motorcycle
    tracker.track_class_votes[3]["motorcycle"] += 0.90
    tracker.all_seen_track_ids.add(3)

    assert tracker.get_consensus_class(1) == "car"
    assert tracker.get_consensus_class(2) == "bus"
    assert tracker.get_consensus_class(3) == "motorcycle"

    counts = tracker.get_cumulative_unique_counts_by_type()
    assert counts["car"] == 1
    assert counts["bus"] == 1
    assert counts["truck"] == 0  # No false truck inflation!
    assert counts["motorcycle"] == 1
    assert counts["bicycle"] == 0

    # Invariant: sum of category counts equals total unique vehicles
    assert sum(counts.values()) == len(tracker.all_seen_track_ids) == 3


def test_annotate_frame_rendering(tracker):
    """Verify annotate_frame produces valid BGR image with bounding boxes and HUD."""
    frame = np.full((480, 640, 3), (60, 60, 65), dtype=np.uint8)
    det = TrackedVehicleDetection(
        track_id=1,
        class_id=2,
        vehicle_type="car",
        confidence=0.90,
        bounding_box=[100, 100, 200, 200],
        area=10000,
        centroid=(150, 150),
    )
    result = FrameTrackingResult(
        frame_number=1,
        video_timestamp=0.04,
        detections=[det],
        live_counts_by_type={"car": 1, "bus": 0, "truck": 0, "motorcycle": 0, "bicycle": 0},
        live_total_vehicles=1,
        cumulative_unique_counts_by_type={"car": 1, "bus": 0, "truck": 0, "motorcycle": 0, "bicycle": 0},
        cumulative_total_unique_vehicles=1,
        traffic_density="LOW",
    )

    annotated = tracker.annotate_frame(frame, result, show_hud=True, show_trails=True, fps=25.0)
    assert isinstance(annotated, np.ndarray)
    assert annotated.shape == frame.shape
    assert annotated.dtype == np.uint8


def test_missing_video_raises_error(tracker):
    """Verify FileNotFoundError is raised when target video does not exist."""
    fake_path = PROJECT_ROOT / "data" / "videos" / "missing_track_video_9999.mp4"
    with pytest.raises(FileNotFoundError, match="Input video file not found"):
        tracker.process_video(fake_path)


def test_full_video_tracking_and_density_export(tracker, gps_sync):
    """Verify video processing generates structured JSON with intervals and GPS coordinates."""
    summary = tracker.process_video(
        video_path=SAMPLE_VIDEO_PATH,
        gps_synchronizer=gps_sync,
        output_video_path=OUTPUT_VIDEO_PATH,
        output_json_path=OUTPUT_JSON_PATH,
        interval_seconds=1.0,
        max_frames=20,
        show_progress=False,
    )

    assert "metadata" in summary
    assert "aggregate_statistics" in summary
    assert "interval_measurements" in summary
    assert summary["metadata"]["is_simulated"] is True
    assert "prototype" in summary["metadata"]["disclaimer"].lower()

    assert OUTPUT_JSON_PATH.exists()
    with open(OUTPUT_JSON_PATH, "r", encoding="utf-8") as f:
        data = json.load(f)
        assert len(data["interval_measurements"]) > 0
        first_interval = data["interval_measurements"][0]
        assert "latitude" in first_interval
        assert "longitude" in first_interval
        assert "traffic_density" in first_interval
        assert first_interval["traffic_density"] in ["LOW", "MEDIUM", "HIGH"]
