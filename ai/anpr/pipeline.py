"""Automatic Number-Plate Recognition (ANPR) Pipeline for BusSense-AI.

================================================================================
PIPELINE ARCHITECTURE:
================================================================================
Video Stream
  │
  ▼ [1. Vehicle Detection & Tracking] (Ultralytics YOLOv8 + ByteTrack)
Persistent Vehicle Bounding Box & Track ID
  │
  ▼ [2. Number-Plate Localization] (Custom Plate YOLO / Adaptive Morphological Extractor)
Cropped License Plate Region
  │
  ▼ [3. OCR Text Extraction] (CLAHE/Bilateral Preprocessing + EasyOCR)
Raw OCR String & Character Confidence
  │
  ▼ [4. Positional Confusion Matrix & Normalization] (PlateValidator)
Normalized Indian Registration Number & Format Validation (Standard / BH Series)
  │
  ▼ [5. Video-GPS Synchronization] (GPSVideoSynchronizer Single Source of Truth)
Geographic Coordinates (Latitude, Longitude, Speed, Heading)
  │
  ▼ [6. Incident Record & Evidence Generation]
Structured Incident Record JSON + Annotated Tri-Panel Evidence Frame (.jpg)
================================================================================
"""

import os
import sys
import time
import logging
from pathlib import Path
from dataclasses import dataclass, field, asdict
from typing import List, Dict, Any, Optional, Union, Tuple, Set
import numpy as np
import cv2
import json

from ai.pipeline.gps_sync import GPSVideoSynchronizer
from ai.tracking.tracker import VehicleTracker, FrameTrackingResult, TrackedVehicleDetection
from ai.anpr.plate_detector import PlateDetector, PlateDetection
from ai.anpr.ocr_engine import OCREngine, PlateOCRResult
from ai.anpr.validator import PlateValidator, ValidationResult

logger = logging.getLogger(__name__)


@dataclass
class PlateIncidentRecord:
    """Represents a validated number plate recognition event with GPS position."""
    event_id: str
    bus_id: str
    frame_number: int
    video_timestamp: float
    timestamp: str  # ISO-8601 UTC timestamp from GPSVideoSynchronizer
    latitude: float
    longitude: float
    speed_kmh: float
    heading_deg: float
    vehicle_tracking_id: int
    vehicle_type: str
    raw_ocr_result: str
    normalized_result: str
    ocr_confidence: float
    is_valid_format: bool
    plate_type: str
    state_code: Optional[str] = None
    rejection_reason: Optional[str] = None
    plate_bounding_box: List[int] = field(default_factory=list)  # [px1, py1, px2, py2]
    vehicle_bounding_box: List[int] = field(default_factory=list)  # [vx1, vy1, vx2, vy2]
    image_path: Optional[str] = None
    is_simulated: bool = True

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


