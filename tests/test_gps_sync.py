"""Unit test suite for GPSVideoSynchronizer edge AI pipeline synchronization module."""

import pytest
import pandas as pd
from datetime import datetime, timezone, timedelta
from ai.pipeline.gps_sync import GPSVideoSynchronizer, interpolate_heading


def create_sample_gps_data():
    """Generates synthetic GPS records for controlled unit testing."""
    base_time = datetime(2026, 9, 9, 10, 0, 0, tzinfo=timezone.utc)
    return [
        {"timestamp": (base_time + timedelta(seconds=0)).isoformat(), "latitude": 17.3850, "longitude": 78.4860, "speed": 20.0, "heading": 90.0},
        {"timestamp": (base_time + timedelta(seconds=1)).isoformat(), "latitude": 17.3860, "longitude": 78.4870, "speed": 30.0, "heading": 90.0},
        {"timestamp": (base_time + timedelta(seconds=2)).isoformat(), "latitude": 17.3870, "longitude": 78.4880, "speed": 40.0, "heading": 100.0},
        {"timestamp": (base_time + timedelta(seconds=5)).isoformat(), "latitude": 17.3900, "longitude": 78.4910, "speed": 25.0, "heading": 110.0},
    ]


def test_exact_match():
    """Test lookup matching an exact GPS timestamp."""
    data = create_sample_gps_data()
    sync = GPSVideoSynchronizer(gps_source=data, bus_id="BUS_101", camera_id="CAM_FRONT_01")

    pos = sync.get_position(video_timestamp=1.0)
    assert pos["interpolation_status"] == "exact_match"
    assert pos["latitude"] == pytest.approx(17.3860, abs=1e-5)
    assert pos["longitude"] == pytest.approx(78.4870, abs=1e-5)
    assert pos["speed"] == 30.0
    assert pos["heading"] == 90.0
    assert pos["bus_id"] == "BUS_101"
    assert pos["camera_id"] == "CAM_FRONT_01"


def test_linear_interpolation():
    """Test linear coordinate and speed interpolation between two bounding GPS timestamps."""
    data = create_sample_gps_data()
    sync = GPSVideoSynchronizer(gps_source=data)

    # t = 0.5s is midway between t0 (17.3850, 78.4860, 20km/h) and t1 (17.3860, 78.4870, 30km/h)
    pos = sync.get_position(video_timestamp=0.5, interpolate=True)
    assert pos["interpolation_status"] == "interpolated"
    assert pos["latitude"] == pytest.approx(17.3855, abs=1e-5)
    assert pos["longitude"] == pytest.approx(78.4865, abs=1e-5)
    assert pos["speed"] == pytest.approx(25.0, abs=1e-2)
    assert pos["heading"] == pytest.approx(90.0, abs=1e-1)


def test_heading_interpolation_wrap_around():
    """Test heading angular interpolation across the 0° / 360° boundary."""
    # Heading from 350° to 10° midway should be 0.0° (not 180°)
    mid_heading = interpolate_heading(350.0, 10.0, alpha=0.5)
    assert mid_heading == pytest.approx(0.0, abs=1e-1)

    # Heading from 10° to 350° midway should also be 0.0°
    mid_heading_rev = interpolate_heading(10.0, 350.0, alpha=0.5)
    assert mid_heading_rev == pytest.approx(0.0, abs=1e-1)


def test_nearest_fallback_when_disabled():
    """Test fallback to nearest neighbor when interpolate=False."""
    data = create_sample_gps_data()
    sync = GPSVideoSynchronizer(gps_source=data)

    # t = 0.8s should snap to t = 1.0s (17.3860, 78.4870)
    pos = sync.get_position(video_timestamp=0.8, interpolate=False)
    assert pos["interpolation_status"] == "nearest_neighbor"
    assert pos["latitude"] == pytest.approx(17.3860, abs=1e-5)
    assert pos["longitude"] == pytest.approx(78.4870, abs=1e-5)


def test_out_of_range_clamping():
    """Test boundary clamping for timestamps before start or after end of GPS log."""
    data = create_sample_gps_data()
    sync = GPSVideoSynchronizer(gps_source=data)

    # Negative timestamp (before video start)
    pos_pre = sync.get_position(video_timestamp=-3.5)
    assert pos_pre["interpolation_status"] == "out_of_range_clamped"
    assert pos_pre["latitude"] == pytest.approx(17.3850, abs=1e-5)

    # Timestamp far past end of GPS (5s end)
    pos_post = sync.get_position(video_timestamp=99.0)
    assert pos_post["interpolation_status"] == "out_of_range_clamped"
    assert pos_post["latitude"] == pytest.approx(17.3900, abs=1e-5)
    assert pos_post["longitude"] == pytest.approx(78.4910, abs=1e-5)


