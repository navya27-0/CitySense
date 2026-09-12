"""Unit and integration tests for YOLO vehicle detection module."""

import pytest
import json
import numpy as np
import cv2
from pathlib import Path
from ai.vehicle_detection import VehicleDetector, FrameDetectionResult, SingleDetection

PROJECT_ROOT = Path(__file__).resolve().parent.parent
SAMPLE_VIDEO_PATH = PROJECT_ROOT / "data" / "videos" / "sample_bus_feed.mp4"
OUTPUT_VIDEO_PATH = PROJECT_ROOT / "data" / "outputs" / "test_detection_output.mp4"
OUTPUT_JSON_PATH = PROJECT_ROOT / "data" / "outputs" / "test_detections.json"


@pytest.fixture(scope="module")
def detector():
    """Initializes a shared lightweight VehicleDetector instance."""
    return VehicleDetector(model_path="yolov8n.pt", conf_threshold=0.25, device="cpu")


def test_detector_initialization(detector):
    """Verify detector loads model and registers all 5 required vehicle classes."""
    expected_classes = {"car", "bus", "truck", "motorcycle", "bicycle"}
    registered_classes = set(detector.target_classes.values())
    assert expected_classes.issubset(registered_classes)
    assert detector.model is not None


def test_detect_empty_or_corrupted_frame(detector):
    """Verify detector raises ValueError on empty or corrupted frames."""
    with pytest.raises(ValueError, match="invalid, empty, or corrupted"):
        detector.detect_frame(None)

    with pytest.raises(ValueError, match="invalid, empty, or corrupted"):
        detector.detect_frame(np.array([], dtype=np.uint8))


def test_detect_synthetic_frame(detector):
    """Verify detection on a synthetic image containing geometric vehicle representations."""
    frame = np.full((480, 640, 3), (60, 60, 65), dtype=np.uint8)
    # Draw simple road pattern
    cv2.rectangle(frame, (100, 150), (250, 220), (40, 40, 200), -1)

    result = detector.detect_frame(frame, frame_number=1, video_timestamp=0.04)
    assert isinstance(result, FrameDetectionResult)
    assert result.frame_number == 1
    assert result.video_timestamp == 0.04
    assert isinstance(result.counts_by_type, dict)
    assert "car" in result.counts_by_type
    assert "bus" in result.counts_by_type


def test_annotate_frame(detector):
    """Verify frame annotation returns valid image array with identical resolution."""
    frame = np.full((480, 640, 3), (60, 60, 65), dtype=np.uint8)
    dummy_detection = SingleDetection(
        class_id=2,
        vehicle_type="car",
        confidence=0.88,
        bounding_box=[100, 150, 250, 220],
        area=10500,
    )
    result = FrameDetectionResult(
        frame_number=1,
        video_timestamp=0.04,
        detections=[dummy_detection],
        counts_by_type={"car": 1, "bus": 0, "truck": 0, "motorcycle": 0, "bicycle": 0},
        total_vehicles=1,
    )

    annotated = detector.annotate_frame(frame, result, show_hud=True, fps=30.0)
    assert isinstance(annotated, np.ndarray)
    assert annotated.shape == frame.shape
    assert annotated.dtype == np.uint8


def test_missing_video_file(detector):
    """Verify FileNotFoundError is raised when target video does not exist."""
    fake_path = PROJECT_ROOT / "data" / "videos" / "non_existent_video_12345.mp4"
    with pytest.raises(FileNotFoundError, match="Input video file not found"):
        detector.process_video(fake_path)


def test_video_processing_and_json_export(detector):
    """Verify processing video extracts structured JSON with required fields."""
    # Ensure sample video exists
    if not SAMPLE_VIDEO_PATH.exists():
        from scripts.generate_sample_traffic_video import generate_traffic_video
        generate_traffic_video(output_path=SAMPLE_VIDEO_PATH, num_frames=30)

    summary = detector.process_video(
        video_path=SAMPLE_VIDEO_PATH,
        output_video_path=OUTPUT_VIDEO_PATH,
        output_json_path=OUTPUT_JSON_PATH,
        max_frames=15,
        show_progress=False,
    )

    assert "metadata" in summary
    assert "aggregate_statistics" in summary
    assert "frame_detections" in summary
    assert len(summary["frame_detections"]) == 15

    # Check JSON export on disk
    assert OUTPUT_JSON_PATH.exists()
    with open(OUTPUT_JSON_PATH, "r", encoding="utf-8") as f:
        loaded = json.load(f)

    first_frame = loaded["frame_detections"][0]
    assert "frame_number" in first_frame
    assert "video_timestamp" in first_frame
    assert "total_vehicles" in first_frame
    assert "counts_by_type" in first_frame
    assert "detections" in first_frame
