"""Unified Edge-AI Processing Pipeline for BusSense-AI.

================================================================================
ARCHITECTURE & EXECUTION CONTRACT:
================================================================================
Ties together all edge AI perception and analytics modules built across the project:
1. Video Capture (OpenCV)
2. GPS Telemetry Synchronization via GPSVideoSynchronizer (ai/pipeline/gps_sync.py)
   — Single source of truth for all spatial-temporal interpolation.
3. Multi-Object Vehicle Detection, Tracking, and Recount-Prevention (ByteTrack)
4. Periodic Prototype Traffic-Density Window Aggregation & Classification
5. Urban Road-Defect Detection (Potholes, damaged roads, missing dividers, etc.)
6. Traffic Incident Detection Engine (Rash driving & suspected hit-and-run)
7. Targeted Number Plate Recognition (EasyOCR + Plate localization on flagged vehicles)
8. Attachment of synchronized GPS (lat, lon, speed, heading), timestamp, bus_id,
   and route_id to every generated event.
9. Export of structured JSON events and composite diagnostic evidence frames.
10. Optional non-blocking FastAPI backend telemetry and event dispatch.

ENVIRONMENT VARIABLE TOGGLES:
- ENABLE_VEHICLE_DETECTION (default: true)
- ENABLE_ROAD_DEFECT_DETECTION (default: true)
- ENABLE_OCR (default: true)
- ENABLE_INCIDENT_DETECTION (default: true)
- ENABLE_DENSITY_ESTIMATION (default: true)
- SEND_TO_BACKEND (default: false)

If a stage is disabled, its model weights are NEVER loaded into memory.
Pedestrian detection is strictly excluded from this edge pipeline.
================================================================================
"""

import os
import sys
import time
import json
import uuid
import logging
import argparse
from pathlib import Path
from dataclasses import dataclass, field, asdict
from typing import Dict, Any, List, Optional, Union, Tuple, Set
from collections import defaultdict, deque
import urllib.request
import urllib.error

import cv2
import numpy as np

# Ensure project root is in sys.path
PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from ai.pipeline.gps_sync import GPSVideoSynchronizer
from ai.tracking.tracker import VehicleTracker, FrameTrackingResult, TrackedVehicleDetection, TARGET_VEHICLE_CLASSES
from ai.tracking.density_estimator import (
    TrafficDensityEstimator,
    IntervalTrafficMeasurement,
    TrafficDensity,
)
from ai.road_defect_detection.detector import (
    RoadDefectDetector,
    RoadDefectDetection,
    RoadDefectType,
    RoadDefectSeverity,
    DEFECT_COLORS,
)
from ai.anpr.plate_detector import PlateDetector, PlateDetection
from ai.anpr.ocr_engine import OCREngine, PlateOCRResult
from ai.anpr.validator import PlateValidator, ValidationResult
from ai.incident_detection import (
    IncidentDetector,
    IncidentConfig,
    IncidentRecord,
    IncidentType,
    IncidentSeverity,
    IncidentStatus,
    DISCLAIMER_TEXT as INCIDENT_DISCLAIMER,
)

logger = logging.getLogger("EdgePipeline")


def get_env_bool(key: str, default: bool = True) -> bool:
    """Safely parses boolean environment variables."""
    val = os.getenv(key)
    if val is None:
        return default
    return val.strip().lower() in ("1", "true", "yes", "on", "t")


@dataclass
class PipelineConfig:
    """Unified configuration for edge AI pipeline execution and sub-engine toggles."""
    bus_id: str = "BUS_101"
    route_id: str = "216"
    camera_id: str = "CAM_FRONT_01"
    device: str = "cpu"
    conf_threshold: float = 0.25
    imgsz: int = 640
    
    # Sub-Engine Enable Toggles (supports env var defaults)
    enable_vehicle_detection: bool = field(default_factory=lambda: get_env_bool("ENABLE_VEHICLE_DETECTION", True))
    enable_road_defect_detection: bool = field(default_factory=lambda: get_env_bool("ENABLE_ROAD_DEFECT_DETECTION", True))
    enable_ocr: bool = field(default_factory=lambda: get_env_bool("ENABLE_OCR", True))
    enable_incident_detection: bool = field(default_factory=lambda: get_env_bool("ENABLE_INCIDENT_DETECTION", True))
    enable_density_estimation: bool = field(default_factory=lambda: get_env_bool("ENABLE_DENSITY_ESTIMATION", True))
    send_to_backend: bool = field(default_factory=lambda: get_env_bool("SEND_TO_BACKEND", False))
    backend_api_url: str = field(default_factory=lambda: os.getenv("BACKEND_API_URL", "http://127.0.0.1:8000"))

    # Model Weights Paths
    vehicle_model: str = "yolov8n.pt"
    defect_model: str = "models/road_defects/best.pt"
    plate_model: str = "models/number_plates/best.pt"
    
    # Performance & Timing Parameters
    density_interval_seconds: float = 1.0
    ocr_languages: List[str] = field(default_factory=lambda: ["en"])