class ANPRPipeline:
    """End-to-end edge AI Automatic Number-Plate Recognition (ANPR) pipeline."""

    def __init__(
        self,
        vehicle_model: Union[str, Path] = "yolov8n.pt",
        plate_model: Union[str, Path] = "models/number_plates/best.pt",
        conf_threshold: float = 0.25,
        ocr_languages: Optional[List[str]] = None,
        gpu: bool = False,
        bus_id: str = "BUS_101",
        device: str = "cpu",
        imgsz: int = 640,
    ):
        """Initializes the ANPR pipeline.

        Args:
            vehicle_model: Model checkpoint or path for vehicle detection.
            plate_model: Model checkpoint or path for custom plate detection.
            conf_threshold: Detection confidence threshold.
            ocr_languages: Languages for EasyOCR (default: ['en']).
            gpu: Enable GPU acceleration for OCR.
            bus_id: Identifier of the capturing transit bus.
            device: Compute device ('cpu', 'cuda', 'mps').
            imgsz: Input resolution for vehicle detection inference (default: 640).
        """
        self.bus_id = bus_id
        self.conf_threshold = conf_threshold
        self.device = device
        self.imgsz = imgsz

        logger.info("Initializing ANPR Vehicle Tracker...")
        self.tracker = VehicleTracker(
            model_path=vehicle_model,
            conf_threshold=conf_threshold,
            device=device,
            imgsz=imgsz,
        )

        logger.info("Initializing ANPR Plate Detector...")
        self.plate_detector = PlateDetector(
            custom_weights_path=plate_model,
            conf_threshold=conf_threshold,
            device=device,
        )

        logger.info("Initializing ANPR OCR Engine...")
        self.ocr_engine = OCREngine(
            languages=ocr_languages or ["en"],
            gpu=gpu,
            min_confidence=0.20,
        )

        self.validator = PlateValidator()
        self.reset_state()

    def reset_state(self) -> None:
        """Resets tracking histories and recognized plate caches."""
        self.tracker.reset_state()
        # Cache of best OCR record per track_id: track_id -> PlateIncidentRecord
        self.best_plate_records: Dict[int, PlateIncidentRecord] = {}
        # Frame counter for plate event UUID generation
        self._record_seq = 1

    def process_frame(
        self,
        frame: np.ndarray,
        frame_number: int = 0,
        video_timestamp: float = 0.0,
        gps_synchronizer: Optional[GPSVideoSynchronizer] = None,
        output_evidence_dir: Optional[Union[str, Path]] = None,
    ) -> Tuple[FrameTrackingResult, List[PlateIncidentRecord]]:
        """Executes full ANPR pipeline on a single frame.

        Args:
            frame: BGR numpy image frame.
            frame_number: Frame sequence index.
            video_timestamp: Video playback timestamp in seconds.
            gps_synchronizer: Instance of GPSVideoSynchronizer.
            output_evidence_dir: Directory path to save generated evidence images.

        Returns:
            Tuple of (FrameTrackingResult, List of new/updated PlateIncidentRecords).
        """
        if frame is None or frame.size == 0:
            raise ValueError("Input frame is invalid or empty.")

        # 1. Track Vehicles with ByteTrack
        track_res = self.tracker.track_frame(
            frame=frame,
            frame_number=frame_number,
            video_timestamp=video_timestamp,
            conf_threshold=self.conf_threshold,
            imgsz=self.imgsz,
        )

        # 2. Extract GPS Coordinates via GPSVideoSynchronizer (Single Source of Truth)
        if gps_synchronizer is not None:
            pos = gps_synchronizer.get_position(video_timestamp=video_timestamp, interpolate=True)
            iso_time = pos.get("gps_timestamp") or pos.get("interpolated_timestamp") or ""
            lat = pos.get("latitude", 0.0)
            lon = pos.get("longitude", 0.0)
            spd = pos.get("speed", 0.0)
            hdg = pos.get("heading", 0.0)
        else:
            iso_time = "2026-09-09T00:00:00Z"
            lat, lon, spd, hdg = 17.3850, 78.4867, 0.0, 0.0

        current_frame_records: List[PlateIncidentRecord] = []

        # 3. Process each tracked vehicle
        for det in track_res.detections:
            t_id = det.track_id
            v_type = det.vehicle_type
            v_box = det.bounding_box

            # Localize number plate candidate
            plate_det = self.plate_detector.detect_plate_in_vehicle(
                frame=frame,
                vehicle_box=v_box,
                vehicle_type=v_type,
            )

            if plate_det is not None and plate_det.plate_crop.size > 0:
                # Perform OCR on localized plate crop
                ocr_res = self.ocr_engine.recognize_text(plate_det.plate_crop)

                if ocr_res.raw_text:
                    # Normalize & Validate against Indian Registration Rules
                    val_res = self.validator.validate_and_normalize(ocr_res.raw_text)

                    event_id = f"anpr_{self.bus_id}_{t_id:04d}_{frame_number:06d}"
                    evidence_path = None

                    # Generate and save evidence card only if this is the best valid detection for this track
                    prev_best = self.best_plate_records.get(t_id)
                    is_better = prev_best is None or (ocr_res.confidence > prev_best.ocr_confidence)

                    if output_evidence_dir is not None and is_better and val_res.is_valid_format:
                        out_dir = Path(output_evidence_dir)
                        out_dir.mkdir(parents=True, exist_ok=True)
                        file_name = f"plate_{self.bus_id}_trk{t_id:04d}_{frame_number:06d}.jpg"
                        target_file = out_dir / file_name
                        evidence_img = self.create_evidence_image(
                            frame=frame,
                            plate_det=plate_det,
                            val_res=val_res,
                            ocr_conf=ocr_res.confidence,
                            track_id=t_id,
                            vehicle_type=v_type,
                            timestamp_str=iso_time,
                            lat=lat,
                            lon=lon,
                        )
                        cv2.imwrite(str(target_file), evidence_img)
                        evidence_path = str(target_file)
                        if prev_best and prev_best.evidence_card_path:
                            try:
                                Path(prev_best.evidence_card_path).unlink(missing_ok=True)
                            except Exception:
                                pass
                    elif prev_best and prev_best.evidence_card_path:
                        evidence_path = prev_best.evidence_card_path

                    record = PlateIncidentRecord(
                        event_id=event_id,
                        bus_id=self.bus_id,
                        frame_number=frame_number,
                        video_timestamp=round(video_timestamp, 3),
                        timestamp=iso_time,
                        latitude=round(lat, 6),
                        longitude=round(lon, 6),
                        speed_kmh=round(spd, 2),
                        heading_deg=round(hdg, 1),
                        vehicle_tracking_id=t_id,
                        vehicle_type=v_type,
                        raw_ocr_result=val_res.raw_text,
                        normalized_result=val_res.normalized_text,
                        ocr_confidence=round(ocr_res.confidence, 3),
                        is_valid_format=val_res.is_valid_format,
                        plate_type=val_res.plate_type,
                        state_code=val_res.state_code,
                        rejection_reason=val_res.rejection_reason,
                        plate_bounding_box=plate_det.plate_box,
                        vehicle_bounding_box=v_box,
                        image_path=evidence_path,
                        is_simulated=True,
                    )

                    # Update best confidence record for this tracked vehicle
                    existing = self.best_plate_records.get(t_id)
                    if existing is None or (record.is_valid_format and not existing.is_valid_format) or (record.ocr_confidence > existing.ocr_confidence):
                        self.best_plate_records[t_id] = record

                    current_frame_records.append(record)

        return track_res, current_frame_records

    def create_evidence_image(
        self,
        frame: np.ndarray,
        plate_det: PlateDetection,
        val_res: ValidationResult,
        ocr_conf: float,
        track_id: int,
        vehicle_type: str,
        timestamp_str: str,
        lat: float,
        lon: float,
    ) -> np.ndarray:
        """Constructs an evidence card combining vehicle context, plate zoom, and metadata overlay."""
        card_w, card_h = 720, 360
        canvas = np.full((card_h, card_w, 3), (20, 24, 33), dtype=np.uint8)

        # 1. Left Panel: Scene Vehicle Crop with bounding box
        vx1, vy1, vx2, vy2 = plate_det.vehicle_box
        v_h, v_w = max(1, vy2 - vy1), max(1, vx2 - vx1)
        # Add small margin
        m_x = int(v_w * 0.15)
        m_y = int(v_h * 0.15)
        crop_x1 = max(0, vx1 - m_x)
        crop_y1 = max(0, vy1 - m_y)
        crop_x2 = min(frame.shape[1], vx2 + m_x)
        crop_y2 = min(frame.shape[0], vy2 + m_y)

        scene_crop = frame[crop_y1:crop_y2, crop_x1:crop_x2].copy()
        # Draw vehicle box and plate box on scene crop
        local_vx1 = vx1 - crop_x1
        local_vy1 = vy1 - crop_y1
        local_vx2 = vx2 - crop_x1
        local_vy2 = vy2 - crop_y1
        cv2.rectangle(scene_crop, (local_vx1, local_vy1), (local_vx2, local_vy2), (245, 130, 48), 2)

        px1, py1, px2, py2 = plate_det.plate_box
        local_px1 = max(0, px1 - crop_x1)
        local_py1 = max(0, py1 - crop_y1)
        local_px2 = min(scene_crop.shape[1], px2 - crop_x1)
        local_py2 = min(scene_crop.shape[0], py2 - crop_y1)
        cv2.rectangle(scene_crop, (local_px1, local_py1), (local_px2, local_py2), (34, 197, 94), 2)

        # Resize vehicle panel
        panel_w = 340
        panel_h = 240
        scene_resized = cv2.resize(scene_crop, (panel_w, panel_h))
        canvas[60:60 + panel_h, 20:20 + panel_w] = scene_resized
        cv2.rectangle(canvas, (20, 60), (20 + panel_w, 60 + panel_h), (51, 65, 85), 1)

        # 2. Right Panel: High-contrast cropped license plate zoom
        plate_crop = plate_det.plate_crop
        zoom_w = 320
        zoom_h = 100
        if plate_crop.size > 0:
            plate_resized = cv2.resize(plate_crop, (zoom_w, zoom_h))
            canvas[60:60 + zoom_h, 380:380 + zoom_w] = plate_resized
            cv2.rectangle(canvas, (380, 60), (380 + zoom_w, 60 + zoom_h), (34, 197, 94), 2)

        # 3. Top Banner
        cv2.putText(
            canvas,
            f"BusSense-AI | ANPR Evidence Record #{track_id:04d}",
            (20, 32),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.55,
            (56, 189, 248),
            2,
            cv2.LINE_AA,
        )
        badge_text = "VALID INDIAN FORMAT" if val_res.is_valid_format else "UNVALIDATED OCR FORMAT"
        badge_color = (34, 197, 94) if val_res.is_valid_format else (0, 165, 255)
        cv2.putText(
            canvas,
            f"[{badge_text}]",
            (420, 32),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.45,
            badge_color,
            1,
            cv2.LINE_AA,
        )

        # 4. Right Metadata Block (Under Plate Zoom)
        cv2.putText(canvas, f"PLATE: {val_res.normalized_text or val_res.raw_text}", (380, 190), cv2.FONT_HERSHEY_SIMPLEX, 0.70, (255, 255, 255), 2, cv2.LINE_AA)
        cv2.putText(canvas, f"Raw OCR: {val_res.raw_text} | Conf: {ocr_conf * 100:.1f}%", (380, 218), cv2.FONT_HERSHEY_SIMPLEX, 0.42, (148, 163, 184), 1, cv2.LINE_AA)
        cv2.putText(canvas, f"Vehicle: #{track_id} {vehicle_type.upper()}", (380, 244), cv2.FONT_HERSHEY_SIMPLEX, 0.45, (226, 232, 240), 1, cv2.LINE_AA)
        if val_res.rejection_reason:
            cv2.putText(canvas, f"Note: {val_res.rejection_reason[:36]}...", (380, 270), cv2.FONT_HERSHEY_SIMPLEX, 0.38, (0, 165, 255), 1, cv2.LINE_AA)
        elif val_res.state_code:
            cv2.putText(canvas, f"State: {val_res.state_code} | Type: {val_res.plate_type}", (380, 270), cv2.FONT_HERSHEY_SIMPLEX, 0.40, (34, 197, 94), 1, cv2.LINE_AA)

        # 5. Bottom Footer (GPS & Timestamps)
        footer_y = 335
        cv2.line(canvas, (20, 310), (card_w - 20, 310), (51, 65, 85), 1)
        cv2.putText(canvas, f"Bus ID: {self.bus_id} | GPS: ({lat:.5f}, {lon:.5f}) | Time: {timestamp_str[:19]}", (20, footer_y), cv2.FONT_HERSHEY_SIMPLEX, 0.42, (203, 213, 225), 1, cv2.LINE_AA)

        return canvas

    def annotate_frame(
        self,
        frame: np.ndarray,
        track_res: FrameTrackingResult,
        records: List[PlateIncidentRecord],
    ) -> np.ndarray:
        """Renders license plate bounding boxes and OCR badges directly on the video frame with resolution-scaled typography."""
        annotated = self.tracker.annotate_frame(frame, track_res, show_hud=True, show_trails=True)
        h, w = annotated.shape[:2]

        res_scale = max(1.0, min(w, h * 16 // 9) / 1280.0)
        plate_box_thick = max(2, int(round(2.5 * res_scale)))
        font_scale = max(0.55, 0.52 * res_scale)
        font_thick = max(1, int(round(1.5 * res_scale)))
        pad_x = int(6 * res_scale)
        pad_y = int(5 * res_scale)
        font = cv2.FONT_HERSHEY_SIMPLEX

        # 1. Render active frame plate bounding boxes and raw reading badges
        for rec in records:
            if rec.plate_bounding_box and len(rec.plate_bounding_box) == 4:
                px1, py1, px2, py2 = rec.plate_bounding_box
                badge_color = (34, 197, 94) if rec.is_valid_format else (0, 165, 255)
                cv2.rectangle(annotated, (px1, py1), (px2, py2), badge_color, plate_box_thick)

                plate_txt = f"{rec.normalized_result or rec.raw_ocr_result} ({int(rec.ocr_confidence * 100)}%)"
                (tw, th), _ = cv2.getTextSize(plate_txt, font, font_scale, font_thick)

                badge_y1 = max(0, py1 - th - 2 * pad_y)
                badge_y2 = py1
                badge_x2 = min(w, px1 + tw + 2 * pad_x)

                cv2.rectangle(annotated, (px1, badge_y1), (badge_x2, badge_y2), badge_color, -1)
                cv2.rectangle(annotated, (px1, badge_y1), (badge_x2, badge_y2), (15, 23, 42), max(1, int(res_scale)))
                # Outline + text
                cv2.putText(annotated, plate_txt, (px1 + pad_x, py1 - pad_y), font, font_scale, (0, 0, 0), font_thick + 2, cv2.LINE_AA)
                cv2.putText(annotated, plate_txt, (px1 + pad_x, py1 - pad_y), font, font_scale, (255, 255, 255), font_thick, cv2.LINE_AA)

        # 2. Render persistent track-level plate badges above vehicle bounding boxes
        for det in track_res.detections:
            t_id = det.track_id
            best_rec = self.best_plate_records.get(t_id)
            if best_rec is not None and (best_rec.normalized_result or best_rec.raw_ocr_result):
                vx1, vy1, vx2, vy2 = det.bounding_box
                plate_str = best_rec.normalized_result or best_rec.raw_ocr_result
                badge_color = (34, 197, 94) if best_rec.is_valid_format else (0, 165, 255)

                label_text = f"PLATE: {plate_str} ({int(best_rec.ocr_confidence * 100)}%)"
                (tw, th), _ = cv2.getTextSize(label_text, font, font_scale, font_thick)

                badge_y1 = max(0, vy1 - th - 2 * pad_y)
                badge_y2 = vy1
                badge_x2 = min(w, vx1 + tw + 2 * pad_x)

                cv2.rectangle(annotated, (vx1, badge_y1), (badge_x2, badge_y2), badge_color, -1)
                cv2.rectangle(annotated, (vx1, badge_y1), (badge_x2, badge_y2), (15, 23, 42), max(1, int(res_scale)))
                # Outline + text
                cv2.putText(annotated, label_text, (vx1 + pad_x, vy1 - pad_y), font, font_scale, (0, 0, 0), font_thick + 2, cv2.LINE_AA)
                cv2.putText(annotated, label_text, (vx1 + pad_x, vy1 - pad_y), font, font_scale, (255, 255, 255), font_thick, cv2.LINE_AA)

        return annotated

    def process_video(
        self,
        video_path: Union[str, Path],
        gps_synchronizer: Optional[GPSVideoSynchronizer] = None,
        output_video_path: Optional[Union[str, Path]] = None,
        output_json_path: Optional[Union[str, Path]] = None,
        output_evidence_dir: Optional[Union[str, Path]] = None,
        max_frames: Optional[int] = None,
        conf_threshold: Optional[float] = None,
        show_progress: bool = True,
    ) -> Dict[str, Any]:
        """Processes video feed with full vehicle tracking, plate localization, OCR, and GPS sync.

        Args:
            video_path: Path to input MP4 video file.
            gps_synchronizer: Instance of GPSVideoSynchronizer.
            output_video_path: Path to save annotated output video.
            output_json_path: Path to save structured incident records JSON.
            output_evidence_dir: Directory path to save evidence images.
            max_frames: Maximum frames to process.
            conf_threshold: Confidence threshold override.
            show_progress: Whether to print console progress.

        Returns:
            Dictionary containing summary statistics and list of all recognized plate incidents.
        """
        self.reset_state()
        conf = conf_threshold if conf_threshold is not None else self.conf_threshold

        video_file = Path(video_path)
        if not video_file.exists():
            raise FileNotFoundError(f"Input video file not found: {video_file.resolve()}")

        cap = cv2.VideoCapture(str(video_file))
        if not cap.isOpened():
            raise ValueError(f"Failed to open video file '{video_file}'. Unsupported format or corrupted file.")

        fps = cap.get(cv2.CAP_PROP_FPS) or 25.0
        width = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
        height = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
        total_video_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))

        writer = None
        if output_video_path:
            out_p = Path(output_video_path)
            out_p.parent.mkdir(parents=True, exist_ok=True)
            fourcc = cv2.VideoWriter_fourcc(*"mp4v")
            writer = cv2.VideoWriter(str(out_p), fourcc, fps, (width, height))
            if not writer.isOpened():
                fourcc = cv2.VideoWriter_fourcc(*"XVID")
                writer = cv2.VideoWriter(str(out_p), fourcc, fps, (width, height))

        frame_idx = 0
        all_records: List[PlateIncidentRecord] = []
        start_time = time.time()

        try:
            while True:
                if max_frames and frame_idx >= max_frames:
                    break

                ret, frame = cap.read()
                if not ret:
                    if frame_idx == 0:
                        raise ValueError(f"Unable to read initial frame from video: {video_file}")
                    break

                if frame is None or frame.size == 0:
                    frame_idx += 1
                    continue

                video_timestamp = frame_idx / float(fps)

                # Process frame through ANPR pipeline
                track_res, records = self.process_frame(
                    frame=frame,
                    frame_number=frame_idx,
                    video_timestamp=video_timestamp,
                    gps_synchronizer=gps_synchronizer,
                    output_evidence_dir=output_evidence_dir,
                )
                all_records.extend(records)

                # Write annotated frame
                if writer is not None:
                    annotated = self.annotate_frame(frame, track_res, records)
                    writer.write(annotated)

                frame_idx += 1

                if show_progress and frame_idx % 20 == 0:
                    pct = (frame_idx / total_video_frames * 100) if total_video_frames > 0 else 0
                    print(f"[*] ANPR processing frame {frame_idx}/{total_video_frames or '?'} ({pct:.1f}%) | Unique Plates Logged: {len(self.best_plate_records)}", flush=True)

        finally:
            cap.release()
            if writer is not None:
                writer.release()

        elapsed = time.time() - start_time
        avg_fps = frame_idx / max(1e-4, elapsed)

        # Compile deduplicated best records across the entire video
        unique_vehicle_records = list(self.best_plate_records.values())
        valid_plates = [r for r in unique_vehicle_records if r.is_valid_format]
        unvalidated_plates = [r for r in unique_vehicle_records if not r.is_valid_format]

        summary_payload = {
            "metadata": {
                "source_video": str(video_file),
                "bus_id": self.bus_id,
                "confidence_threshold": conf,
                "video_resolution": f"{width}x{height}",
                "video_fps": float(fps),
                "total_frames_processed": frame_idx,
                "processing_time_seconds": round(elapsed, 2),
                "average_inference_fps": round(avg_fps, 2),
                "is_simulated": True,
            },
            "aggregate_statistics": {
                "total_unique_vehicles_tracked": len(self.tracker.all_seen_track_ids),
                "total_plate_detections_logged": len(all_records),
                "unique_vehicles_with_plates": len(unique_vehicle_records),
                "valid_format_plates_count": len(valid_plates),
                "unvalidated_format_plates_count": len(unvalidated_plates),
                "valid_plates_list": [r.normalized_result for r in valid_plates],
            },
            "deduplicated_plate_incidents": [r.to_dict() for r in unique_vehicle_records],
            "all_plate_detections": [r.to_dict() for r in all_records],
        }

        if output_json_path:
            out_j = Path(output_json_path)
            out_j.parent.mkdir(parents=True, exist_ok=True)
            with open(out_j, "w", encoding="utf-8") as f:
                json.dump(summary_payload, f, indent=2)

        return summary_payload
