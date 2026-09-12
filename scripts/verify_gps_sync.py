"""Verification and Demonstration Script for Video-GPS Synchronization.

Loads simulated Hyderabad GPS trajectory, tests video frame timestamp lookups,
evaluates linear/angular interpolation, verifies edge cases, and exports
structured verification results to data/outputs/gps_sync_test.json.

Usage:
    python scripts/verify_gps_sync.py

NOTE: SIMULATED TELEMETRY FOR HACKATHON PROTOTYPE DEMONSTRATION.
"""

import sys
import json
from pathlib import Path

# Add project root to sys.path
PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from ai.pipeline.gps_sync import GPSVideoSynchronizer

GPS_CSV_PATH = PROJECT_ROOT / "data" / "gps" / "BUS_101.csv"
OUTPUT_JSON_PATH = PROJECT_ROOT / "data" / "outputs" / "gps_sync_test.json"


def run_verification():
    print("==================================================================")
    print(" BusSense-AI: Video-GPS Synchronization Pipeline Verification")
    print("==================================================================")
    print(f" Source GPS CSV: {GPS_CSV_PATH}")

    synchronizer = GPSVideoSynchronizer(
        gps_source=GPS_CSV_PATH,
        bus_id="BUS_101",
        camera_id="CAM_FRONT_01",
    )

    print(f"[OK] Loaded {len(synchronizer.gps_df)} GPS waypoints for {synchronizer.bus_id}")
    print(f"     Time Range: {synchronizer.first_gps_time.isoformat()} to {synchronizer.last_gps_time.isoformat()}\n")

    test_timestamps = [
        0.0,    # Origin / start
        0.5,    # Sub-second interpolation
        1.5,    # Linear midpoint
        3.25,   # Intermediate waypoint
        10.0,   # 10s into journey
        25.4,   # 25.4s into journey
        60.0,   # Mid-route
        -5.0,   # Pre-start (out of range clamping)
        999.0,  # Post-end (out of range clamping)
    ]

    sync_results = []
    print(f"{'Video Time':<12} | {'Lat':<10} | {'Lon':<10} | {'Speed':<9} | {'Heading':<9} | {'Status'}")
    print("-" * 75)

    for v_ts in test_timestamps:
        pos = synchronizer.get_position(v_ts, interpolate=True)
        sync_results.append(pos)
        print(
            f"{v_ts:>7.2f}s     | {pos['latitude']:<10.6f} | {pos['longitude']:<10.6f} | "
            f"{pos['speed']:>5.1f} km/h | {pos['heading']:>5.1f} deg | {pos['interpolation_status']}"
        )

    # Generate sample AI detection events inheriting synchronized GPS positions
    sample_ai_events = [
        synchronizer.create_ai_event(
            event_type="pothole",
            confidence=0.94,
            video_timestamp=3.5,
            severity="high",
            image_path="data/outputs/events/pothole_001.jpg",
            metadata={"depth_est_cm": 9.2, "bbox": [320, 480, 450, 600]},
        ),
        synchronizer.create_ai_event(
            event_type="congestion",
            confidence=0.89,
            video_timestamp=12.0,
            severity="medium",
            metadata={"vehicle_density": "high", "surrounding_cars": 14},
        ),
        synchronizer.create_ai_event(
            event_type="license_plate_detected",
            confidence=0.96,
            video_timestamp=24.5,
            severity="low",
            image_path="data/outputs/events/plate_001.jpg",
            metadata={"plate_text": "TS09EA1234", "ocr_confidence": 0.97},
        ),
    ]

    # Export structured test artifact
    OUTPUT_JSON_PATH.parent.mkdir(parents=True, exist_ok=True)
    export_data = {
        "metadata": {
            "module": "GPSVideoSynchronizer",
            "bus_id": "BUS_101",
            "camera_id": "CAM_FRONT_01",
            "region": "Hyderabad Metropolitan Region (Route 216)",
            "is_simulated": True,
            "simulation_notice": "SIMULATED TELEMETRY FOR HACKATHON PROTOTYPE DEMONSTRATION",
        },
        "frame_synchronization_samples": sync_results,
        "sample_ai_events": sample_ai_events,
    }

    with open(OUTPUT_JSON_PATH, "w", encoding="utf-8") as f:
        json.dump(export_data, f, indent=2)

    print(f"\n[OK] Exported synchronization verification dataset to: {OUTPUT_JSON_PATH}")
    print("==================================================================")


if __name__ == "__main__":
    run_verification()