@dataclass
class UnifiedEventRecord:
    """Standardized event record emitted by the edge AI pipeline."""
    event_id: str
    event_category: str  # ROAD_DEFECT, TRAFFIC_INCIDENT, TRAFFIC_DENSITY, ANPR
    event_type: str      # e.g. POTHOLE, RASH_DRIVING, HIGH_DENSITY, TS09EA1234
    confidence: float
    severity: str        # LOW, MEDIUM, HIGH, CRITICAL
    bus_id: str
    route_id: str
    camera_id: str
    timestamp: str       # ISO-8601 UTC timestamp from GPSVideoSynchronizer
    video_timestamp: float
    frame_number: int
    latitude: float
    longitude: float
    speed_kmh: float
    heading_deg: float
    evidence_image: Optional[str] = None
    details: Dict[str, Any] = field(default_factory=dict)
    is_simulated: bool = True
    disclaimer: str = INCIDENT_DISCLAIMER

    def to_dict(self) -> Dict[str, Any]:
        """Converts dataclass to serializable dictionary."""
        return asdict(self)


class EdgeAIPipeline:
    """Unified Edge AI Pipeline orchestrating vehicle tracking, density estimation,
    road defect detection, targeted ANPR, and incident detection with single-source GPS synchronization.
    """

    def __init__(self, config: Optional[PipelineConfig] = None):
        """Initializes the Edge AI Pipeline according to active engine toggles."""
        self.config = config or PipelineConfig()
        
        logger.info("=" * 80)
        logger.info("Initializing BusSense-AI Unified Edge AI Pipeline...")
        logger.info(f"Bus ID: {self.config.bus_id} | Route ID: {self.config.route_id} | Device: {self.config.device}")
        logger.info(f"Stage Toggles: Vehicle Detection={self.config.enable_vehicle_detection}, "
                    f"Road Defects={self.config.enable_road_defect_detection}, "
                    f"OCR={self.config.enable_ocr}, "
                    f"Incidents={self.config.enable_incident_detection}, "
                    f"Density={self.config.enable_density_estimation}, "
                    f"Backend Dispatch={self.config.send_to_backend}")
        logger.info("=" * 80)

        # 1. Vehicle Tracker & Counting (ByteTrack)
        if self.config.enable_vehicle_detection or self.config.enable_incident_detection or self.config.enable_density_estimation:
            logger.info("Loading Vehicle Tracker (YOLOv8 + ByteTrack)...")
            self.vehicle_tracker = VehicleTracker(
                model_path=self.config.vehicle_model,
                conf_threshold=self.config.conf_threshold,
                device=self.config.device,
                imgsz=self.config.imgsz,
            )
        else:
            logger.info("Vehicle Detection disabled: skipping vehicle tracker model.")
            self.vehicle_tracker = None

        # 2. Traffic Density Estimator
        if self.config.enable_density_estimation:
            logger.info("Initializing Traffic Density Estimator...")
            self.density_estimator = TrafficDensityEstimator(
                interval_seconds=self.config.density_interval_seconds,
            )
        else:
            logger.info("Traffic Density Estimation disabled.")
            self.density_estimator = None

        # 3. Road Defect Detector
        if self.config.enable_road_defect_detection:
            logger.info("Loading Road Defect Detector...")
            self.road_defect_detector = RoadDefectDetector(
                model_path=self.config.defect_model,
                conf_threshold=self.config.conf_threshold,
                device=self.config.device,
                bus_id=self.config.bus_id,
            )
        else:
            logger.info("Road Defect Detection disabled: skipping defect model.")
            self.road_defect_detector = None

        # 4. Number Plate Detector & OCR Engine (Targeted on demand)
        if self.config.enable_ocr:
            logger.info("Loading ANPR Plate Detector and OCR Engine...")
            self.plate_detector = PlateDetector(
                custom_weights_path=self.config.plate_model,
                conf_threshold=self.config.conf_threshold,
                device=self.config.device,
            )
            self.ocr_engine = OCREngine(
                languages=self.config.ocr_languages,
                gpu=(self.config.device == "cuda"),
                min_confidence=0.20,
            )
            self.validator = PlateValidator()
        else:
            logger.info("OCR Engine disabled: skipping OCR & plate models.")
            self.plate_detector = None
            self.ocr_engine = None
            self.validator = None

        # 5. Incident Detection Engine
        if self.config.enable_incident_detection:
            logger.info("Initializing Incident Detection Engine...")
            self.incident_detector = IncidentDetector(
                bus_id=self.config.bus_id,
                device=self.config.device,
                enable_ocr=False,  # Edge pipeline manages targeted OCR directly
            )
        else:
            logger.info("Incident Detection disabled: skipping incident engine.")
            self.incident_detector = None

        # Cache of confirmed license plates per track ID: track_id -> (plate_str, conf)
        self.best_plates: Dict[int, Tuple[str, float]] = {}
        self._last_defect_evidence_ts: Dict[str, float] = {}
        self._defect_clusters: Dict[str, Dict[str, Any]] = {}

        # Reset cumulative event log
        self.all_events: List[UnifiedEventRecord] = []
        self.interval_density_records: List[IntervalTrafficMeasurement] = []
        
        # Density interval streaming state
        self._density_interval_start_t: float = 0.0
        self._density_interval_active_ids: Set[int] = set()
        self._density_current_interval_idx: int = 0

    def reset_state(self) -> None:
        """Resets all sub-engine states for a new video stream."""
        if self.vehicle_tracker is not None:
            self.vehicle_tracker.reset_state()
        if self.incident_detector is not None:
            self.incident_detector.reset_state()
        self.best_plates.clear()
        self._last_defect_evidence_ts.clear()
        self._defect_clusters.clear()
        self.all_events.clear()
        self.interval_density_records.clear()
        self._density_interval_start_t = 0.0
        self._density_interval_active_ids.clear()
        self._density_current_interval_idx = 0

    def process_frame(
        self,
        frame: np.ndarray,
        frame_number: int,
        video_timestamp: float,
        gps_synchronizer: GPSVideoSynchronizer,
        output_evidence_dir: Optional[Union[str, Path]] = None,
    ) -> Tuple[Optional[FrameTrackingResult], List[RoadDefectDetection], List[UnifiedEventRecord]]:
        """Processes a single video frame through all enabled edge AI stages.

        Args:
            frame: OpenCV BGR image array.
            frame_number: Frame index (0-based).
            video_timestamp: Relative seconds from video start.
            gps_synchronizer: GPSVideoSynchronizer instance (single source of truth).
            output_evidence_dir: Directory path for exporting evidence images.

        Returns:
            Tuple of (FrameTrackingResult, List of RoadDefectDetections, List of new UnifiedEventRecords).
        """
        if frame is None or frame.size == 0:
            raise ValueError("Input frame is invalid or empty.")

        h, w = frame.shape[:2]
        new_events: List[UnifiedEventRecord] = []

        # 1. Synchronize GPS Position via GPSVideoSynchronizer (Single Source of Truth)
        pos = gps_synchronizer.get_position(video_timestamp=video_timestamp, interpolate=True)
        iso_time = pos.get("gps_timestamp") or ""
        lat = float(pos.get("latitude", 0.0))
        lon = float(pos.get("longitude", 0.0))
        spd = float(pos.get("speed", 0.0))
        hdg = float(pos.get("heading", 0.0))

        # 2. Stage A: Vehicle Tracking & Counting
        tracking_result: Optional[FrameTrackingResult] = None
        if self.vehicle_tracker is not None:
            tracking_result = self.vehicle_tracker.track_frame(
                frame=frame,
                frame_number=frame_number,
                video_timestamp=video_timestamp,
                conf_threshold=self.config.conf_threshold,
                imgsz=self.config.imgsz,
            )

        # 3. Stage B: Traffic Density Estimation
        if self.density_estimator is not None and tracking_result is not None:
            self.density_estimator.gps_sync = gps_synchronizer
            for det in tracking_result.detections:
                self._density_interval_active_ids.add(det.track_id)

            if (video_timestamp - self._density_interval_start_t) >= self.config.density_interval_seconds:
                int_counts: Dict[str, int] = {k: 0 for k in TARGET_VEHICLE_CLASSES.values()}
                for t_id in self._density_interval_active_ids:
                    c_type = self.vehicle_tracker.get_consensus_class(t_id) if self.vehicle_tracker else "car"
                    if c_type in int_counts:
                        int_counts[c_type] += 1
                    else:
                        int_counts[c_type] = int_counts.get(c_type, 0) + 1

                density_meas = self.density_estimator.create_interval_measurement(
                    interval_index=self._density_current_interval_idx,
                    start_time=self._density_interval_start_t,
                    end_time=video_timestamp,
                    car_count=int_counts.get("car", 0),
                    bus_count=int_counts.get("bus", 0),
                    truck_count=int_counts.get("truck", 0),
                    motorcycle_count=int_counts.get("motorcycle", 0),
                    bicycle_count=int_counts.get("bicycle", 0),
                    active_track_ids=sorted(list(self._density_interval_active_ids)),
                    unique_interval_track_ids=sorted(list(self._density_interval_active_ids)),
                )
                self.interval_density_records.append(density_meas)
                self._density_current_interval_idx += 1
                self._density_interval_start_t = video_timestamp
                self._density_interval_active_ids = set()

                evt = UnifiedEventRecord(
                    event_id=f"density_{self.config.bus_id}_{frame_number:06d}_{int(video_timestamp)}",
                    event_category="TRAFFIC_DENSITY",
                    event_type=density_meas.traffic_density,
                    confidence=1.0,
                    severity="LOW" if density_meas.traffic_density == "LOW" else ("MEDIUM" if density_meas.traffic_density == "MEDIUM" else "HIGH"),
                    bus_id=self.config.bus_id,
                    route_id=self.config.route_id,
                    camera_id=self.config.camera_id,
                    timestamp=iso_time,
                    video_timestamp=round(video_timestamp, 3),
                    frame_number=frame_number,
                    latitude=lat,
                    longitude=lon,
                    speed_kmh=spd,
                    heading_deg=hdg,
                    details=density_meas.to_dict(),
                )
                new_events.append(evt)
                self.all_events.append(evt)

        # 4. Stage C: Road Defect Detection
        defect_detections: List[RoadDefectDetection] = []
        if self.road_defect_detector is not None:
            defect_detections = self.road_defect_detector.detect_frame(
                frame=frame,
                frame_number=frame_number,
                video_timestamp=video_timestamp,
                conf_threshold=self.config.conf_threshold,
            )
            for defect in defect_detections:
                dtype_str = str(defect.defect_type.value if hasattr(defect.defect_type, "value") else defect.defect_type)
                sev_str = str(defect.severity.value if hasattr(defect.severity, "value") else defect.severity).upper()
                conf = round(float(defect.confidence), 3)

                # Meaningful filter: only persist events & save evidence for high-confidence / severe defects
                is_meaningful = conf >= 0.40 or sev_str in ("HIGH", "CRITICAL")
                if not is_meaningful:
                    continue

                # Spatio-temporal deduplication: group continuous sightings into a single physical encounter
                cluster = self._defect_clusters.get(dtype_str)
                is_existing_encounter = cluster is not None and (video_timestamp - cluster["last_ts"] < 5.0)

                if is_existing_encounter:
                    cluster["last_ts"] = video_timestamp
                    # If this frame provides a clearer/higher-confidence view, upgrade the evidence snapshot
                    if conf > cluster["best_conf"]:
                        cluster["best_conf"] = conf
                        if output_evidence_dir is not None and cluster.get("evidence_file"):
                            try:
                                ev_file = Path(cluster["evidence_file"])
                                annotated_defect = self.road_defect_detector.annotate_frame(
                                    frame=frame,
                                    detections=[defect],
                                )
                                cv2.imwrite(str(ev_file), annotated_defect)
                            except Exception as e:
                                logger.debug(f"Defect evidence update skipped: {e}")
                    # Skip emitting duplicate event for ongoing encounter
                    continue

                # Brand new defect encounter: emit 1 meaningful event and save 1 evidence snapshot
                evidence_path = None
                event_id = f"defect_{self.config.bus_id}_{dtype_str}_{frame_number:06d}"

                if output_evidence_dir is not None:
                    out_dir = Path(output_evidence_dir)
                    out_dir.mkdir(parents=True, exist_ok=True)
                    fname = f"defect_{self.config.bus_id}_{dtype_str}_{frame_number:06d}.jpg"
                    ev_file = out_dir / fname
                    
                    try:
                        annotated_defect = self.road_defect_detector.annotate_frame(
                            frame=frame,
                            detections=[defect],
                        )
                        cv2.imwrite(str(ev_file), annotated_defect)
                        evidence_path = str(ev_file)
                    except Exception as e:
                        logger.debug(f"Defect evidence write failed: {e}")

                self._defect_clusters[dtype_str] = {
                    "start_ts": video_timestamp,
                    "last_ts": video_timestamp,
                    "best_conf": conf,
                    "event_id": event_id,
                    "evidence_file": evidence_path,
                }

                evt = UnifiedEventRecord(
                    event_id=event_id,
                    event_category="ROAD_DEFECT",
                    event_type=dtype_str,
                    confidence=conf,
                    severity=sev_str,
                    bus_id=self.config.bus_id,
                    route_id=self.config.route_id,
                    camera_id=self.config.camera_id,
                    timestamp=iso_time,
                    video_timestamp=round(video_timestamp, 3),
                    frame_number=frame_number,
                    latitude=lat,
                    longitude=lon,
                    speed_kmh=spd,
                    heading_deg=hdg,
                    evidence_image=evidence_path,
                    details={
                        "bounding_box": defect.bounding_box,
                        "area": defect.area,
                        "centroid": list(defect.centroid),
                        "is_simulated": True,
                    },
                )
                new_events.append(evt)
                self.all_events.append(evt)

        # 5. Stage D: Incident Detection Engine
        if self.incident_detector is not None:
            _, new_incidents = self.incident_detector.process_frame(
                frame=frame,
                frame_number=frame_number,
                video_timestamp=video_timestamp,
                gps_synchronizer=gps_synchronizer,
                output_evidence_dir=Path(output_evidence_dir) if output_evidence_dir else None,
            )

            for inc in new_incidents:
                # 6. Stage E: Targeted ANPR on Incident-Flagged Vehicle
                reg_num = self.best_plates.get(inc.vehicle_tracking_id, (None, 0.0))[0]
                reg_conf = self.best_plates.get(inc.vehicle_tracking_id, (None, 0.0))[1]

                if self.config.enable_ocr and self.plate_detector is not None and self.ocr_engine is not None and not reg_num:
                    t_state = self.incident_detector.track_states.get(inc.vehicle_tracking_id)
                    if t_state and t_state["boxes"]:
                        v_box = t_state["boxes"][-1]
                        v_type = t_state.get("vehicle_type", "car")
                        plate_det = self.plate_detector.detect_plate_in_vehicle(frame, v_box, v_type)
                        if plate_det is not None and plate_det.plate_crop.size > 0:
                            ocr_res = self.ocr_engine.recognize_text(plate_det.plate_crop)
                            if ocr_res.raw_text:
                                val_res = self.validator.validate_and_normalize(ocr_res.raw_text)
                                if val_res.normalized_text:
                                    reg_num = val_res.normalized_text
                                    reg_conf = ocr_res.confidence
                                    self.best_plates[inc.vehicle_tracking_id] = (reg_num, reg_conf)

                evt = UnifiedEventRecord(
                    event_id=inc.incident_id,
                    event_category="TRAFFIC_INCIDENT",
                    event_type=inc.incident_type,
                    confidence=round(float(inc.event_confidence), 3),
                    severity=inc.severity,
                    bus_id=self.config.bus_id,
                    route_id=self.config.route_id,
                    camera_id=self.config.camera_id,
                    timestamp=iso_time,
                    video_timestamp=round(video_timestamp, 3),
                    frame_number=frame_number,
                    latitude=lat,
                    longitude=lon,
                    speed_kmh=spd,
                    heading_deg=hdg,
                    evidence_image=inc.evidence_image,
                    details={
                        "vehicle_tracking_id": inc.vehicle_tracking_id,
                        "registration_number": reg_num,
                        "registration_confidence": round(float(reg_conf), 3),
                        "status": inc.status,
                        "rule_details": inc.details,
                    },
                )
                new_events.append(evt)
                self.all_events.append(evt)

        # 7. Optional Non-Blocking Backend Dispatch
        if self.config.send_to_backend and new_events:
            self._dispatch_events_to_backend(new_events, pos)

        return tracking_result, defect_detections, new_events

    def _dispatch_events_to_backend(self, events: List[UnifiedEventRecord], gps_pos: Dict[str, Any]) -> None:
        """Sends events and telemetry to FastAPI backend with graceful timeout and error handling."""
        try:
            telemetry_payload = {
                "bus_id": self.config.bus_id,
                "route_id": self.config.route_id,
                "latitude": gps_pos.get("latitude", 0.0),
                "longitude": gps_pos.get("longitude", 0.0),
                "speed": gps_pos.get("speed", 0.0),
                "heading": gps_pos.get("heading", 0.0),
                "status": "active",
                "timestamp": gps_pos.get("gps_timestamp"),
            }
            req_data = json.dumps(telemetry_payload).encode("utf-8")
            req = urllib.request.Request(
                f"{self.config.backend_api_url}/api/v1/telemetry",
                data=req_data,
                headers={"Content-Type": "application/json"},
                method="POST",
            )
            with urllib.request.urlopen(req, timeout=0.5):
                pass
        except Exception as e:
            logger.debug(f"Backend telemetry dispatch skipped (offline/unreachable): {e}")

    def annotate_frame(
        self,
        frame: np.ndarray,
        tracking_result: Optional[FrameTrackingResult],
        defects: List[RoadDefectDetection],
        events: List[UnifiedEventRecord],
        gps_pos: Dict[str, Any],
        fps: float = 0.0,
    ) -> np.ndarray:
        """Renders unified high-contrast annotations with telemetry HUD, vehicle boxes,
        defect highlights, and active event alerts.
        """
        annotated = frame.copy()
        h, w = annotated.shape[:2]
        res_scale = max(1.0, min(w, h * 16 // 9) / 1280.0)

        # 1. Draw Vehicle Tracking Boxes & Labels
        if tracking_result is not None:
            for det in tracking_result.detections:
                t_id = det.track_id
                v_type = det.vehicle_type
                x1, y1, x2, y2 = det.bounding_box
                box_color = (245, 130, 48) if v_type == "car" else (34, 197, 94)

                thick = max(2, int(round(2.2 * res_scale)))
                cv2.rectangle(annotated, (x1, y1), (x2, y2), box_color, thick)

                reg_num = self.best_plates.get(t_id, (None, 0.0))[0]
                lbl = f"#{t_id} {v_type.upper()}"
                if reg_num:
                    lbl += f" [{reg_num}]"

                font_scale = 0.55 * res_scale
                font_thick = max(1, int(round(1.5 * res_scale)))
                (tw, th), tb = cv2.getTextSize(lbl, cv2.FONT_HERSHEY_DUPLEX, font_scale, font_thick)
                cv2.rectangle(annotated, (x1, max(0, y1 - th - 8)), (x1 + tw + 10, y1), (20, 22, 28), -1)
                cv2.rectangle(annotated, (x1, max(0, y1 - th - 8)), (x1 + tw + 10, y1), box_color, 1)
                cv2.putText(annotated, lbl, (x1 + 5, y1 - 4), cv2.FONT_HERSHEY_DUPLEX, font_scale, (255, 255, 255), font_thick, cv2.LINE_AA)

        # 2. Draw Road Defect Annotations
        for defect in defects:
            dx1, dy1, dx2, dy2 = defect.bounding_box
            dtype_val = defect.defect_type.value if hasattr(defect.defect_type, "value") else defect.defect_type
            d_color = DEFECT_COLORS.get(dtype_val, (0, 0, 255))
            thick = max(2, int(round(2.4 * res_scale)))
            cv2.rectangle(annotated, (dx1, dy1), (dx2, dy2), d_color, thick)

            d_lbl = f"{dtype_val} ({defect.confidence * 100:.0f}%)"
            font_scale = 0.55 * res_scale
            font_thick = max(1, int(round(1.5 * res_scale)))
            (dtw, dth), dtb = cv2.getTextSize(d_lbl, cv2.FONT_HERSHEY_DUPLEX, font_scale, font_thick)
            cv2.rectangle(annotated, (dx1, max(0, dy1 - dth - 8)), (dx1 + dtw + 10, dy1), (20, 22, 28), -1)
            cv2.rectangle(annotated, (dx1, max(0, dy1 - dth - 8)), (dx1 + dtw + 10, dy1), d_color, 1)
            cv2.putText(annotated, d_lbl, (dx1 + 5, dy1 - 4), cv2.FONT_HERSHEY_DUPLEX, font_scale, (255, 255, 255), font_thick, cv2.LINE_AA)

        # 3. Draw Top Telemetry HUD Banner
        hud_h = int(round(84 * res_scale))
        overlay = annotated.copy()
        cv2.rectangle(overlay, (0, 0), (w, hud_h), (16, 18, 24), -1)
        cv2.addWeighted(overlay, 0.88, annotated, 0.12, 0, annotated)
        cv2.line(annotated, (0, hud_h), (w, hud_h), (0, 200, 255), max(2, int(2 * res_scale)))

        hud_font_scale = 0.54 * res_scale
        hud_thick = max(1, int(round(1.4 * res_scale)))

        active_veh_cnt = len(tracking_result.detections) if tracking_result else 0
        total_veh_cnt = len(self.vehicle_tracker.all_seen_track_ids) if self.vehicle_tracker else 0
        
        line1 = (
            f"BusSense-AI Edge Pipeline | Bus: {self.config.bus_id} (Rte {self.config.route_id}) | "
            f"Active: {active_veh_cnt} | Cumulative: {total_veh_cnt} | Events: {len(self.all_events)}"
        )
        if fps > 0:
            line1 += f" | {fps:.1f} FPS"

        lat = float(gps_pos.get("latitude", 0.0))
        lon = float(gps_pos.get("longitude", 0.0))
        spd = float(gps_pos.get("speed", 0.0))
        hdg = float(gps_pos.get("heading", 0.0))
        ts_str = str(gps_pos.get("gps_timestamp", "")).replace("T", " ")[:19]

        line2 = f"GPS: {lat:.6f}, {lon:.6f} | Speed: {spd:.1f} km/h (Hdg {hdg:.0f}°) | Time: {ts_str} UTC"

        cv2.putText(annotated, line1, (int(16 * res_scale), int(32 * res_scale)), cv2.FONT_HERSHEY_SIMPLEX, hud_font_scale, (255, 255, 255), hud_thick, cv2.LINE_AA)
        cv2.putText(annotated, line2, (int(16 * res_scale), int(64 * res_scale)), cv2.FONT_HERSHEY_SIMPLEX, hud_font_scale * 0.92, (140, 210, 255), hud_thick, cv2.LINE_AA)

        return annotated

    def run(
        self,
        video_path: Union[str, Path],
        gps_path: Union[str, Path],
        output_video_path: Optional[Union[str, Path]] = None,
        output_json_path: Optional[Union[str, Path]] = None,
        output_evidence_dir: Optional[Union[str, Path]] = None,
        max_frames: Optional[int] = None,
    ) -> Dict[str, Any]:
        """Runs the entire edge AI processing pipeline from video and GPS inputs."""
        v_path = Path(video_path)
        g_path = Path(gps_path)

        if not v_path.exists():
            raise FileNotFoundError(f"Input video not found: {v_path}")
        if not g_path.exists():
            raise FileNotFoundError(f"Input GPS CSV not found: {g_path}")

        self.reset_state()

        logger.info(f"Initializing GPSVideoSynchronizer from: {g_path}")
        gps_sync = GPSVideoSynchronizer(
            gps_source=g_path,
            bus_id=self.config.bus_id,
            camera_id=self.config.camera_id,
        )

        cap = cv2.VideoCapture(str(v_path))
        if not cap.isOpened():
            raise RuntimeError(f"Failed to open video file: {v_path}")

        fps = cap.get(cv2.CAP_PROP_FPS) or 30.0
        width = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
        height = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
        total_video_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))

        writer = None
        if output_video_path is not None:
            out_v = Path(output_video_path)
            out_v.parent.mkdir(parents=True, exist_ok=True)
            fourcc = cv2.VideoWriter_fourcc(*"mp4v")
            writer = cv2.VideoWriter(str(out_v), fourcc, fps, (width, height))

        if output_evidence_dir is not None:
            Path(output_evidence_dir).mkdir(parents=True, exist_ok=True)

        logger.info(f"Processing edge AI pipeline on {v_path.name} ({width}x{height} @ {fps:.1f} FPS, {total_video_frames} frames)...")

        frame_idx = 0
        t_start = time.time()

        try:
            while True:
                ret, frame = cap.read()
                if not ret or frame is None:
                    break

                video_ts = frame_idx / fps

                # Process frame through all active stages
                tracking_res, defects, new_evts = self.process_frame(
                    frame=frame,
                    frame_number=frame_idx,
                    video_timestamp=video_ts,
                    gps_synchronizer=gps_sync,
                    output_evidence_dir=output_evidence_dir,
                )

                # Annotate and write output video
                if writer is not None:
                    pos = gps_sync.get_position(video_timestamp=video_ts)
                    ann = self.annotate_frame(
                        frame=frame,
                        tracking_result=tracking_res,
                        defects=defects,
                        events=new_evts,
                        gps_pos=pos,
                        fps=fps,
                    )
                    writer.write(ann)

                frame_idx += 1
                if frame_idx % 60 == 0:
                    elapsed = time.time() - t_start
                    cur_fps = frame_idx / max(0.001, elapsed)
                    logger.info(f"Processed {frame_idx}/{total_video_frames} frames ({cur_fps:.1f} FPS) | Cumulative Events: {len(self.all_events)}")

                if max_frames is not None and frame_idx >= max_frames:
                    break

        finally:
            cap.release()
            if writer is not None:
                writer.release()

        # Finalize open density measurement interval
        if self.density_estimator is not None and (self._density_interval_active_ids or (frame_idx > 0 and len(self.interval_density_records) == 0)):
            final_t = frame_idx / float(fps)
            int_counts = {k: 0 for k in TARGET_VEHICLE_CLASSES.values()}
            for t_id in self._density_interval_active_ids:
                c_type = self.vehicle_tracker.get_consensus_class(t_id) if self.vehicle_tracker else "car"
                if c_type in int_counts:
                    int_counts[c_type] += 1
                else:
                    int_counts[c_type] = int_counts.get(c_type, 0) + 1

            final_meas = self.density_estimator.create_interval_measurement(
                interval_index=self._density_current_interval_idx,
                start_time=self._density_interval_start_t,
                end_time=final_t,
                car_count=int_counts.get("car", 0),
                bus_count=int_counts.get("bus", 0),
                truck_count=int_counts.get("truck", 0),
                motorcycle_count=int_counts.get("motorcycle", 0),
                bicycle_count=int_counts.get("bicycle", 0),
                active_track_ids=sorted(list(self._density_interval_active_ids)),
                unique_interval_track_ids=sorted(list(self._density_interval_active_ids)),
            )
            self.interval_density_records.append(final_meas)

        elapsed_total = time.time() - t_start
        fps_overall = frame_idx / max(0.001, elapsed_total)
        logger.info(f"Pipeline completed: {frame_idx} frames processed in {elapsed_total:.2f}s ({fps_overall:.1f} FPS).")

        events_by_category = defaultdict(int)
        for ev in self.all_events:
            events_by_category[ev.event_category] += 1

        summary = {
            "bus_id": self.config.bus_id,
            "route_id": self.config.route_id,
            "total_frames_processed": frame_idx,
            "elapsed_seconds": round(elapsed_total, 2),
            "processing_fps": round(fps_overall, 1),
            "total_events_generated": len(self.all_events),
            "events_by_category": dict(events_by_category),
            "unique_vehicles_counted": len(self.vehicle_tracker.all_seen_track_ids) if self.vehicle_tracker else 0,
            "unique_vehicle_classes": self.vehicle_tracker.get_cumulative_unique_counts_by_type() if self.vehicle_tracker else {},
            "traffic_density_intervals_recorded": len(self.interval_density_records),
            "events": [e.to_dict() for e in self.all_events],
            "is_simulated": True,
        }

        # ── Edge Processing Bandwidth Metrics ─────────────────────────────
        # Proves: raw video stays at edge, only slim event metadata transmitted.
        raw_frame_bytes = width * height * 3  # BGR uncompressed
        raw_video_bytes = frame_idx * raw_frame_bytes

        slim_payloads = []
        for ev in self.all_events:
            slim = {
                "event_type": ev.event_type,
                "confidence": round(ev.confidence, 3),
                "bus_id": ev.bus_id,
                "timestamp": ev.timestamp,
                "latitude": round(ev.latitude, 6),
                "longitude": round(ev.longitude, 6),
                "tracking_id": ev.details.get("vehicle_tracking_id") if ev.details else None,
                "registration_number": ev.details.get("registration_number") if ev.details else None,
                "evidence_image_ref": ev.evidence_image,
            }
            slim_payloads.append(slim)

        transmitted_event_bytes = sum(len(json.dumps(s, default=str).encode("utf-8")) for s in slim_payloads)

        # Calculate actual evidence image sizes
        evidence_bytes = 0
        for ev in self.all_events:
            if ev.evidence_image and Path(ev.evidence_image).exists():
                try:
                    evidence_bytes += Path(ev.evidence_image).stat().st_size
                except OSError:
                    pass

        total_transmitted = transmitted_event_bytes + evidence_bytes
        reduction_pct = round((1.0 - total_transmitted / max(1, raw_video_bytes)) * 100, 2) if raw_video_bytes > 0 else 0.0

        def _fmt_bytes(n: int) -> str:
            if n < 1024: return f"{n} B"
            if n < 1024**2: return f"{n/1024:.2f} KB"
            if n < 1024**3: return f"{n/(1024**2):.2f} MB"
            return f"{n/(1024**3):.2f} GB"

        summary["edge_processing_metrics"] = {
            "frames_processed_locally": frame_idx,
            "events_generated": len(self.all_events),
            "video_resolution": f"{width}x{height}",
            "video_fps": fps,
            "raw_frame_size_bytes": raw_frame_bytes,
            "raw_video_data_bytes": raw_video_bytes,
            "raw_video_data_display": _fmt_bytes(raw_video_bytes),
            "transmitted_event_data_bytes": transmitted_event_bytes,
            "transmitted_event_data_display": _fmt_bytes(transmitted_event_bytes),
            "evidence_images_bytes": evidence_bytes,
            "evidence_images_display": _fmt_bytes(evidence_bytes),
            "total_transmitted_bytes": total_transmitted,
            "total_transmitted_display": _fmt_bytes(total_transmitted),
            "bandwidth_reduction_pct": max(0.0, min(100.0, reduction_pct)),
            "per_event_payload_example": slim_payloads[0] if slim_payloads else {},
            "events_payload_fields": [
                "event_type", "confidence", "bus_id", "timestamp",
                "latitude", "longitude", "tracking_id",
                "registration_number", "evidence_image_ref"
            ],
            "disclaimer": "Estimate based on this prototype's processing run — not a general industry claim.",
            "is_simulated": True,
        }

        logger.info(
            f"Edge Bandwidth Metrics: Raw video ~{_fmt_bytes(raw_video_bytes)}, "
            f"Transmitted ~{_fmt_bytes(total_transmitted)}, "
            f"Reduction ~{reduction_pct:.2f}%"
        )

        if output_json_path is not None:
            out_j = Path(output_json_path)
            out_j.parent.mkdir(parents=True, exist_ok=True)
            with open(out_j, "w", encoding="utf-8") as f:
                json.dump(summary, f, indent=2, default=str)
            logger.info(f"Exported structured pipeline summary to: {out_j}")

        return summary


