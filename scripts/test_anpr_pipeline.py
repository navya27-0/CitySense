"""Standalone Verification Runner for Number-Plate Recognition (ANPR) Pipeline.

Executes end-to-end ANPR on an MP4 video feed with GPS synchronization:
Vehicle Detection -> Tracking -> Number-Plate Localization -> EasyOCR -> Normalization -> GPS Tagging -> Evidence Cards.

Usage:
    python scripts/test_anpr_pipeline.py [--video data/videos/road_test.mp4] [--gps-csv data/gps/BUS_101.csv]

Outputs:
    - data/outputs/anpr_output.mp4
    - data/outputs/anpr_incident_records.json
    - data/outputs/plates/plate_<BUS_ID>_trk<TRK_ID>_<FRAME>.jpg
"""

import sys
import argparse
from pathlib import Path

# Add project root to sys.path
PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from ai.pipeline.gps_sync import GPSVideoSynchronizer
from ai.anpr import ANPRPipeline

DEFAULT_VIDEO_PATH = PROJECT_ROOT / "data" / "videos" / "road_test.mp4"
DEFAULT_GPS_CSV = PROJECT_ROOT / "data" / "gps" / "BUS_101.csv"
DEFAULT_OUT_VIDEO = PROJECT_ROOT / "data" / "outputs" / "anpr_output.mp4"
DEFAULT_OUT_JSON = PROJECT_ROOT / "data" / "outputs" / "anpr_incident_records.json"
DEFAULT_PLATES_DIR = PROJECT_ROOT / "data" / "outputs" / "plates"


