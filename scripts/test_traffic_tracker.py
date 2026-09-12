"""Standalone Traffic Tracking & Density Estimation Verification Runner.

Processes input MP4 video using YOLOv8 + ByteTrack, synchronizes with GPS CSV via
GPSVideoSynchronizer, counts unique vehicles (preventing recounts), classifies prototype
traffic density (LOW / MEDIUM / HIGH), and exports annotated video + structured JSON.

Usage:
    python scripts/test_traffic_tracker.py [--video data/videos/sample_bus_feed.mp4] [--gps-csv data/gps/BUS_101.csv]

Outputs:
    - data/outputs/traffic_tracking_output.mp4
    - data/outputs/traffic_density_measurements.json

DISCLAIMER: Prototype traffic-density estimation — not scientifically calibrated.
"""

import sys
import argparse
from pathlib import Path

# Add project root to sys.path
PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from ai.pipeline.gps_sync import GPSVideoSynchronizer
from ai.tracking import VehicleTracker, TrafficDensityEstimator

DEFAULT_VIDEO_PATH = PROJECT_ROOT / "data" / "videos" / "sample_bus_feed.mp4"
DEFAULT_GPS_CSV = PROJECT_ROOT / "data" / "gps" / "BUS_101.csv"
DEFAULT_OUT_VIDEO = PROJECT_ROOT / "data" / "outputs" / "traffic_tracking_output.mp4"
DEFAULT_OUT_JSON = PROJECT_ROOT / "data" / "outputs" / "traffic_density_measurements.json"