# ==============================================================================
# CLI RUNNER ENTRYPOINT
# ==============================================================================

def parse_args():
    """Parses command line arguments for standalone execution."""
    parser = argparse.ArgumentParser(
        description="BusSense-AI Unified Edge AI Processing Pipeline (SIH26124)",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    parser.add_argument("--video", type=str, required=True, help="Path to input video stream/file")
    parser.add_argument("--gps", type=str, required=True, help="Path to input GPS trajectory CSV")
    parser.add_argument("--bus-id", type=str, default="BUS_101", help="Transit bus fleet ID")
    parser.add_argument("--route-id", type=str, default="216", help="Transit route identifier")
    parser.add_argument("--out-video", type=str, default=None, help="Destination for annotated video MP4")
    parser.add_argument("--out-json", type=str, default=None, help="Destination for structured JSON events")
    parser.add_argument("--out-dir", type=str, default="data/outputs/unified_evidence", help="Evidence directory")
    parser.add_argument("--max-frames", type=int, default=None, help="Cap maximum frames processed")
    parser.add_argument("--conf", type=float, default=0.25, help="Perception confidence threshold")
    parser.add_argument("--device", type=str, default="cpu", help="Inference device (cpu, cuda, mps)")
    parser.add_argument("--send-backend", action="store_true", help="Send telemetry and events to FastAPI backend")
    parser.add_argument("--api-url", type=str, default="http://127.0.0.1:8000", help="FastAPI backend URL")
    
    # Engine toggles
    parser.add_argument("--no-vehicles", action="store_true", help="Disable vehicle tracking stage")
    parser.add_argument("--no-defects", action="store_true", help="Disable road defect detection stage")
    parser.add_argument("--no-ocr", action="store_true", help="Disable OCR number plate extraction stage")
    parser.add_argument("--no-incidents", action="store_true", help="Disable incident detection stage")
    parser.add_argument("--no-density", action="store_true", help="Disable traffic density estimation stage")
    
    return parser.parse_args()


def main():
    """Main CLI execution handler."""
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        datefmt="%H:%M:%S",
    )
    args = parse_args()

    print("=" * 80)
    print(" BusSense-AI — Unified Edge AI Processing Pipeline (SIH26124)")
    print(f" NOTE: {INCIDENT_DISCLAIMER.upper()}")
    print("=" * 80)
    print(f" Input Video:        {args.video}")
    print(f" GPS Trajectory:     {args.gps}")
    print(f" Bus ID / Route ID:  {args.bus_id} / Route {args.route_id}")
    print(f" Output Video:       {args.out_video}")
    print(f" Output JSON:        {args.out_json}")
    print(f" Evidence Dir:       {args.out_dir}")
    print(f" Send to Backend:    {args.send_backend} ({args.api_url})")
    print("=" * 80)

    config = PipelineConfig(
        bus_id=args.bus_id,
        route_id=args.route_id,
        device=args.device,
        conf_threshold=args.conf,
        enable_vehicle_detection=not args.no_vehicles,
        enable_road_defect_detection=not args.no_defects,
        enable_ocr=not args.no_ocr,
        enable_incident_detection=not args.no_incidents,
        enable_density_estimation=not args.no_density,
        send_to_backend=args.send_backend,
        backend_api_url=args.api_url,
    )

    pipeline = EdgeAIPipeline(config=config)

    summary = pipeline.run(
        video_path=args.video,
        gps_path=args.gps,
        output_video_path=args.out_video,
        output_json_path=args.out_json,
        output_evidence_dir=args.out_dir,
        max_frames=args.max_frames,
    )

    print("\n" + "=" * 80)
    print(" Pipeline Execution Summary")
    print("=" * 80)
    print(f" Total Frames Processed:    {summary['total_frames_processed']}")
    print(f" Processing Speed:          {summary['processing_fps']:.1f} FPS ({summary['elapsed_seconds']:.2f}s total)")
    print(f" Total Events Generated:    {summary['total_events_generated']}")
    for cat, cnt in summary["events_by_category"].items():
        print(f"   • {cat:22s}: {cnt}")
    print(f" Unique Vehicles Counted:   {summary['unique_vehicles_counted']}")
    for v_class, cnt in summary["unique_vehicle_classes"].items():
        print(f"   - {v_class:10s}: {cnt}")
    print(f" Density Windows Logged:    {summary['traffic_density_intervals_recorded']}")
    if args.out_video:
        print(f" Output Annotated Video:    {args.out_video}")
    if args.out_json:
        print(f" Output Structured JSON:    {args.out_json}")
    print(f" Saved Evidence Directory:  {args.out_dir}")
    print("=" * 80)


if __name__ == "__main__":
    main()
