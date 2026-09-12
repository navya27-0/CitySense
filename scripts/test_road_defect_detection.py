"""Standalone Road Defect Detection Verification Runner for BusSense-AI.

Detects potholes, damaged roads, missing dividers, missing zebra crossings, damaged signboards,
and waterlogging. Attaches GPS coordinates via GPSVideoSynchronizer and exports evidence frames.

Usage:
    python scripts/test_road_defect_detection.py [--video data/videos/road_test.mp4] [--gps-csv data/gps/BUS_101.csv]

Outputs:
    - data/outputs/road_defect_output.mp4
    - data/outputs/road_defect_events.json
    - data/outputs/events/roaddefect_<BUS>_<TYPE>_<FRAME>.jpg

DISCLAIMER: Prototype road-defect estimation for hackathon demonstration.
"""

import sys
import argparse
from pathlib import Path

# Add project root to sys.path
PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from ai.pipeline.gps_sync import GPSVideoSynchronizer
from ai.road_defect_detection import RoadDefectDetector

DEFAULT_VIDEO_PATH = PROJECT_ROOT / "data" / "videos" / "road_test.mp4"
DEFAULT_GPS_CSV = PROJECT_ROOT / "data" / "gps" / "BUS_101.csv"
DEFAULT_OUT_VIDEO = PROJECT_ROOT / "data" / "outputs" / "road_defect_output.mp4"
DEFAULT_OUT_JSON = PROJECT_ROOT / "data" / "outputs" / "road_defect_events.json"
DEFAULT_EVENTS_DIR = PROJECT_ROOT / "data" / "outputs" / "events"
DEFAULT_MODEL_PATH = PROJECT_ROOT / "models" / "road_defects" / "best.pt"


