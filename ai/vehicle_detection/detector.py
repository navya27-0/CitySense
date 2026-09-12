"""Vehicle Detection Module for BusSense-AI using Ultralytics YOLO.

================================================================================
MODEL SPECIFICATION & ARCHITECTURAL RATIONALE:
================================================================================
- Default Model: `yolov8n.pt` (YOLOv8 Nano)
- Parameter Count: ~3.2 Million parameters (~6.2 MB disk footprint)
- Rationale: Designed specifically for edge/laptop execution without requiring a
  discrete GPU. Delivers 30-60+ FPS inference on standard CPUs with high precision
  on targeted urban transportation classes:
    * class 1: bicycle
    * class 2: car
    * class 3: motorcycle
    * class 5: bus
    * class 7: truck
- Reusability: Exposes `VehicleDetector` class with per-frame detection, batch video
  processing, bounding-box rendering, and vehicle counting metrics.
================================================================================
"""

import sys
import os
import time
import logging
from pathlib import Path
from dataclasses import dataclass, asdict, field
from typing import List, Dict, Any, Optional, Tuple, Union
import numpy as np
import cv2

try:
    from ultralytics import YOLO
except ImportError as e:
    raise ImportError("Ultralytics package is required. Install via: pip install ultralytics") from e

logger = logging.getLogger(__name__)

# Standard COCO class mappings for urban vehicles
TARGET_VEHICLE_CLASSES = {
    1: "bicycle",
    2: "car",
    3: "motorcycle",
    5: "bus",
    7: "truck",
}

# Distinct UI Palette for Vehicle Classes (BGR format for OpenCV)
CLASS_COLORS = {
    "car": (248, 189, 56),        # Blue/Cyan
    "bus": (34, 197, 94),         # Green
    "truck": (245, 158, 11),      # Amber
    "motorcycle": (168, 85, 247), # Purple
    "bicycle": (236, 72, 153),    # Pink
}


@dataclass
class SingleDetection:
    """Represents a single detected vehicle in a frame."""
    class_id: int
    vehicle_type: str
    confidence: float
    bounding_box: List[int]  # [x1, y1, x2, y2]
    area: int

    def to_dict(self) -> Dict[str, Any]:
        return {
            "class_id": self.class_id,
            "vehicle_type": self.vehicle_type,
            "confidence": round(float(self.confidence), 3),
            "bounding_box": [int(v) for v in self.bounding_box],
            "area": int(self.area),
        }


@dataclass
class FrameDetectionResult:
    """Represents detection metrics and objects for a single video frame."""
    frame_number: int
    video_timestamp: float
    detections: List[SingleDetection] = field(default_factory=list)
    counts_by_type: Dict[str, int] = field(default_factory=dict)
    total_vehicles: int = 0

    def to_dict(self) -> Dict[str, Any]:
        return {
            "frame_number": self.frame_number,
            "video_timestamp": round(float(self.video_timestamp), 3),
            "total_vehicles": self.total_vehicles,
            "counts_by_type": self.counts_by_type,
            "detections": [d.to_dict() for d in self.detections],
        }


