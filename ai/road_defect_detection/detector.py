"""Road-Defect Detection Module for BusSense-AI.

================================================================================
BEL PROBLEM STATEMENT COVERAGE:
Detects potholes, damaged roads, missing road dividers, missing zebra crossings,
damaged/missing traffic signboards, and waterlogging as subtypes of one unified
road defect sensing module.

ARCHITECTURE:
Video Stream -> RoadDefectDetector -> Bounding Box + Confidence + Defect Subtype
             -> GPS Association (via GPSVideoSynchronizer) -> Evidence Frame Export
             -> Urban Sensing Event (JSON/DB)

CUSTOM WEIGHT DROP-IN CONTRACT:
- The detector dynamically checks for custom trained YOLO weights at:
  `models/road_defects/best.pt` (or any custom path passed to constructor).
- If present, class names are introspected directly from `model.names` (not hardcoded).
- If not present, the detector logs a clear warning and operates in a calibrated
  DEMO / FALLBACK MODE using computer vision edge/texture anomaly filters and sample cues,
  ensuring demo runs and test pipelines function end-to-end.
- A generic/untrained COCO model is NEVER falsely claimed to detect potholes.
================================================================================
"""

import os
import sys
import uuid
import time
import logging
from enum import Enum
from pathlib import Path
from dataclasses import dataclass, field, asdict
from typing import Dict, Any, List, Optional, Union, Tuple, Set
import json

import cv2
import numpy as np

from ai.pipeline.gps_sync import GPSVideoSynchronizer

logger = logging.getLogger(__name__)

# Standard Urban Road Defect Subtypes
class RoadDefectType(str, Enum):
    POTHOLE = "POTHOLE"
    DAMAGED_ROAD = "DAMAGED_ROAD"
    MISSING_DIVIDER = "MISSING_DIVIDER"
    MISSING_ZEBRA_CROSSING = "MISSING_ZEBRA_CROSSING"
    DAMAGED_SIGNBOARD = "DAMAGED_SIGNBOARD"
    WATERLOGGING = "WATERLOGGING"


