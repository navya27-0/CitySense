"""Standalone CLI Runner for Incident Detection Engine.

Integrates vehicle detection, ByteTrack tracking, ANPR plate extraction,
GPSVideoSynchronizer telemetry, and rule-based heuristic event detection.

Usage:
    python scripts/test_incident_detection.py --video data/videos/road_test.mp4 --gps-csv data/gps/BUS_101.csv
"""

import sys
import argparse
import logging
from pathlib import Path
import json

# Ensure project root is in sys.path
PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from ai.incident_detection import (
    IncidentDetector,
    IncidentConfig,
    IncidentRecord,
    DISCLAIMER_TEXT,
)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger("IncidentRunner")


def parse_args():
    parser = argparse.ArgumentParser(
        description="BusSense-AI Incident Detection CLI Runner",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    parser.add_argument(
        "--video",
        type=str,
        default=str(PROJECT_ROOT / "data" / "videos" / "road_test.mp4"),
        help="Path to input video file",
    )
    parser.add_argument(
        "--gps-csv",
        type=str,
        default=str(PROJECT_ROOT / "data" / "gps" / "BUS_101.csv"),
        help="Path to GPS trajectory CSV file",
    )
    parser.add_argument(
        "--out-video",
        type=str,
        default=str(PROJECT_ROOT / "data" / "outputs" / "incident_detection_output.mp4"),
        help="Path for output annotated video",
    )
    parser.add_argument(
        "--out-json",
        type=str,
        default=str(PROJECT_ROOT / "data" / "outputs" / "incident_records.json"),
        help="Path for structured incident records JSON",
    )
    parser.add_argument(
        "--out-dir",
        type=str,
        default=str(PROJECT_ROOT / "data" / "outputs" / "incidents"),
        help="Directory to save tri-panel evidence cards",
    )
    parser.add_argument(
        "--bus-id",
        type=str,
        default="BUS_101",
        help="Transit bus identifier",
    )
    parser.add_argument(
        "--conf",
        type=float,
        default=0.25,
        help="Detection confidence threshold",
    )
    parser.add_argument(
        "--imgsz",
        type=int,
        default=640,
        help="YOLO inference image size",
    )
    parser.add_argument(
        "--max-frames",
        type=int,
        default=None,
        help="Maximum frames to process (None for entire video)",
    )
    parser.add_argument(
        "--enable-ocr",
        action="store_true",
        default=False,
        help="Enable OCR license plate recognition (slower, disabled by default for real-time incident detection)",
    )
    parser.add_argument(
        "--device",
        type=str,
        default="cpu",
        help="Inference compute device (cpu, cuda, mps)",
    )
    return parser.parse_args()


def main():
    args = parse_args()

    print("=" * 80)
    print(" BusSense-AI — Incident Detection Engine Runner (SIH26124)")
    print(f" NOTE: {DISCLAIMER_TEXT.upper()}")
    print("=" * 80)
    print(f" Input Video:    {args.video}")
    print(f" GPS CSV:        {args.gps_csv}")
    print(f" Output Video:   {args.out_video}")
    print(f" Output JSON:    {args.out_json}")
    print(f" Evidence Dir:   {args.out_dir}")
    print(f" Bus ID:         {args.bus_id}")
    print(f" OCR Enabled:    {args.enable_ocr}")
    print("=" * 80)

    config = IncidentConfig()

    detector = IncidentDetector(
        config=config,
        vehicle_model="yolov8n.pt",
        plate_model="models/number_plates/best.pt",
        conf_threshold=args.conf,
        bus_id=args.bus_id,
        device=args.device,
        imgsz=args.imgsz,
        enable_ocr=args.enable_ocr,
    )

    summary = detector.process_video(
        video_path=args.video,
        output_video_path=args.out_video,
        output_json_path=args.out_json,
        output_evidence_dir=args.out_dir,
        gps_csv_path=args.gps_csv,
        max_frames=args.max_frames,
    )

    print("\n" + "=" * 80)
    print(" Incident Detection Processing Summary")
    print("=" * 80)
    print(f" Total Frames Processed:   {summary['total_frames_processed']}")
    print(f" Total Incidents Detected: {summary['total_incidents_detected']}")
    for inc_type, count in summary["incidents_by_type"].items():
        print(f"  - {inc_type}: {count}")
    print(f" Annotated Video:          {args.out_video}")
    print(f" Records JSON:             {args.out_json}")
    print(f" Evidence Images:          {args.out_dir}")
    print("=" * 80)


if __name__ == "__main__":
    main()