def main():
    parser = argparse.ArgumentParser(
        description="Run Automatic Number-Plate Recognition (ANPR) on video feed with GPS integration."
    )
    parser.add_argument(
        "--video",
        type=str,
        default=str(DEFAULT_VIDEO_PATH),
        help=f"Path to input MP4 video file (default: {DEFAULT_VIDEO_PATH})",
    )
    parser.add_argument(
        "--gps-csv",
        type=str,
        default=str(DEFAULT_GPS_CSV),
        help=f"Path to synchronized GPS CSV trajectory (default: {DEFAULT_GPS_CSV})",
    )
    parser.add_argument(
        "--out-video",
        "--output-video",
        dest="out_video",
        type=str,
        default=str(DEFAULT_OUT_VIDEO),
        help=f"Path to output annotated video (default: {DEFAULT_OUT_VIDEO})",
    )
    parser.add_argument(
        "--out-json",
        "--output-json",
        dest="out_json",
        type=str,
        default=str(DEFAULT_OUT_JSON),
        help=f"Path to output structured incident records JSON (default: {DEFAULT_OUT_JSON})",
    )
    parser.add_argument(
        "--plates-dir",
        type=str,
        default=str(DEFAULT_PLATES_DIR),
        help=f"Directory to save tri-panel evidence cards (default: {DEFAULT_PLATES_DIR})",
    )
    parser.add_argument(
        "--bus-id",
        type=str,
        default="BUS_101",
        help="Transit fleet bus identifier (default: BUS_101)",
    )
    parser.add_argument(
        "--conf",
        type=float,
        default=0.25,
        help="Detection confidence threshold (default: 0.25)",
    )
    parser.add_argument(
        "--max-frames",
        type=int,
        default=150,
        help="Maximum frames to process (default: 150, 0 = entire video)",
    )

    args = parser.parse_args()

    video_path = Path(args.video)
    gps_path = Path(args.gps_csv)

    # 1. Validate Input Video
    if not video_path.exists():
        # Fallback to sample_bus_feed.mp4 if road_test is not found
        fallback_video = PROJECT_ROOT / "data" / "videos" / "sample_bus_feed.mp4"
        if fallback_video.exists():
            print(f"[WARN] Video {video_path} not found. Falling back to {fallback_video}")
            video_path = fallback_video
        else:
            print(f"[ERROR] Input video does not exist: {video_path.resolve()}", file=sys.stderr)
            sys.exit(1)

    # 2. Validate & Load GPS Synchronizer
    gps_sync = None
    if gps_path.exists():
        try:
            print(f"[*] Initializing GPSVideoSynchronizer with {gps_path}...")
            gps_sync = GPSVideoSynchronizer(
                gps_source=gps_path,
                bus_id=args.bus_id,
                camera_id="CAM_FRONT_01",
            )
            print(f" [✓] Loaded {len(gps_sync.gps_df)} synchronized GPS records.")
        except Exception as e:
            print(f"[WARN] Failed to load GPS CSV ({e}). Operating with default spatial coordinates.")
    else:
        print(f"[WARN] GPS CSV not found at {gps_path}. Operating with default coordinates.")

    print("==================================================================")
    print(" BusSense-AI | Automatic Number-Plate Recognition (ANPR) Pipeline")
    print("==================================================================")
    print(f" Video Path:         {video_path}")
    print(f" GPS Trajectory:     {gps_path if gps_sync else 'Default Fallback'}")
    print(f" Transit Bus ID:     {args.bus_id}")
    print(f" Detection Conf:     {args.conf}")
    print(f" Output Video:       {args.out_video}")
    print(f" Output Records JSON:{args.out_json}")
    print(f" Evidence Frames Dir:{args.plates_dir}")
    print(f" Max Frames:         {args.max_frames if args.max_frames > 0 else 'All'}")
    print("==================================================================\n")

    # 3. Initialize ANPR Pipeline
    try:
        pipeline = ANPRPipeline(
            vehicle_model="yolov8n.pt",
            plate_model="models/number_plates/best.pt",
            conf_threshold=args.conf,
            bus_id=args.bus_id,
            device="cpu",
            imgsz=640,
        )
    except Exception as e:
        print(f"[ERROR] Failed to initialize ANPR pipeline: {e}", file=sys.stderr)
        sys.exit(1)

    # 4. Process Video Stream
    try:
        max_f = args.max_frames if args.max_frames > 0 else None
        summary = pipeline.process_video(
            video_path=video_path,
            gps_synchronizer=gps_sync,
            output_video_path=args.out_video,
            output_json_path=args.out_json,
            output_evidence_dir=args.plates_dir,
            max_frames=max_f,
            conf_threshold=args.conf,
            show_progress=True,
        )

        print("\n==================================================================")
        print(" ANPR Processing Completed Successfully")
        print("==================================================================")
        meta = summary["metadata"]
        stats = summary["aggregate_statistics"]
        print(f" Total Frames Processed:        {meta['total_frames_processed']}")
        print(f" Total Unique Vehicles Tracked: {stats['total_unique_vehicles_tracked']}")
        print(f" Total Plate Detections Logged: {stats['total_plate_detections_logged']}")
        print(f" Unique Vehicles with Plates:   {stats['unique_vehicles_with_plates']}")
        print(f" Valid Format Plates Count:     {stats['valid_format_plates_count']}")
        print(f" Valid Plates Recognized:       {stats['valid_plates_list']}")
        print(f" Average Processing Speed:      {meta['average_inference_fps']} FPS")
        print(f" Total Processing Time:         {meta['processing_time_seconds']}s")
        print(f"\n [✓] Annotated video saved:     {args.out_video}")
        print(f" [✓] Structured JSON saved:      {args.out_json}")
        print(f" [✓] Evidence frames saved in:   {args.plates_dir}")
        print("==================================================================")

        # Print sample deduplicated plate records
        sample_records = summary["deduplicated_plate_incidents"]
        if sample_records:
            print(f"\nSample Recognized Number Plate Incidents (Top {min(3, len(sample_records))}):")
            for i, rec in enumerate(sample_records[:3], 1):
                status_badge = "VALID" if rec['is_valid_format'] else f"REJECTED ({rec['rejection_reason']})"
                print(f" {i}. Vehicle #{rec['vehicle_tracking_id']} ({rec['vehicle_type'].upper()})")
                print(f"    - Normalized Plate: {rec['normalized_result']} [{status_badge}]")
                print(f"    - Raw OCR Text:     '{rec['raw_ocr_result']}' (Confidence: {rec['ocr_confidence']*100:.1f}%)")
                print(f"    - GPS Position:     ({rec['latitude']:.5f}, {rec['longitude']:.5f}) at {rec['timestamp']}")
                print(f"    - Evidence Card:    {rec['image_path']}")

    except Exception as e:
        print(f"\n[ERROR] ANPR execution failed: {e}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