def main():
    parser = argparse.ArgumentParser(
        description="Run multi-object vehicle tracking and prototype traffic density estimation on video + GPS feed."
    )
    parser.add_argument(
        "--video",
        type=str,
        default=str(DEFAULT_VIDEO_PATH),
        help=f"Path to input MP4 video (default: {DEFAULT_VIDEO_PATH})",
    )
    parser.add_argument(
        "--gps-csv",
        type=str,
        default=str(DEFAULT_GPS_CSV),
        help=f"Path to input GPS CSV (default: {DEFAULT_GPS_CSV})",
    )
    parser.add_argument(
        "--out-video",
        "--output-video",
        dest="out_video",
        type=str,
        default=str(DEFAULT_OUT_VIDEO),
        help=f"Path to output annotated MP4 video (default: {DEFAULT_OUT_VIDEO})",
    )
    parser.add_argument(
        "--out-json",
        "--output-json",
        dest="out_json",
        type=str,
        default=str(DEFAULT_OUT_JSON),
        help=f"Path to output structured JSON (default: {DEFAULT_OUT_JSON})",
    )
    parser.add_argument(
        "--interval-seconds",
        type=float,
        default=1.0,
        help="Aggregation time window in seconds for traffic density measurements (default: 1.0)",
    )
    parser.add_argument(
        "--conf",
        type=float,
        default=0.25,
        help="Detection confidence threshold (default: 0.25)",
    )
    parser.add_argument(
        "--model",
        type=str,
        default="yolov8n.pt",
        help="YOLO model checkpoint (default: yolov8n.pt)",
    )
    parser.add_argument(
        "--imgsz",
        type=int,
        default=640,
        help="Inference image resolution (default: 640)",
    )
    parser.add_argument(
        "--max-frames",
        type=int,
        default=250,
        help="Maximum frames to process (default: 250, 0 = entire video)",
    )

    args = parser.parse_args()

    video_path = Path(args.video)
    gps_path = Path(args.gps_csv)

    # 1. Validate Input Video
    if not video_path.exists():
        print(f"[ERROR] Input video file does not exist: {video_path.resolve()}", file=sys.stderr)
        sys.exit(1)

    # 2. Validate & Load GPS Synchronizer
    gps_sync = None
    if gps_path.exists():
        try:
            print(f"[*] Initializing GPSVideoSynchronizer with {gps_path}...")
            gps_sync = GPSVideoSynchronizer(
                gps_source=gps_path,
                bus_id="BUS_101",
                camera_id="CAM_FRONT_01",
            )
            print(f" [✓] Loaded {len(gps_sync.gps_df)} synchronized GPS records.")
        except Exception as e:
            print(f"[WARN] Failed to load GPS CSV ({e}). Proceeding without GPS sync.")
    else:
        print(f"[WARN] GPS CSV not found at {gps_path}. Proceeding with default spatial coordinates.")

    print("==================================================================")
    print(" BusSense-AI | Vehicle Tracking & Traffic Density Estimation")
    print(" (PROTOTYPE ESTIMATION — NOT SCIENTIFICALLY CALIBRATED)")
    print("==================================================================")
    print(f" Video Path:         {video_path}")
    print(f" GPS Trajectory:     {gps_path if gps_sync else 'None (Fallback)'}")
    print(f" YOLO Model:         {args.model} (ByteTrack Tracker)")
    print(f" Inference Imgsz:    {args.imgsz}")
    print(f" Confidence:         {args.conf}")
    print(f" Time Interval:      {args.interval_seconds}s")
    print(f" Output Video:       {args.out_video}")
    print(f" Output JSON:        {args.out_json}")
    print(f" Max Frames:         {args.max_frames if args.max_frames > 0 else 'All'}")
    print("==================================================================\n")

    # 3. Initialize Tracker
    try:
        tracker = VehicleTracker(
            model_path=args.model,
            conf_threshold=args.conf,
            tracker_type="bytetrack.yaml",
            interval_seconds=args.interval_seconds,
            imgsz=args.imgsz,
            device="cpu",
        )
    except Exception as e:
        print(f"[ERROR] Failed to initialize VehicleTracker: {e}", file=sys.stderr)
        sys.exit(1)

    # 4. Process Video Feed
    try:
        max_f = args.max_frames if args.max_frames > 0 else None
        summary = tracker.process_video(
            video_path=video_path,
            gps_synchronizer=gps_sync,
            output_video_path=args.out_video,
            output_json_path=args.out_json,
            interval_seconds=args.interval_seconds,
            max_frames=max_f,
            conf_threshold=args.conf,
            imgsz=args.imgsz,
            show_progress=True,
        )

        print("\n==================================================================")
        print(" Tracking & Density Estimation Processing Completed")
        print("==================================================================")
        meta = summary["metadata"]
        stats = summary["aggregate_statistics"]
        print(f" Total Frames Processed:      {meta['total_frames_processed']}")
        print(f" Total Unique Vehicles Counted: {stats['total_unique_vehicles_counted']}")
        print(f" Unique Counts Breakdown:     {stats['unique_counts_by_type']}")
        print(f" Interval Measurements:       {stats['total_interval_measurements']}")
        print(f" Density Distribution:        {stats['density_distribution']}")
        print(f" Average Inference Speed:     {meta['average_inference_fps']} FPS")
        print(f" Total Processing Time:       {meta['processing_time_seconds']}s")
        print(f"\n [OK] Annotated tracking video saved: {args.out_video}")
        print(f" [OK] Structured density JSON saved:  {args.out_json}")
        print("==================================================================")

        # Print sample interval
        if summary["interval_measurements"]:
            print("\nSample Interval Traffic Measurement:")
            sample = summary["interval_measurements"][min(10, len(summary["interval_measurements"]) - 1)]
            print(f" - Interval #{sample['interval_index']} (Time: {sample['video_timestamp_start']}s - {sample['video_timestamp_end']}s)")
            print(f"   GPS Position:  ({sample['latitude']:.5f}, {sample['longitude']:.5f}) | Speed: {sample['speed_kmh']:.1f} km/h")
            print(f"   Vehicle Count: Total: {sample['total_vehicle_count']} (Cars: {sample['car_count']}, Buses: {sample['bus_count']}, Trucks: {sample['truck_count']}, Motos: {sample['motorcycle_count']}, Bikes: {sample['bicycle_count']})")
            print(f"   Density Level: [{sample['traffic_density']}] (Prototype Estimation)")
            print(f"   Track IDs:     {sample['unique_interval_track_ids']}")

    except Exception as e:
        print(f"\n[ERROR] Tracking pipeline execution failed: {e}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