class RoadDefectSeverity(str, Enum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


# Distinct BGR Colors for defect bounding boxes and HUD badges
DEFECT_COLORS = {
    "POTHOLE": (0, 0, 255),               # Red
    "DAMAGED_ROAD": (0, 140, 255),         # Orange
    "MISSING_DIVIDER": (0, 230, 255),      # Yellow-Gold
    "MISSING_ZEBRA_CROSSING": (255, 0, 255), # Magenta
    "DAMAGED_SIGNBOARD": (255, 140, 0),    # Cyan / Blue
    "WATERLOGGING": (255, 215, 0),         # Teal / Light Blue
}

SEVERITY_COLORS = {
    "low": (34, 197, 94),       # Green
    "medium": (0, 200, 255),    # Yellow
    "high": (0, 140, 255),      # Orange
    "critical": (0, 0, 255),    # Red
}

# Subtype name normalization dictionary for custom model introspection
SUBTYPE_SYNONYMS = {
    "pothole": RoadDefectType.POTHOLE,
    "potholes": RoadDefectType.POTHOLE,
    "cavity": RoadDefectType.POTHOLE,
    "d00": RoadDefectType.POTHOLE,              # RDD2022 dataset code for longitudinal crack/pothole
    "damaged_road": RoadDefectType.DAMAGED_ROAD,
    "crack": RoadDefectType.DAMAGED_ROAD,
    "alligator_crack": RoadDefectType.DAMAGED_ROAD,
    "d20": RoadDefectType.DAMAGED_ROAD,          # RDD2022 alligator crack
    "d40": RoadDefectType.DAMAGED_ROAD,          # RDD2022 rutting/bump
    "missing_divider": RoadDefectType.MISSING_DIVIDER,
    "divider": RoadDefectType.MISSING_DIVIDER,
    "broken_median": RoadDefectType.MISSING_DIVIDER,
    "missing_zebra_crossing": RoadDefectType.MISSING_ZEBRA_CROSSING,
    "zebra_crossing": RoadDefectType.MISSING_ZEBRA_CROSSING,
    "faded_crosswalk": RoadDefectType.MISSING_ZEBRA_CROSSING,
    "damaged_signboard": RoadDefectType.DAMAGED_SIGNBOARD,
    "damaged_sign": RoadDefectType.DAMAGED_SIGNBOARD,
    "signboard": RoadDefectType.DAMAGED_SIGNBOARD,
    "waterlogging": RoadDefectType.WATERLOGGING,
    "water_logging": RoadDefectType.WATERLOGGING,
    "standing_water": RoadDefectType.WATERLOGGING,
    "flooded_road": RoadDefectType.WATERLOGGING,
}


@dataclass
class RoadDefectDetection:
    """Represents a raw defect detection within a single video frame."""
    defect_type: str
    confidence: float
    bounding_box: List[int]  # [x1, y1, x2, y2]
    area: int
    severity: str = "medium"
    centroid: Tuple[int, int] = (0, 0)
    is_simulated: bool = True

    def to_dict(self) -> Dict[str, Any]:
        return {
            "defect_type": self.defect_type,
            "confidence": round(float(self.confidence), 3),
            "bounding_box": self.bounding_box,
            "area": self.area,
            "severity": self.severity,
            "centroid": list(self.centroid),
            "is_simulated": self.is_simulated,
        }


@dataclass
class RoadDefectEvent:
    """Represents a full urban road defect event synchronized with GPS and evidence imagery."""
    event_id: str
    bus_id: str
    event_type: str  # POTHOLE, DAMAGED_ROAD, MISSING_DIVIDER, etc.
    defect_subtype: str
    confidence: float
    frame_number: int
    video_timestamp: float
    timestamp: str  # ISO UTC from GPS
    latitude: float
    longitude: float
    speed_kmh: float
    heading_deg: float
    severity: str  # low, medium, high, critical
    image_path: str
    bounding_box: List[int]
    area: int
    status: str = "detected"
    is_simulated: bool = True
    metadata: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "event_id": self.event_id,
            "bus_id": self.bus_id,
            "event_type": self.event_type,
            "defect_subtype": self.defect_subtype,
            "confidence": round(float(self.confidence), 3),
            "frame_number": self.frame_number,
            "video_timestamp": round(float(self.video_timestamp), 3),
            "timestamp": self.timestamp,
            "latitude": round(float(self.latitude), 6),
            "longitude": round(float(self.longitude), 6),
            "speed_kmh": round(float(self.speed_kmh), 2),
            "heading_deg": round(float(self.heading_deg), 1),
            "severity": self.severity,
            "image_path": self.image_path,
            "bounding_box": self.bounding_box,
            "area": self.area,
            "status": self.status,
            "is_simulated": self.is_simulated,
            "metadata": self.metadata,
        }


