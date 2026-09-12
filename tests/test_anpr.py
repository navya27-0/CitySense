"""Unit and integration tests for Automatic Number-Plate Recognition (ANPR) pipeline."""

import pytest
import numpy as np
import cv2
import json
from pathlib import Path

from ai.pipeline.gps_sync import GPSVideoSynchronizer
from ai.anpr.validator import PlateValidator, ValidationResult
from ai.anpr.ocr_engine import OCREngine, PlateOCRResult
from ai.anpr.plate_detector import PlateDetector, PlateDetection
from ai.anpr.pipeline import ANPRPipeline, PlateIncidentRecord

PROJECT_ROOT = Path(__file__).resolve().parent.parent
SAMPLE_VIDEO_PATH = PROJECT_ROOT / "data" / "videos" / "sample_bus_feed.mp4"
SAMPLE_GPS_PATH = PROJECT_ROOT / "data" / "gps" / "BUS_101.csv"
OUTPUT_VIDEO_PATH = PROJECT_ROOT / "data" / "outputs" / "test_anpr_output.mp4"
OUTPUT_JSON_PATH = PROJECT_ROOT / "data" / "outputs" / "test_anpr_records.json"
OUTPUT_PLATES_DIR = PROJECT_ROOT / "data" / "outputs" / "test_plates"


@pytest.fixture(scope="module")
def gps_sync():
    """Shared GPSVideoSynchronizer fixture."""
    return GPSVideoSynchronizer(gps_source=SAMPLE_GPS_PATH, bus_id="BUS_101")


@pytest.fixture(scope="module")
def anpr_pipeline():
    """Shared lightweight ANPRPipeline fixture."""
    return ANPRPipeline(
        vehicle_model="yolov8n.pt",
        plate_model="models/number_plates/best.pt",
        conf_threshold=0.25,
        bus_id="BUS_101",
        device="cpu",
    )


# ==============================================================================
# 1. PLATE VALIDATOR & CONFUSION MATRIX TESTS
# ==============================================================================

def test_standard_indian_license_plate_validation():
    """Verify standard Indian registration formats across various states are validated."""
    valid_samples = [
        ("TS09EA1234", "TS", "STANDARD_INDIAN"),
        ("AP28AB5678", "AP", "STANDARD_INDIAN"),
        ("DL3CAA1111", "DL", "STANDARD_INDIAN"),
        ("MH12DE1432", "MH", "STANDARD_INDIAN"),
        ("KA01MG2020", "KA", "STANDARD_INDIAN"),
        ("HR26DK8337", "HR", "STANDARD_INDIAN"),
        ("TN07CL4920", "TN", "STANDARD_INDIAN"),
    ]

    for raw, expected_state, expected_type in valid_samples:
        res = PlateValidator.validate_and_normalize(raw)
        assert res.is_valid_format is True, f"Failed on valid plate: {raw}"
        assert res.state_code == expected_state
        assert res.plate_type == expected_type
        assert res.rejection_reason is None


def test_bharat_stage_bh_series_validation():
    """Verify Bharat Stage (BH Series) nationwide registration format validation."""
    bh_samples = [
        "22BH1234AA",
        "21BH9999Z",
        "23BH0001AB",
    ]

    for raw in bh_samples:
        res = PlateValidator.validate_and_normalize(raw)
        assert res.is_valid_format is True
        assert res.plate_type == "BH_SERIES"
        assert res.state_code == "BH"
        assert res.rejection_reason is None


def test_positional_character_confusion_corrections():
    """Verify positional context-aware confusion matrix corrections (e.g. O->0, 5->S, B->8)."""
    # 1. Letter 'O' in district code (digits) -> corrected to '0'
    res1 = PlateValidator.validate_and_normalize("TSO9EA1234")
    assert res1.normalized_text == "TS09EA1234"
    assert res1.is_valid_format is True

    # 2. Digit '5' in state code (letters) -> corrected to 'S'
    res2 = PlateValidator.validate_and_normalize("T509EA1234")
    assert res2.normalized_text == "TS09EA1234"
    assert res2.is_valid_format is True

    # 3. Letter 'I' in number sequence -> corrected to '1'
    res3 = PlateValidator.validate_and_normalize("TS09EAI234")
    assert res3.normalized_text == "TS09EA1234"
    assert res3.is_valid_format is True

    # 4. Spacing and punctuation stripping: "TS-09 EA 1234" -> "TS09EA1234"
    res4 = PlateValidator.validate_and_normalize("TS-09 EA 1234")
    assert res4.normalized_text == "TS09EA1234"
    assert res4.is_valid_format is True


def test_invalid_plate_rejection_with_reasons():
    """Verify invalid strings are rejected with explicit non-null rejection reasons."""
    invalid_samples = [
        ("", "Empty or whitespace-only"),
        ("ABC", "too short"),
        ("VERYLONGLICENSEPLATENUMBER123456", "exceeds maximum"),
        ("ZZ09EA1234", "Invalid state prefix"),
        ("TS09ABCDE", "does not match standard Indian registration pattern"),
    ]

    for raw, expected_reason_keyword in invalid_samples:
        res = PlateValidator.validate_and_normalize(raw)
        assert res.is_valid_format is False
        assert res.rejection_reason is not None
        assert expected_reason_keyword.lower() in res.rejection_reason.lower()
        # Ensure raw result is strictly preserved
        assert res.raw_text == raw


# ==============================================================================
# 2. OCR ENGINE & PREPROCESSING TESTS
# ==============================================================================