def main():
    parser = argparse.ArgumentParser(
        description="Run urban road defect detection pipeline on video with GPS synchronization."
    )
    parser.add_argument(
        "--video",
        type=str,
        default=str(DEFAULT_VIDEO_PATH),
        help=f"Path to input video (default: {DEFAULT_VIDEO_PATH})",
    )
    parser.add_argument(
        "--gps-csv",
        type=str,
        default=str(DEFAULT_GPS_CSV),
        help=f"Path to input GPS CSV (default: {DEFAULT_GPS_CSV})",
    )
    parser.add_argument(
        "--model",
        type=str,
        default=str(DEFAULT_MODEL_PATH),
        help=f"Path to custom trained YOLO road defect model (default: {DEFAULT_MODEL_PATH})",
    )
    parser.add_argument(
        "--conf",
        type=float,
        default=0.30,
        help="Confidence detection threshold (default: 0.30)",
    )
    parser.add_argument(
        "--bus-id",
        type=str,
        default="BUS_101",
        help="Bus unit identifier (default: BUS_101)",
    )
    parser.add_argument(
        "--out-video",
        "--output-video",
        dest="out_video",
        type=str,
        default=str(DEFAULT_OUT_VIDEO),
        help=f"Path to save output video (default: {DEFAULT_OUT_VIDEO})",
    )
    parser.add_argument(
        "--out-json",
        "--output-json",
        dest="out_json",
        type=str,
        default=str(DEFAULT_OUT_JSON),
        help=f"Path to save structured events JSON (default: {DEFAULT_OUT_JSON})",
    )
    parser.add_argument(
        "--events-dir",
        type=str,
        default=str(DEFAULT_EVENTS_DIR),
        help=f"Directory to store evidence frame images (default: {DEFAULT_EVENTS_DIR})",
    )
    parser.add_argument(
        "--max-frames",
        type=int,
        default=200,
        help="Maximum frames to process (default: 200, 0 = full video)",
    )

    args = parser.parse_args()

    video_path = Path(args.video)
    gps_path = Path(args.gps_csv)

    # 1. Validate Input Video
    if not video_path.exists():
        # Fallback check if road_test.mp4.mp4 exists
        alt_path = Path(str(video_path) + ".mp4")
        if alt_path.exists():
            video_path = alt_path
        else:
            print(f"[ERROR] Input video file does not exist: {video_path.resolve()}", file=sys.stderr)
            sys.exit(1)

    # 2. Validate GPS Synchronizer
    gps_sync = None
    if gps_path.exists():
        try:
            print(f"[*] Initializing GPSVideoSynchronizer with {gps_path}...")
            gps_sync = GPSVideoSynchronizer(
                gps_source=gps_path,
                bus_id=args.bus_id,
                camera_id="CAM_FRONT_01",
            )
            print(f" [OK] Loaded {len(gps_sync.gps_df)} synchronized GPS records.")
        except Exception as e:
            print(f"[WARN] Failed loading GPS CSV ({e}). Proceeding without GPS sync.")
    else:
        print(f"[WARN] GPS CSV not found at {gps_path}. Default spatial coordinates will be used.")

    print("==================================================================")
    print(" BusSense-AI | Urban Road-Defect & Infrastructure Detection")
    print("==================================================================")
    print(f" Video Path:         {video_path}")
    print(f" GPS Trajectory:     {gps_path if gps_sync else 'Fallback Coordinates'}")
    print(f" Model Weights:      {args.model}")
    print(f" Confidence Filter:  {args.conf}")
    print(f" Bus Unit ID:        {args.bus_id}")
    print(f" Target Subtypes:    Potholes, Damaged Road, Missing Dividers,")
    print(f"                     Missing Zebra Crossings, Damaged Signboards, Waterlogging")
    print(f" Output Video Path:  {args.out_video}")
    print(f" Output JSON Path:   {args.out_json}")
    print(f" Evidence Frames:    {args.events_dir}")
    print(f" Max Frames:         {args.max_frames if args.max_frames > 0 else 'All'}")
    print("==================================================================\n")

    # 3. Initialize Detector
    try:
        detector = RoadDefectDetector(
            model_path=args.model,
            conf_threshold=args.conf,
            bus_id=args.bus_id,
            evidence_dir=args.events_dir,
            save_evidence=True,
            enable_demo_fallback=True,
            device="cpu",
        )
    except Exception as e:
        print(f"[ERROR] Failed to initialize RoadDefectDetector: {e}", file=sys.stderr)
        sys.exit(1)

    # 4. Process Video Feed
    try:
        max_f = args.max_frames if args.max_frames > 0 else None
        summary = detector.process_video(
            video_path=video_path,
            gps_synchronizer=gps_sync,
            output_video_path=args.out_video,
            output_json_path=args.out_json,
            max_frames=max_f,
            conf_threshold=args.conf,
            show_progress=True,
        )

        print("\n==================================================================")
        print(" Road Defect Detection Completed Successfully")
        print("==================================================================")
        meta = summary["metadata"]
        stats = summary["aggregate_statistics"]
        print(f" Model Source:              {meta['model_source']}")
        print(f" Custom Weights Loaded:     {meta['custom_weights_loaded']}")
        print(f" Total Frames Processed:    {meta['total_frames_processed']}")
        print(f" Total Urban Events Logged: {stats['total_events_logged']}")
        print(f" Breakdown by Subtype:      {stats['events_by_subtype']}")
        print(f" Breakdown by Severity:     {stats['events_by_severity']}")
        print(f" Average Processing FPS:    {meta['average_inference_fps']} FPS")
        print(f" Total Processing Time:     {meta['processing_time_seconds']}s")
        print(f"\n [OK] Annotated video saved:  {args.out_video}")
        print(f" [OK] Structured JSON saved:   {args.out_json}")
        print(f" [OK] Evidence frames saved in: {args.events_dir}")
        print("==================================================================")

        # Print sample event
        if summary["events"]:
            print("\nSample Logged Road Defect Event:")
            sample = summary["events"][0]
            print(f" - Event ID:     {sample['event_id']}")
            print(f"   Subtype:      {sample['event_type']} (Severity: {sample['severity'].upper()})")
            print(f"   Confidence:   {sample['confidence']:.2f}")
            print(f"   Time/GPS:     Frame {sample['frame_number']} ({sample['video_timestamp']}s) @ ({sample['latitude']:.5f}, {sample['longitude']:.5f})")
            print(f"   Evidence Img: {sample['image_path']}")
            print(f"   Bounding Box: {sample['bounding_box']}")

    except Exception as e:
        print(f"\n[ERROR] Road defect pipeline execution failed: {e}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
