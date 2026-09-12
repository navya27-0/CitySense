"""Standalone Vehicle Detection Runner & Verification Script for BusSense-AI.

Processes input MP4 video using lightweight YOLOv8 Nano model, detects vehicles
(car, bus, truck, motorcycle, bicycle), annotates bounding boxes and HUD counters,
and exports structured JSON and annotated MP4 video.

Usage:
    python scripts/test_vehicle_detection.py [--video data/videos/sample_bus_feed.mp4] [--model yolov8n.pt] [--conf 0.35]

Outputs:
    - data/outputs/vehicle_detection_output.mp4
    - data/outputs/vehicle_detections.json

NOTE: STANDALONE EDGE AI MODULE FOR HACKATHON PROTOTYPE DEMONSTRATION.
"""

import sys
import argparse
import time
from pathlib import Path

# Add project root to sys.path
PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from ai.vehicle_detection import VehicleDetector

DEFAULT_VIDEO_PATH = PROJECT_ROOT / "data" / "videos" / "sample_bus_feed.mp4"
DEFAULT_OUTPUT_VIDEO = PROJECT_ROOT / "data" / "outputs" / "vehicle_detection_output.mp4"
DEFAULT_OUTPUT_JSON = PROJECT_ROOT / "data" / "outputs" / "vehicle_detections.json"
MODELS_DIR = PROJECT_ROOT / "models"


def main():
    parser = argparse.ArgumentParser(description="Run YOLO vehicle detection on an MP4 video feed.")
    parser.add_argument(
        "--video",
        type=str,
        default=str(DEFAULT_VIDEO_PATH),
        help="Path to input MP4 video file (default: data/videos/sample_bus_feed.mp4)",
    )
    parser.add_argument(
        "--model",
        type=str,
        default="yolov8n.pt",
        help="YOLO model checkpoint or weight file (default: yolov8n.pt)",
    )
    parser.add_argument(
        "--conf",
        type=float,
        default=0.35,
        help="Confidence detection threshold (default: 0.35)",
    )
    parser.add_argument(
        "--out-video",
        "--output-video",
        dest="out_video",
        type=str,
        default=str(DEFAULT_OUTPUT_VIDEO),
        help="Path to save annotated output MP4 video",
    )
    parser.add_argument(
        "--out-json",
        "--output-json",
        dest="out_json",
        type=str,
        default=str(DEFAULT_OUTPUT_JSON),
        help="Path to save structured JSON detections output",
    )
    parser.add_argument(
        "--imgsz",
        type=int,
        default=640,
        help="Inference resolution (default: 640)",
    )
    parser.add_argument(
        "--max-frames",
        type=int,
        default=0,
        help="Optional limit on frames to process (0 = entire video)",
    )
    args = parser.parse_args()

    video_path = Path(args.video)

    # If default sample video doesn't exist, generate it automatically
    if not video_path.exists() and video_path == DEFAULT_VIDEO_PATH:
        print(f"[*] Sample video not found at {video_path}. Generating realistic synthetic traffic video...")
        from scripts.generate_sample_traffic_video import generate_traffic_video
        generate_traffic_video(output_path=DEFAULT_VIDEO_PATH, num_frames=120)

    # 1. Validate Input Video File
    if not video_path.exists():
        print(f"[ERROR] Input video file does not exist: {video_path.resolve()}", file=sys.stderr)
        print("        Please provide a valid MP4 file using --video <path_to_video.mp4>", file=sys.stderr)
        sys.exit(1)

    print("==================================================================")
    print(" BusSense-AI | Edge AI Vehicle Detection & Counting Pipeline")
    print("==================================================================")
    print(f" Input Video:        {video_path}")
    print(f" YOLO Model:         {args.model} (Lightweight Nano variant)")
    print(f" Inference Imgsz:    {args.imgsz}")
    print(f" Confidence Filter:  {args.conf}")
    print(f" Target Classes:     Car, Bus, Truck, Motorcycle, Bicycle")
    print(f" Output Video Path:  {args.out_video}")
    print(f" Output JSON Path:   {args.out_json}")
    print("==================================================================\n")

    # 2. Initialize Detector
    try:
        detector = VehicleDetector(
            model_path=args.model,
            conf_threshold=args.conf,
            imgsz=args.imgsz,
            device="cpu",
        )
    except Exception as e:
        print(f"[ERROR] Failed to initialize YOLO vehicle detector: {e}", file=sys.stderr)
        sys.exit(1)

    # 3. Process Video
    try:
        max_f = args.max_frames if args.max_frames > 0 else None
        summary = detector.process_video(
            video_path=video_path,
            output_video_path=args.out_video,
            output_json_path=args.out_json,
            max_frames=max_f,
            conf_threshold=args.conf,
            show_progress=True,
        )

        print("\n==================================================================")
        print(" Detection Processing Completed Successfully")
        print("==================================================================")
        meta = summary["metadata"]
        stats = summary["aggregate_statistics"]
        print(f" Total Frames Processed:   {meta['total_frames_processed']}")
        print(f" Total Detections Count:   {stats['total_vehicle_detections']}")
        print(f" Average Vehicles / Frame: {stats['average_vehicles_per_frame']}")
        print(f" Class Breakdown:          {stats['cumulative_counts_by_type']}")
        print(f" Average Inference Speed:  {meta['average_inference_fps']:.1f} FPS")
        print(f" Processing Time:          {meta['processing_time_seconds']}s")
        print(f"\n [✓] Annotated video saved: {args.out_video}")
        print(f" [✓] Structured JSON saved: {args.out_json}")
        print("==================================================================")

    except Exception as e:
        print(f"\n[ERROR] Video processing pipeline failed: {e}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