class VehicleDetector:
    """Edge AI vehicle detector using lightweight Ultralytics YOLOv8."""

    def __init__(
        self,
        model_path: Union[str, Path] = "yolov8n.pt",
        conf_threshold: float = 0.35,
        iou_threshold: float = 0.45,
        device: str = "cpu",
        target_classes: Optional[Dict[int, str]] = None,
        imgsz: int = 640,
        agnostic_nms: bool = True,
    ):
        """Initialize Vehicle Detector.

        Args:
            model_path: Path or identifier of the YOLO model weights (default: yolov8n.pt).
            conf_threshold: Minimum confidence score for valid detection.
            iou_threshold: NMS IoU threshold for overlapping bounding boxes.
            device: Computation device ('cpu', 'cuda', 'mps').
            target_classes: Dictionary mapping class IDs to class names.
            imgsz: Inference input resolution (default: 640 for high-performance edge inference).
            agnostic_nms: Class-agnostic NMS to prevent overlapping bounding boxes of different classes.
        """
        self.model_path = str(model_path)
        self.conf_threshold = conf_threshold
        self.iou_threshold = iou_threshold
        self.device = device
        self.target_classes = target_classes or TARGET_VEHICLE_CLASSES
        self.imgsz = imgsz
        self.agnostic_nms = agnostic_nms

        self.model = self._load_model()

    def _load_model(self) -> YOLO:
        """Loads YOLO model with graceful exception handling."""
        try:
            # Check local models directory first if standard name is provided
            models_dir_file = Path(__file__).resolve().parent.parent.parent / "models" / self.model_path
            if models_dir_file.exists():
                target_path = str(models_dir_file)
            else:
                target_path = self.model_path

            logger.info(f"Loading YOLO model weights: {target_path} on {self.device}")
            model = YOLO(target_path)
            return model
        except Exception as e:
            raise RuntimeError(
                f"Failed to load YOLO model weights from '{self.model_path}'. "
                f"Ensure internet connectivity for initial weight download or verify the file path. Error: {e}"
            ) from e

    def detect_frame(
        self,
        frame: np.ndarray,
        frame_number: int = 0,
        video_timestamp: float = 0.0,
        conf_threshold: Optional[float] = None,
        imgsz: Optional[int] = None,
    ) -> FrameDetectionResult:
        """Runs vehicle detection on an individual video frame (BGR numpy array).

        Args:
            frame: Input video frame as numpy BGR image array.
            frame_number: Sequential frame index.
            video_timestamp: Playback timestamp in seconds.
            conf_threshold: Optional override for confidence threshold.
            imgsz: Optional override for inference image size.

        Returns:
            FrameDetectionResult containing list of detections and class counts.
        """
        if frame is None or not isinstance(frame, np.ndarray) or frame.size == 0:
            raise ValueError("Input frame is invalid, empty, or corrupted.")

        conf = conf_threshold if conf_threshold is not None else self.conf_threshold
        inference_imgsz = imgsz if imgsz is not None else self.imgsz
        target_class_ids = list(self.target_classes.keys())

        # Perform YOLO inference filtered to target vehicle classes with agnostic NMS
        results = self.model.predict(
            source=frame,
            conf=conf,
            iou=self.iou_threshold,
            classes=target_class_ids,
            agnostic_nms=self.agnostic_nms,
            imgsz=inference_imgsz,
            device=self.device,
            verbose=False,
        )

        detections: List[SingleDetection] = []
        counts: Dict[str, int] = {name: 0 for name in self.target_classes.values()}

        if results and len(results) > 0:
            boxes = results[0].boxes
            if boxes is not None and len(boxes) > 0:
                xyxy_arr = boxes.xyxy.cpu().numpy()
                conf_arr = boxes.conf.cpu().numpy()
                cls_arr = boxes.cls.cpu().numpy().astype(int)

                for xyxy, score, cls_id in zip(xyxy_arr, conf_arr, cls_arr):
                    if cls_id in self.target_classes:
                        v_type = self.target_classes[cls_id]
                        x1, y1, x2, y2 = [int(round(coord)) for coord in xyxy]
                        area = max(0, x2 - x1) * max(0, y2 - y1)

                        det = SingleDetection(
                            class_id=int(cls_id),
                            vehicle_type=v_type,
                            confidence=float(score),
                            bounding_box=[x1, y1, x2, y2],
                            area=area,
                        )
                        detections.append(det)
                        counts[v_type] = counts.get(v_type, 0) + 1

        total = sum(counts.values())
        return FrameDetectionResult(
            frame_number=frame_number,
            video_timestamp=video_timestamp,
            detections=detections,
            counts_by_type=counts,
            total_vehicles=total,
        )

    def annotate_frame(
        self,
        frame: np.ndarray,
        result: FrameDetectionResult,
        show_hud: bool = True,
        fps: float = 0.0,
    ) -> np.ndarray:
        """Draws bounding boxes, labels, and count HUD on the frame."""
        annotated = frame.copy()
        h, w = annotated.shape[:2]

        res_scale = max(1.0, min(w, h * 16 // 9) / 1280.0)
        box_thick = max(2, int(round(2.2 * res_scale)))
        font_scale = max(0.55, 0.52 * res_scale)
        font_thick = max(1, int(round(1.5 * res_scale)))
        pad_x = int(6 * res_scale)
        pad_y = int(5 * res_scale)
        font = cv2.FONT_HERSHEY_SIMPLEX

        # 1. Draw each detected vehicle bounding box and badge
        for det in result.detections:
            x1, y1, x2, y2 = det.bounding_box
            color = CLASS_COLORS.get(det.vehicle_type, (0, 255, 0))

            # Bounding box
            cv2.rectangle(annotated, (x1, y1), (x2, y2), color, box_thick)

            # Label badge with confidence
            label = f"{det.vehicle_type.upper()} {det.confidence:.2f}"
            (text_w, text_h), baseline = cv2.getTextSize(label, font, font_scale, font_thick)

            badge_y1 = max(0, y1 - text_h - 2 * pad_y)
            badge_y2 = y1
            badge_x2 = min(w, x1 + text_w + 2 * pad_x)

            cv2.rectangle(annotated, (x1, badge_y1), (badge_x2, badge_y2), color, -1)
            cv2.rectangle(annotated, (x1, badge_y1), (badge_x2, badge_y2), (15, 23, 42), max(1, int(res_scale)))

            text_pos = (x1 + pad_x, y1 - pad_y)
            cv2.putText(annotated, label, text_pos, font, font_scale, (0, 0, 0), font_thick + 2, cv2.LINE_AA)
            cv2.putText(annotated, label, text_pos, font, font_scale, (255, 255, 255), font_thick, cv2.LINE_AA)

        # 2. Draw Top-Left HUD summary panel
        if show_hud:
            hud_w = int(360 * res_scale)
            hud_h = int(115 * res_scale)
            hud_x = int(15 * res_scale)
            hud_y = int(15 * res_scale)

            overlay = annotated.copy()
            cv2.rectangle(overlay, (hud_x, hud_y), (hud_x + hud_w, hud_y + hud_h), (15, 23, 42), -1)
            cv2.addWeighted(overlay, 0.85, annotated, 0.15, 0, annotated)
            cv2.rectangle(annotated, (hud_x, hud_y), (hud_x + hud_w, hud_y + hud_h), (56, 189, 248), max(1, int(1.5 * res_scale)))

            hud_font_scale1 = max(0.48, 0.44 * res_scale)
            hud_font_scale2 = max(0.60, 0.58 * res_scale)
            hud_font_scale3 = max(0.46, 0.42 * res_scale)
            hud_thick1 = max(1, int(1.2 * res_scale))
            hud_thick2 = max(2, int(1.8 * res_scale))

            cv2.putText(annotated, "BusSense-AI | Vehicle Sensing", (hud_x + int(12 * res_scale), hud_y + int(24 * res_scale)), font, hud_font_scale1, (56, 189, 248), hud_thick1, cv2.LINE_AA)
            cv2.putText(annotated, f"Total Vehicles: {result.total_vehicles}", (hud_x + int(12 * res_scale), hud_y + int(52 * res_scale)), font, hud_font_scale2, (255, 255, 255), hud_thick2, cv2.LINE_AA)

            counts_str = " | ".join([f"{k[:3].upper()}:{v}" for k, v in result.counts_by_type.items() if v > 0] or ["No vehicles detected"])
            cv2.putText(annotated, counts_str, (hud_x + int(12 * res_scale), hud_y + int(80 * res_scale)), font, hud_font_scale3, (241, 245, 249), hud_thick1, cv2.LINE_AA)

            hud_footer = f"Time: {result.video_timestamp:.1f}s"
            if fps > 0:
                hud_footer += f" | {fps:.1f} FPS"
            cv2.putText(annotated, hud_footer, (hud_x + int(12 * res_scale), hud_y + int(104 * res_scale)), font, hud_font_scale3, (245, 158, 11), hud_thick1, cv2.LINE_AA)

        return annotated

    def process_video(
        self,
        video_path: Union[str, Path],
        output_video_path: Optional[Union[str, Path]] = None,
        output_json_path: Optional[Union[str, Path]] = None,
        max_frames: Optional[int] = None,
        conf_threshold: Optional[float] = None,
        show_progress: bool = True,
    ) -> Dict[str, Any]:
        """Processes an MP4 video file, detects vehicles per frame, and exports outputs.

        Args:
            video_path: Path to input MP4 video file.
            output_video_path: Path to save annotated output MP4 video.
            output_json_path: Path to save structured detections JSON.
            max_frames: Optional maximum frame limit for quick testing.
            conf_threshold: Optional confidence threshold.
            show_progress: Whether to print console progress.

        Returns:
            Dictionary containing overall summary and list of per-frame detections.
        """
        video_file = Path(video_path)
        if not video_file.exists():
            raise FileNotFoundError(f"Input video file not found: {video_file.resolve()}")

        cap = cv2.VideoCapture(str(video_file))
        if not cap.isOpened():
            raise ValueError(f"Failed to open video file '{video_file}'. Codec may be unsupported or file corrupted.")

        fps = cap.get(cv2.CAP_PROP_FPS) or 30.0
        width = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
        height = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
        total_video_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))

        if width <= 0 or height <= 0:
            cap.release()
            raise ValueError(f"Video file has invalid dimensions: {width}x{height}")

        writer = None
        if output_video_path:
            out_p = Path(output_video_path)
            out_p.parent.mkdir(parents=True, exist_ok=True)
            fourcc = cv2.VideoWriter_fourcc(*"mp4v")
            writer = cv2.VideoWriter(str(out_p), fourcc, fps, (width, height))
            if not writer.isOpened():
                # Fallback to standard avc1 / XVID
                fourcc = cv2.VideoWriter_fourcc(*"XVID")
                writer = cv2.VideoWriter(str(out_p), fourcc, fps, (width, height))

        frame_idx = 0
        frame_results: List[FrameDetectionResult] = []
        corrupted_frames_count = 0
        start_time = time.time()

        try:
            while True:
                if max_frames and frame_idx >= max_frames:
                    break

                ret, frame = cap.read()
                if not ret:
                    if frame_idx == 0:
                        raise ValueError(f"Unable to read initial frame from video: {video_file}")
                    break  # End of video stream

                if frame is None or frame.size == 0:
                    corrupted_frames_count += 1
                    logger.warning(f"Corrupted frame encountered at index {frame_idx}, skipping.")
                    frame_idx += 1
                    continue

                video_timestamp = frame_idx / float(fps)
                t_frame_start = time.time()

                # Detect vehicles in frame
                res = self.detect_frame(
                    frame=frame,
                    frame_number=frame_idx,
                    video_timestamp=video_timestamp,
                    conf_threshold=conf_threshold,
                )
                frame_results.append(res)

                # Annotate and write to output video
                if writer is not None:
                    calc_fps = 1.0 / max(1e-4, (time.time() - t_frame_start))
                    annotated_frame = self.annotate_frame(frame, res, show_hud=True, fps=calc_fps)
                    writer.write(annotated_frame)

                frame_idx += 1

                if show_progress and frame_idx % 20 == 0:
                    pct = (frame_idx / total_video_frames * 100) if total_video_frames > 0 else 0
                    print(f"[*] Processed frame {frame_idx}/{total_video_frames or '?'} ({pct:.1f}%) - {res.total_vehicles} vehicles in frame", flush=True)

        finally:
            cap.release()
            if writer is not None:
                writer.release()

        elapsed_time = time.time() - start_time
        avg_processing_fps = frame_idx / max(1e-4, elapsed_time)

        # Aggregate summary statistics
        cumulative_counts: Dict[str, int] = {k: 0 for k in self.target_classes.values()}
        total_detections = 0
        for f_res in frame_results:
            for k, v in f_res.counts_by_type.items():
                cumulative_counts[k] += v
            total_detections += len(f_res.detections)

        summary = {
            "metadata": {
                "source_video": str(video_file),
                "model_weights": self.model_path,
                "confidence_threshold": self.conf_threshold,
                "video_resolution": f"{width}x{height}",
                "video_fps": round(fps, 2),
                "total_frames_processed": frame_idx,
                "corrupted_frames_skipped": corrupted_frames_count,
                "processing_time_seconds": round(elapsed_time, 2),
                "average_inference_fps": round(avg_processing_fps, 2),
                "is_simulated": True,
            },
            "aggregate_statistics": {
                "total_vehicle_detections": total_detections,
                "cumulative_counts_by_type": cumulative_counts,
                "average_vehicles_per_frame": round(total_detections / max(1, frame_idx), 2),
            },
            "frame_detections": [r.to_dict() for r in frame_results],
        }

        # Export structured JSON if path provided
        if output_json_path:
            json_p = Path(output_json_path)
            json_p.parent.mkdir(parents=True, exist_ok=True)
            import json
            with open(json_p, "w", encoding="utf-8") as f:
                json.dump(summary, f, indent=2)

        return summary