class RoadDefectDetector:
    """Edge AI detector for urban road surface defects and infrastructure anomalies."""

    DEFAULT_MODEL_PATH = Path("models/road_defects/best.pt")

    def __init__(
        self,
        model_path: Optional[Union[str, Path]] = None,
        conf_threshold: float = 0.30,
        device: str = "cpu",
        bus_id: str = "BUS_101",
        evidence_dir: Union[str, Path] = "data/outputs/events",
        save_evidence: bool = True,
        enable_demo_fallback: bool = True,
        dedup_window_seconds: float = 2.0,
    ):
        """Initializes the RoadDefectDetector.

        Args:
            model_path: Path to custom trained YOLO weights (e.g. models/road_defects/best.pt).
            conf_threshold: Minimum confidence threshold.
            device: Compute device ('cpu', 'cuda').
            bus_id: Bus fleet identifier.
            evidence_dir: Directory where annotated evidence frames are saved.
            save_evidence: Whether to save evidence images on detection.
            enable_demo_fallback: Whether to use calibrated CV demo fallback if weights are missing.
            dedup_window_seconds: Minimum time between duplicate event triggers of same defect.
        """
        self.conf_threshold = conf_threshold
        self.device = device
        self.bus_id = bus_id
        self.evidence_dir = Path(evidence_dir)
        self.save_evidence = save_evidence
        self.enable_demo_fallback = enable_demo_fallback
        self.dedup_window_seconds = dedup_window_seconds

        if self.save_evidence:
            self.evidence_dir.mkdir(parents=True, exist_ok=True)

        # 1. Inspect model weights
        target_path = Path(model_path) if model_path else self.DEFAULT_MODEL_PATH
        self.custom_model_loaded = False
        self.model = None
        self.class_mapping: Dict[int, str] = {}
        self.model_source_description = ""

        resolved_path = self._resolve_model_path(target_path)
        if resolved_path and resolved_path.exists():
            try:
                from ultralytics import YOLO
                logger.info(f"Loading custom road defect weights from: {resolved_path}")
                self.model = YOLO(str(resolved_path))
                self.custom_model_loaded = True
                self.model_source_description = f"Custom YOLO ({resolved_path.name})"

                # Introspect class names directly from model metadata
                if hasattr(self.model, "names") and self.model.names:
                    for cls_id, raw_name in self.model.names.items():
                        norm_type = self._normalize_subtype(raw_name)
                        self.class_mapping[int(cls_id)] = norm_type
                    logger.info(f"Dynamically mapped {len(self.class_mapping)} defect classes from model: {self.class_mapping}")
                else:
                    self.class_mapping = {0: RoadDefectType.POTHOLE.value}

            except Exception as e:
                logger.warning(f"Failed loading custom weights at {resolved_path}: {e}")
                self.custom_model_loaded = False

        if not self.custom_model_loaded:
            self.model_source_description = "DEMO / FALLBACK MODE (Calibrated CV Anomaly Filters)"
            print(
                f"[WARN] Custom trained road defect model weights not found at '{target_path}'.\n"
                f"       Operating in DEMO / FALLBACK MODE using computer vision edge anomaly filters.\n"
                f"       Custom weights can be dropped in at 'models/road_defects/best.pt' without code changes."
            )

        # State tracking for spatio-temporal deduplication
        self.last_event_timestamps: Dict[str, float] = {}

    def _resolve_model_path(self, path: Path) -> Optional[Path]:
        """Resolves model weights path in local workspace."""
        if path.exists():
            return path
        project_root = Path(__file__).resolve().parent.parent.parent
        in_models = project_root / path
        if in_models.exists():
            return in_models
        return None

    def _normalize_subtype(self, raw_name: str) -> str:
        """Maps arbitrary raw class strings from custom trained models to standard RoadDefectType."""
        clean = str(raw_name).strip().lower().replace("-", "_").replace(" ", "_")
        if clean in SUBTYPE_SYNONYMS:
            return SUBTYPE_SYNONYMS[clean].value
        # Default fallback
        for key, val in SUBTYPE_SYNONYMS.items():
            if key in clean:
                return val.value
        return clean.upper()

    def calculate_severity(self, defect_type: str, area: int, confidence: float, frame_w: int, frame_h: int) -> str:
        """Calculates defect severity based on defect subtype, relative pixel area, and confidence.

        Args:
            defect_type: Defect subtype string (e.g. POTHOLE).
            area: Bounding box area in pixels.
            confidence: Model confidence score.
            frame_w: Video frame width.
            frame_h: Video frame height.

        Returns:
            Severity string ('low', 'medium', 'high', 'critical').
        """
        total_frame_area = max(1, frame_w * frame_h)
        rel_area = area / float(total_frame_area)

        # High priority critical defects
        if defect_type in [RoadDefectType.MISSING_DIVIDER.value, RoadDefectType.WATERLOGGING.value]:
            if rel_area > 0.05 or confidence > 0.75:
                return RoadDefectSeverity.CRITICAL.value
            return RoadDefectSeverity.HIGH.value

        if defect_type == RoadDefectType.POTHOLE.value:
            if rel_area > 0.04 or confidence > 0.80:
                return RoadDefectSeverity.HIGH.value
            elif rel_area > 0.015:
                return RoadDefectSeverity.MEDIUM.value
            return RoadDefectSeverity.LOW.value

        if defect_type == RoadDefectType.DAMAGED_ROAD.value:
            if rel_area > 0.06:
                return RoadDefectSeverity.HIGH.value
            return RoadDefectSeverity.MEDIUM.value

        if rel_area > 0.03:
            return RoadDefectSeverity.MEDIUM.value
        return RoadDefectSeverity.LOW.value

    def detect_frame(
        self,
        frame: np.ndarray,
        frame_number: int = 0,
        video_timestamp: float = 0.0,
        conf_threshold: Optional[float] = None,
    ) -> List[RoadDefectDetection]:
        """Runs defect detection on a single frame.

        Args:
            frame: OpenCV BGR image array.
            frame_number: Sequential frame number.
            video_timestamp: Relative timestamp in seconds.
            conf_threshold: Optional confidence threshold override.

        Returns:
            List of RoadDefectDetection objects.
        """
        if frame is None or not isinstance(frame, np.ndarray) or frame.size == 0:
            raise ValueError("Input frame is invalid, empty, or corrupted.")

        conf = conf_threshold if conf_threshold is not None else self.conf_threshold
        h, w = frame.shape[:2]
        detections: List[RoadDefectDetection] = []

        # 1. Custom YOLO Model Inference
        if self.custom_model_loaded and self.model is not None:
            results = self.model.predict(
                source=frame,
                conf=conf,
                device=self.device,
                verbose=False,
            )
            if results and len(results) > 0:
                boxes = results[0].boxes
                if boxes is not None and len(boxes) > 0:
                    xyxy_arr = boxes.xyxy.cpu().numpy()
                    conf_arr = boxes.conf.cpu().numpy()
                    cls_arr = boxes.cls.cpu().numpy().astype(int)

                    for xyxy, score, cls_id in zip(xyxy_arr, conf_arr, cls_arr):
                        defect_type = self.class_mapping.get(cls_id, RoadDefectType.POTHOLE.value)
                        x1, y1, x2, y2 = [int(round(c)) for c in xyxy]
                        x1, y1 = max(0, x1), max(0, y1)
                        x2, y2 = min(w, x2), min(h, y2)
                        area = max(0, x2 - x1) * max(0, y2 - y1)
                        cx, cy = int((x1 + x2) / 2), int((y1 + y2) / 2)
                        severity = self.calculate_severity(defect_type, area, float(score), w, h)

                        detections.append(
                            RoadDefectDetection(
                                defect_type=defect_type,
                                confidence=float(score),
                                bounding_box=[x1, y1, x2, y2],
                                area=area,
                                severity=severity,
                                centroid=(cx, cy),
                                is_simulated=False,
                            )
                        )
            return detections

        # 2. Demo / Fallback Mode (Computer Vision Anomaly Filters)
        if self.enable_demo_fallback:
            fallback_dets = self._run_cv_fallback_detection(frame, frame_number, video_timestamp, conf)
            detections.extend(fallback_dets)

        return detections

    def _run_cv_fallback_detection(
        self,
        frame: np.ndarray,
        frame_number: int,
        video_timestamp: float,
        conf_thresh: float,
    ) -> List[RoadDefectDetection]:
        """Runs adaptive computer vision filters (dark cavity segmentation, morphological clustering, and texture analysis)."""
        h, w = frame.shape[:2]
        dets: List[RoadDefectDetection] = []

        # 1. Road Surface Region of Interest (ROI)
        roi_y1 = int(h * 0.15)
        roi_y2 = int(h * 0.95)
        roi_x1 = int(w * 0.03)
        roi_x2 = int(w * 0.97)
        roi = frame[roi_y1:roi_y2, roi_x1:roi_x2]

        if roi.size == 0:
            return dets

        gray = cv2.cvtColor(roi, cv2.COLOR_BGR2GRAY)
        blurred = cv2.GaussianBlur(gray, (13, 13), 0)

        mean_val = float(np.mean(blurred))
        std_val = float(np.std(blurred))

        # 2. Adaptive Dark Anomaly Thresholding (Cavities / Puddles / Cracks)
        thresh_val = max(35, mean_val - 1.05 * std_val)
        _, mask_dark = cv2.threshold(blurred, thresh_val, 255, cv2.THRESH_BINARY_INV)

        # 3. Morphological Operations to connect fractured pothole and crack pixels
        k_close = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (11, 11))
        k_open = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (5, 5))
        mask_dark = cv2.morphologyEx(mask_dark, cv2.MORPH_CLOSE, k_close, iterations=2)
        mask_dark = cv2.morphologyEx(mask_dark, cv2.MORPH_OPEN, k_open, iterations=1)

        # 4. Contour Extraction
        contours, _ = cv2.findContours(mask_dark, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)

        min_area = w * h * 0.006  # at least 0.6% of frame area
        max_area = w * h * 0.35   # ignore global lighting changes

        for c in contours:
            c_area = cv2.contourArea(c)
            if min_area < c_area < max_area:
                x, y, bw, bh = cv2.boundingRect(c)
                aspect = bw / float(max(1, bh))

                # Discard unrealistic narrow camera borders / edge noise
                if 0.2 < aspect < 5.5:
                    abs_x1 = x + roi_x1
                    abs_y1 = y + roi_y1
                    abs_x2 = abs_x1 + bw
                    abs_y2 = abs_y1 + bh
                    box_area = bw * bh

                    # Analyze internal patch texture and brightness
                    patch = gray[y:y+bh, x:x+bw]
                    p_var = float(np.var(patch)) if patch.size > 0 else 0.0
                    p_mean = float(np.mean(patch)) if patch.size > 0 else 0.0

                    if p_var > 380:
                        dtype = RoadDefectType.DAMAGED_ROAD.value
                        conf = min(0.92, 0.72 + (p_var / 2500.0) * 0.20)
                    elif p_mean < 75 and p_var < 140:
                        dtype = RoadDefectType.WATERLOGGING.value
                        conf = min(0.90, 0.75 + (c_area / max_area) * 0.15)
                    else:
                        dtype = RoadDefectType.POTHOLE.value
                        conf = min(0.94, 0.78 + (c_area / max_area) * 0.16)

                    if conf >= conf_thresh:
                        sev = self.calculate_severity(dtype, box_area, conf, w, h)
                        centroid = (int((abs_x1 + abs_x2) / 2), int((abs_y1 + abs_y2) / 2))

                        dets.append(
                            RoadDefectDetection(
                                defect_type=dtype,
                                confidence=round(conf, 3),
                                bounding_box=[abs_x1, abs_y1, abs_x2, abs_y2],
                                area=box_area,
                                severity=sev,
                                centroid=centroid,
                                is_simulated=True,
                            )
                        )

        # Sort by confidence and take top 4 most prominent defects in frame
        dets.sort(key=lambda d: d.confidence, reverse=True)
        return dets[:4]

    def save_evidence_image(
        self,
        frame: np.ndarray,
        detection: RoadDefectDetection,
        bus_id: str,
        frame_number: int,
        timestamp_str: str = "",
        gps_coords: Optional[Tuple[float, float]] = None,
    ) -> str:
        """Annotates and saves an evidence frame to data/outputs/events/."""
        annotated = frame.copy()
        h, w = annotated.shape[:2]
        x1, y1, x2, y2 = detection.bounding_box
        color = DEFECT_COLORS.get(detection.defect_type, (0, 0, 255))
        sev_color = SEVERITY_COLORS.get(detection.severity, (0, 200, 255))

        # 1. Bounding box & target corners
        cv2.rectangle(annotated, (x1, y1), (x2, y2), color, 3)

        # 2. Defect Label Badge
        label = f"{detection.defect_type} | SEV: {detection.severity.upper()} | CONF: {detection.confidence:.2f}"
        font = cv2.FONT_HERSHEY_SIMPLEX
        scale = 0.55
        thickness = 2
        (tw, th), _ = cv2.getTextSize(label, font, scale, thickness)
        badge_y1 = max(0, y1 - th - 10)
        cv2.rectangle(annotated, (x1, badge_y1), (min(w, x1 + tw + 12), y1), color, -1)
        cv2.putText(annotated, label, (x1 + 6, y1 - 6), font, scale, (255, 255, 255), thickness, cv2.LINE_AA)

        # 3. Watermark GPS & Timestamp Banner at the bottom
        gps_txt = f"BusSense-AI | Bus: {bus_id} | GPS: {gps_coords[0]:.5f}, {gps_coords[1]:.5f} | Time: {timestamp_str or 'SIMULATED'}" if gps_coords else f"BusSense-AI | Bus: {bus_id} | Time: {timestamp_str}"
        cv2.rectangle(annotated, (0, h - 35), (w, h), (15, 23, 42), -1)
        cv2.putText(annotated, gps_txt, (15, h - 12), font, 0.45, (226, 232, 240), 1, cv2.LINE_AA)

        # 4. Save file: roaddefect_BUS101_POTHOLE_000123.jpg
        clean_bus_id = bus_id.replace("_", "").replace("-", "")
        filename = f"roaddefect_{clean_bus_id}_{detection.defect_type}_{frame_number:06d}.jpg"
        target_path = self.evidence_dir / filename
        cv2.imwrite(str(target_path), annotated)

        return str(target_path.as_posix())

    def create_urban_event(
        self,
        detection: RoadDefectDetection,
        frame_number: int,
        video_timestamp: float,
        frame: np.ndarray,
        gps_synchronizer: Optional[GPSVideoSynchronizer] = None,
    ) -> Optional[RoadDefectEvent]:
        """Constructs an Urban Road Defect Event with attached GPS and evidence image.

        Applies spatio-temporal deduplication to avoid repetitive events for the same anomaly.
        """
        # Deduplication check
        last_t = self.last_event_timestamps.get(detection.defect_type, -999.0)
        if (video_timestamp - last_t) < self.dedup_window_seconds:
            return None  # Skip duplicate trigger

        self.last_event_timestamps[detection.defect_type] = video_timestamp

        # Retrieve geographic coordinates via GPSVideoSynchronizer (Single Source of Truth)
        if gps_synchronizer is not None:
            pos = gps_synchronizer.get_position(video_timestamp=video_timestamp, interpolate=True)
            iso_time = pos.get("gps_timestamp") or pos.get("interpolated_timestamp") or ""
            lat = pos.get("latitude", 17.3850)
            lon = pos.get("longitude", 78.4867)
            spd = pos.get("speed", 0.0)
            hdg = pos.get("heading", 0.0)
        else:
            iso_time = "2026-09-09T14:30:00Z"
            lat = 17.3850
            lon = 78.4867
            spd = 25.0
            hdg = 0.0

        event_id = str(uuid.uuid4())

        # Save evidence frame
        image_path = ""
        if self.save_evidence:
            image_path = self.save_evidence_image(
                frame=frame,
                detection=detection,
                bus_id=self.bus_id,
                frame_number=frame_number,
                timestamp_str=iso_time,
                gps_coords=(lat, lon),
            )

        return RoadDefectEvent(
            event_id=event_id,
            bus_id=self.bus_id,
            event_type=detection.defect_type,
            defect_subtype=detection.defect_type,
            confidence=detection.confidence,
            frame_number=frame_number,
            video_timestamp=video_timestamp,
            timestamp=iso_time,
            latitude=lat,
            longitude=lon,
            speed_kmh=spd,
            heading_deg=hdg,
            severity=detection.severity,
            image_path=image_path,
            bounding_box=detection.bounding_box,
            area=detection.area,
            status="detected",
            is_simulated=True,
            metadata={
                "model_source": self.model_source_description,
                "custom_weights_loaded": self.custom_model_loaded,
                "dedup_window_seconds": self.dedup_window_seconds,
                "disclaimer": "prototype road-defect detection — not scientifically calibrated without field training",
            },
        )

    def annotate_frame(
        self,
        frame: np.ndarray,
        detections: List[RoadDefectDetection],
        events_triggered: int = 0,
        fps: float = 0.0,
    ) -> np.ndarray:
        """Draws bounding boxes, defect labels, and HUD on video output."""
        annotated = frame.copy()
        h, w = annotated.shape[:2]

        res_scale = max(1.0, min(w, h * 16 // 9) / 1280.0)
        box_thick = max(2, int(round(2.2 * res_scale)))
        font_scale = max(0.55, 0.52 * res_scale)
        font_thick = max(1, int(round(1.5 * res_scale)))
        pad_x = int(6 * res_scale)
        pad_y = int(5 * res_scale)
        font = cv2.FONT_HERSHEY_SIMPLEX

        for det in detections:
            x1, y1, x2, y2 = det.bounding_box
            color = DEFECT_COLORS.get(det.defect_type, (0, 0, 255))
            cv2.rectangle(annotated, (x1, y1), (x2, y2), color, box_thick)

            label = f"{det.defect_type} ({det.severity.upper()}) {det.confidence:.2f}"
            (tw, th), _ = cv2.getTextSize(label, font, font_scale, font_thick)

            badge_y1 = max(0, y1 - th - 2 * pad_y)
            badge_y2 = y1
            badge_x2 = min(w, x1 + tw + 2 * pad_x)

            cv2.rectangle(annotated, (x1, badge_y1), (badge_x2, badge_y2), color, -1)
            cv2.rectangle(annotated, (x1, badge_y1), (badge_x2, badge_y2), (15, 23, 42), max(1, int(res_scale)))

            text_pos = (x1 + pad_x, y1 - pad_y)
            cv2.putText(annotated, label, text_pos, font, font_scale, (0, 0, 0), font_thick + 2, cv2.LINE_AA)
            cv2.putText(annotated, label, text_pos, font, font_scale, (255, 255, 255), font_thick, cv2.LINE_AA)

        # Top HUD Banner
        hud_w = int(460 * res_scale)
        hud_h = int(90 * res_scale)
        hud_x = int(15 * res_scale)
        hud_y = int(15 * res_scale)

        overlay = annotated.copy()
        cv2.rectangle(overlay, (hud_x, hud_y), (hud_x + hud_w, hud_y + hud_h), (15, 23, 42), -1)
        cv2.addWeighted(overlay, 0.85, annotated, 0.15, 0, annotated)
        cv2.rectangle(annotated, (hud_x, hud_y), (hud_x + hud_w, hud_y + hud_h), (56, 189, 248), max(1, int(1.5 * res_scale)))

        hud_font_scale1 = max(0.48, 0.44 * res_scale)
        hud_font_scale2 = max(0.55, 0.50 * res_scale)
        hud_font_scale3 = max(0.44, 0.40 * res_scale)
        hud_thick1 = max(1, int(1.2 * res_scale))

        cv2.putText(
            annotated,
            f"BusSense-AI | Road Defect Detection ({'Custom' if self.custom_model_loaded else 'Demo'})",
            (hud_x + int(12 * res_scale), hud_y + int(24 * res_scale)),
            font,
            hud_font_scale1,
            (56, 189, 248),
            hud_thick1,
            cv2.LINE_AA,
        )
        cv2.putText(
            annotated,
            f"Active Defects in Frame: {len(detections)} | Events Logged: {events_triggered}",
            (hud_x + int(12 * res_scale), hud_y + int(50 * res_scale)),
            font,
            hud_font_scale2,
            (255, 255, 255),
            hud_thick1,
            cv2.LINE_AA,
        )
        cv2.putText(
            annotated,
            f"Bus: {self.bus_id} | {fps:.1f} FPS",
            (hud_x + int(12 * res_scale), hud_y + int(74 * res_scale)),
            font,
            hud_font_scale3,
            (148, 163, 184),
            hud_thick1,
            cv2.LINE_AA,
        )

        return annotated

    def process_video(
        self,
        video_path: Union[str, Path],
        gps_synchronizer: Optional[GPSVideoSynchronizer] = None,
        output_video_path: Optional[Union[str, Path]] = None,
        output_json_path: Optional[Union[str, Path]] = None,
        max_frames: Optional[int] = None,
        conf_threshold: Optional[float] = None,
        show_progress: bool = True,
    ) -> Dict[str, Any]:
        """Streams video, detects road defects, logs urban events, saves evidence, and exports JSON."""
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
        events_list: List[RoadDefectEvent] = []
        counts_by_subtype: Dict[str, int] = {t.value: 0 for t in RoadDefectType}
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
                t_f_start = time.time()

                # Detect defects in frame
                detections = self.detect_frame(
                    frame=frame,
                    frame_number=frame_idx,
                    video_timestamp=video_timestamp,
                    conf_threshold=conf_threshold,
                )

                # Process detections into deduplicated urban events
                for det in detections:
                    ev = self.create_urban_event(
                        detection=det,
                        frame_number=frame_idx,
                        video_timestamp=video_timestamp,
                        frame=frame,
                        gps_synchronizer=gps_synchronizer,
                    )
                    if ev is not None:
                        events_list.append(ev)
                        counts_by_subtype[ev.defect_subtype] = counts_by_subtype.get(ev.defect_subtype, 0) + 1

                # Annotate and write video frame
                if writer is not None:
                    calc_fps = 1.0 / max(1e-4, (time.time() - t_f_start))
                    annotated_frame = self.annotate_frame(
                        frame,
                        detections,
                        events_triggered=len(events_list),
                        fps=calc_fps,
                    )
                    writer.write(annotated_frame)

                frame_idx += 1

                if show_progress and frame_idx % 30 == 0:
                    pct = (frame_idx / total_video_frames * 100) if total_video_frames > 0 else 0
                    print(f"[*] Defect detection frame {frame_idx}/{total_video_frames or '?'} ({pct:.1f}%) | Events Logged: {len(events_list)}")

        finally:
            cap.release()
            if writer is not None:
                writer.release()

        elapsed = time.time() - start_time
        avg_fps = frame_idx / max(1e-4, elapsed)

        summary_payload = {
            "metadata": {
                "source_video": str(video_file),
                "model_source": self.model_source_description,
                "custom_weights_loaded": self.custom_model_loaded,
                "confidence_threshold": self.conf_threshold,
                "bus_id": self.bus_id,
                "video_resolution": f"{width}x{height}",
                "video_fps": float(fps),
                "total_frames_processed": frame_idx,
                "processing_time_seconds": round(elapsed, 2),
                "average_inference_fps": round(avg_fps, 2),
                "is_simulated": True,
                "disclaimer": "prototype road-defect detection — not scientifically calibrated without field training",
            },
            "aggregate_statistics": {
                "total_events_logged": len(events_list),
                "events_by_subtype": counts_by_subtype,
                "events_by_severity": {
                    "low": sum(1 for e in events_list if e.severity == "low"),
                    "medium": sum(1 for e in events_list if e.severity == "medium"),
                    "high": sum(1 for e in events_list if e.severity == "high"),
                    "critical": sum(1 for e in events_list if e.severity == "critical"),
                },
            },
            "events": [e.to_dict() for e in events_list],
        }

        if output_json_path:
            out_j = Path(output_json_path)
            out_j.parent.mkdir(parents=True, exist_ok=True)
            with open(out_j, "w", encoding="utf-8") as f:
                json.dump(summary_payload, f, indent=2)

        return summary_payload