def test_ocr_preprocessing_pipeline():
    """Verify image preprocessing produces valid high-contrast 3-channel output."""
    dummy_crop = np.full((40, 140, 3), (180, 180, 185), dtype=np.uint8)
    cv2.putText(dummy_crop, "TS09EA1234", (5, 28), cv2.FONT_HERSHEY_SIMPLEX, 0.6, (20, 20, 20), 2)

    preprocessed = OCREngine.preprocess_plate_image(dummy_crop, target_height=64)
    assert isinstance(preprocessed, np.ndarray)
    assert preprocessed.shape[0] == 64
    assert len(preprocessed.shape) == 3
    assert preprocessed.dtype == np.uint8


def test_ocr_engine_text_recognition():
    """Verify OCREngine returns structured PlateOCRResult."""
    ocr_engine = OCREngine(languages=["en"], gpu=False)
    dummy_plate = np.full((50, 180, 3), (240, 240, 240), dtype=np.uint8)
    cv2.putText(dummy_plate, "TS09EA1234", (10, 35), cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 0, 0), 2)

    res = ocr_engine.recognize_text(dummy_plate)
    assert isinstance(res, PlateOCRResult)
    assert isinstance(res.raw_text, str)
    assert 0.0 <= res.confidence <= 1.0


# ==============================================================================
# 3. PLATE DETECTOR TESTS
# ==============================================================================

def test_plate_detector_morphological_localization():
    """Verify adaptive morphological extractor localizes candidate plate on vehicle crop."""
    detector = PlateDetector()
    frame = np.full((720, 1280, 3), (80, 80, 85), dtype=np.uint8)

    # Draw synthetic car box
    vx1, vy1, vx2, vy2 = 200, 200, 600, 500
    cv2.rectangle(frame, (vx1, vy1), (vx2, vy2), (40, 40, 45), -1)

    # Draw synthetic high-contrast license plate inside vehicle lower half
    px1, py1, px2, py2 = 320, 420, 480, 465
    cv2.rectangle(frame, (px1, py1), (px2, py2), (240, 240, 240), -1)
    cv2.putText(frame, "TS09EA1234", (px1 + 10, py1 + 30), cv2.FONT_HERSHEY_SIMPLEX, 0.6, (10, 10, 10), 2)

    det = detector.detect_plate_in_vehicle(frame, [vx1, vy1, vx2, vy2], vehicle_type="car")
    assert det is not None
    assert isinstance(det, PlateDetection)
    assert det.plate_crop.size > 0
    assert det.confidence > 0.0
    assert len(det.plate_box) == 4


# ==============================================================================
# 4. PIPELINE INTEGRATION & EVIDENCE GENERATION TESTS
# ==============================================================================

def test_create_evidence_image_card(anpr_pipeline):
    """Verify create_evidence_image generates a valid 720x360 tri-panel evidence card."""
    frame = np.full((720, 1280, 3), (60, 65, 75), dtype=np.uint8)
    plate_crop = np.full((40, 140, 3), (250, 250, 250), dtype=np.uint8)
    vehicle_crop = np.full((200, 200, 3), (40, 40, 40), dtype=np.uint8)

    plate_det = PlateDetection(
        plate_box=[320, 420, 460, 460],
        vehicle_box=[200, 200, 600, 500],
        confidence=0.88,
        plate_crop=plate_crop,
        vehicle_crop=vehicle_crop,
        aspect_ratio=3.5,
        method="ADAPTIVE_MORPHOLOGICAL",
    )

    val_res = ValidationResult(
        raw_text="TS09EA1234",
        normalized_text="TS09EA1234",
        is_valid_format=True,
        plate_type="STANDARD_INDIAN",
        state_code="TS",
        rejection_reason=None,
    )

    card = anpr_pipeline.create_evidence_image(
        frame=frame,
        plate_det=plate_det,
        val_res=val_res,
        ocr_conf=0.92,
        track_id=1,
        vehicle_type="car",
        timestamp_str="2026-09-09T14:30:22.000Z",
        lat=17.3918,
        lon=78.4344,
    )

    assert isinstance(card, np.ndarray)
    assert card.shape == (360, 720, 3)
    assert card.dtype == np.uint8


def test_process_frame_gps_synchronization(anpr_pipeline, gps_sync):
    """Verify process_frame attaches geographic coordinates via GPSVideoSynchronizer."""
    frame = np.full((720, 1280, 3), (60, 65, 75), dtype=np.uint8)

    track_res, records = anpr_pipeline.process_frame(
        frame=frame,
        frame_number=10,
        video_timestamp=0.333,
        gps_synchronizer=gps_sync,
    )

    assert track_res is not None
    assert isinstance(records, list)


def test_full_anpr_video_processing(anpr_pipeline, gps_sync):
    """Verify video processing generates structured JSON incident records."""
    summary = anpr_pipeline.process_video(
        video_path=SAMPLE_VIDEO_PATH,
        gps_synchronizer=gps_sync,
        output_video_path=OUTPUT_VIDEO_PATH,
        output_json_path=OUTPUT_JSON_PATH,
        output_evidence_dir=OUTPUT_PLATES_DIR,
        max_frames=15,
        show_progress=False,
    )

    assert "metadata" in summary
    assert "aggregate_statistics" in summary
    assert "deduplicated_plate_incidents" in summary
    assert summary["metadata"]["is_simulated"] is True
    assert summary["metadata"]["bus_id"] == "BUS_101"

    assert OUTPUT_JSON_PATH.exists()
    with open(OUTPUT_JSON_PATH, "r", encoding="utf-8") as f:
        data = json.load(f)
        assert "deduplicated_plate_incidents" in data