def test_malformed_and_missing_rows():
    """Test graceful sanitization of malformed GPS rows, NaNs, and corrupt data."""
    base_time = datetime(2026, 9, 9, 10, 0, 0, tzinfo=timezone.utc)
    dirty_data = [
        {"timestamp": None, "latitude": 17.3850, "longitude": 78.4860},  # Missing timestamp
        {"timestamp": "CORRUPT_TIMESTAMP", "latitude": 17.3850, "longitude": 78.4860},  # Invalid timestamp
        {"timestamp": (base_time + timedelta(seconds=0)).isoformat(), "latitude": 17.3850, "longitude": 78.4860, "speed": "fast", "heading": 90},
        {"timestamp": (base_time + timedelta(seconds=1)).isoformat(), "latitude": "invalid_lat", "longitude": 78.4870},  # Bad lat
        {"timestamp": (base_time + timedelta(seconds=2)).isoformat(), "latitude": 17.3870, "longitude": 78.4880, "speed": 35.0, "heading": 95.0},
    ]

    sync = GPSVideoSynchronizer(gps_source=dirty_data)
    assert len(sync.gps_df) == 2  # Exactly 2 valid rows retained

    pos = sync.get_position(video_timestamp=1.0)
    assert pos["interpolation_status"] == "interpolated"
    assert pos["latitude"] == pytest.approx(17.3860, abs=1e-5)


def test_duplicate_timestamps():
    """Test that duplicate timestamps are deduplicated safely."""
    base_time = datetime(2026, 9, 9, 10, 0, 0, tzinfo=timezone.utc)
    data = [
        {"timestamp": (base_time + timedelta(seconds=0)).isoformat(), "latitude": 17.3850, "longitude": 78.4860, "speed": 20.0},
        {"timestamp": (base_time + timedelta(seconds=1)).isoformat(), "latitude": 17.3860, "longitude": 78.4870, "speed": 30.0},
        {"timestamp": (base_time + timedelta(seconds=1)).isoformat(), "latitude": 17.3860, "longitude": 78.4870, "speed": 30.0},  # Duplicate
        {"timestamp": (base_time + timedelta(seconds=2)).isoformat(), "latitude": 17.3870, "longitude": 78.4880, "speed": 40.0},
    ]

    sync = GPSVideoSynchronizer(gps_source=data)
    assert len(sync.gps_df) == 3


def test_unsorted_gps_data():
    """Test that unsorted GPS data is ordered chronologically automatically."""
    base_time = datetime(2026, 9, 9, 10, 0, 0, tzinfo=timezone.utc)
    unsorted_data = [
        {"timestamp": (base_time + timedelta(seconds=2)).isoformat(), "latitude": 17.3870, "longitude": 78.4880},
        {"timestamp": (base_time + timedelta(seconds=0)).isoformat(), "latitude": 17.3850, "longitude": 78.4860},
        {"timestamp": (base_time + timedelta(seconds=1)).isoformat(), "latitude": 17.3860, "longitude": 78.4870},
    ]

    sync = GPSVideoSynchronizer(gps_source=unsorted_data)
    assert sync.gps_df["dt"].is_monotonic_increasing

    pos = sync.get_position(video_timestamp=0.5)
    assert pos["interpolation_status"] == "interpolated"
    assert pos["latitude"] == pytest.approx(17.3855, abs=1e-5)


def test_ai_event_generation_and_inheritance():
    """Test create_ai_event generates compliant AI event structure with inherited GPS."""
    data = create_sample_gps_data()
    sync = GPSVideoSynchronizer(gps_source=data, bus_id="BUS_102", camera_id="CAM_LEFT_02")

    event = sync.create_ai_event(
        event_type="pothole",
        confidence=0.91,
        video_timestamp=1.5,
        severity="high",
        image_path="data/outputs/events/pothole_1.jpg",
        metadata={"depth_cm": 8.0},
    )

    assert event["event_type"] == "pothole"
    assert event["confidence"] == 0.91
    assert event["severity"] == "high"
    assert event["video_timestamp"] == 1.5
    assert event["bus_id"] == "BUS_102"
    assert event["camera_id"] == "CAM_LEFT_02"
    assert event["latitude"] == pytest.approx(17.3865, abs=1e-5)
    assert event["longitude"] == pytest.approx(78.4875, abs=1e-5)
    assert event["speed"] == pytest.approx(35.0, abs=1e-2)
    assert event["image_path"] == "data/outputs/events/pothole_1.jpg"
    assert event["metadata"]["depth_cm"] == 8.0
    assert event["is_simulated"] is True
