"""Multi-Object Vehicle Tracker & Traffic Density Pipeline for BusSense-AI.

================================================================================
DISCLAIMER:
All traffic density classifications and statistics are PROTOTYPE TRAFFIC-DENSITY
ESTIMATIONS for the SIH26124 mobile urban intelligence platform demonstration.
================================================================================

Integrates Ultralytics YOLOv8 with ByteTrack for persistent vehicle tracking,
unique vehicle lifetime counting (preventing recount of identical vehicles across
consecutive frames), visual trajectory path rendering, and interval aggregation
with GPSVideoSynchronizer.
"""

import sys
import time
import logging
from pathlib import Path
from dataclasses import dataclass, field, asdict
from typing import Dict, Any, List, Optional, Union, Tuple, Set
from collections import defaultdict, deque
import json

import cv2
import numpy as np
from ultralytics import YOLO

from ai.pipeline.gps_sync import GPSVideoSynchronizer
from ai.tracking.density_estimator import (
    TrafficDensityEstimator,
    IntervalTrafficMeasurement,
    TrafficDensity,
    DEFAULT_LOW_DENSITY_MAX,
    DEFAULT_MEDIUM_DENSITY_MAX,
    DEFAULT_INTERVAL_SECONDS,
)

logger = logging.getLogger(__name__)

# COCO Class Mapping for Target Transit Vehicles
TARGET_VEHICLE_CLASSES = {
    1: "bicycle",
    2: "car",
    3: "motorcycle",
    5: "bus",
    7: "truck",
}

# Distinct BGR Colors for bounding boxes and badges
CLASS_COLORS = {
    "car": (245, 130, 48),         # Blue/Cyan
    "bus": (34, 197, 94),          # Green
    "truck": (30, 144, 255),       # Amber / Orange
    "motorcycle": (180, 50, 200),  # Purple
    "bicycle": (235, 51, 153),     # Magenta / Pink
}

DENSITY_COLORS = {
    "LOW": (34, 197, 94),          # Green
    "MEDIUM": (0, 165, 255),       # Orange
    "HIGH": (30, 30, 220),         # Red
}


@dataclass
class TrackedVehicleDetection:
    """Represents a single tracked vehicle detection in a frame."""
    track_id: int
    class_id: int
    vehicle_type: str
    confidence: float
    bounding_box: List[int]  # [x1, y1, x2, y2]
    area: int
    centroid: Tuple[int, int] = (0, 0)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "track_id": self.track_id,
            "class_id": self.class_id,
            "vehicle_type": self.vehicle_type,
            "confidence": round(float(self.confidence), 3),
            "bounding_box": self.bounding_box,
            "area": self.area,
            "centroid": list(self.centroid),
        }


@dataclass
class FrameTrackingResult:
    """Represents tracking state and vehicle counts for a single video frame."""
    frame_number: int
    video_timestamp: float
    detections: List[TrackedVehicleDetection]
    live_counts_by_type: Dict[str, int]
    live_total_vehicles: int
    cumulative_unique_counts_by_type: Dict[str, int]
    cumulative_total_unique_vehicles: int
    traffic_density: str = "LOW"

    def to_dict(self) -> Dict[str, Any]:
        return {
            "frame_number": self.frame_number,
            "video_timestamp": round(self.video_timestamp, 3),
            "live_total_vehicles": self.live_total_vehicles,
            "live_counts_by_type": self.live_counts_by_type,
            "cumulative_total_unique_vehicles": self.cumulative_total_unique_vehicles,
            "cumulative_unique_counts_by_type": self.cumulative_unique_counts_by_type,
            "traffic_density": self.traffic_density,
            "detections": [d.to_dict() for d in self.detections],
        }


class VehicleTracker:
    """Multi-object vehicle tracker with persistent ID assignment and recount prevention."""

    def __init__(
        self,
        model_path: Union[str, Path] = "yolov8n.pt",
        conf_threshold: float = 0.25,
        iou_threshold: float = 0.45,
        tracker_type: str = "bytetrack.yaml",
        device: str = "cpu",
        low_density_max: int = DEFAULT_LOW_DENSITY_MAX,
        medium_density_max: int = DEFAULT_MEDIUM_DENSITY_MAX,
        interval_seconds: float = DEFAULT_INTERVAL_SECONDS,
        track_history_length: int = 30,
        imgsz: int = 640,
        agnostic_nms: bool = True,
    ):
        """Initializes the VehicleTracker.

        Args:
            model_path: Path to YOLO weights or model identifier.
            conf_threshold: Minimum confidence score for detection.
            iou_threshold: IoU threshold for NMS.
            tracker_type: Ultralytics tracking configuration (default: 'bytetrack.yaml').
            device: Compute device ('cpu', 'cuda', 'mps').
            low_density_max: Max vehicles for LOW density.
            medium_density_max: Max vehicles for MEDIUM density.
            interval_seconds: Discrete measurement time window in seconds.
            track_history_length: Max historical centroids stored for trajectory trail rendering.
            imgsz: Input resolution for inference (default: 640).
            agnostic_nms: Prevent multi-class overlapping duplicate bounding boxes.
        """
        self.model_path = Path(model_path)
        self.conf_threshold = conf_threshold
        self.iou_threshold = iou_threshold
        self.tracker_type = tracker_type
        self.device = device
        self.track_history_length = track_history_length
        self.imgsz = imgsz
        self.agnostic_nms = agnostic_nms

        self.density_estimator = TrafficDensityEstimator(
            gps_synchronizer=None,
            low_max=low_density_max,
            medium_max=medium_density_max,
            interval_seconds=interval_seconds,
        )

        # Resolve model weights path
        resolved_weights = self._resolve_model_path(model_path)
        logger.info(f"Loading YOLO tracking model from: {resolved_weights}")
        self.model = YOLO(str(resolved_weights))

        # Target classes subset
        self.target_classes = TARGET_VEHICLE_CLASSES
        self.target_class_ids = list(self.target_classes.keys())

        # Persistent Tracking State
        self.reset_state()

    def reset_state(self) -> None:
        """Resets all tracking histories, unique vehicle IDs, consensus votes, and counters."""
        # Temporal confidence-weighted class votes per track_id: track_id -> Dict[vehicle_type, float_score]
        self.track_class_votes: Dict[int, Dict[str, float]] = defaultdict(lambda: defaultdict(float))
        # Unique set of all track IDs observed across the video lifetime
        self.all_seen_track_ids: Set[int] = set()
        # Track history for motion trail visualization: track_id -> deque of (cx, cy)
        self.track_trajectories: Dict[int, deque] = defaultdict(lambda: deque(maxlen=self.track_history_length))
        # Fallback counter for untracked detections
        self._untracked_id_seq = 10000

    @property
    def seen_track_ids_by_type(self) -> Dict[str, Set[int]]:
        """Returns partition of unique track IDs mapped strictly to their consensus vehicle class."""
        by_type: Dict[str, Set[int]] = {k: set() for k in self.target_classes.values()}
        for t_id in self.all_seen_track_ids:
            c = self.get_consensus_class(t_id)
            if c in by_type:
                by_type[c].add(t_id)
            else:
                by_type[c] = {t_id}
        return by_type

    def get_consensus_class(self, track_id: int, fallback_class: str = "car") -> str:
        """Computes the dominant consensus class for a given track ID via confidence voting.

        Args:
            track_id: Persistent tracking ID.
            fallback_class: Default class if no votes exist yet.

        Returns:
            Dominant vehicle type string (e.g. 'car', 'bus', 'truck', 'motorcycle', 'bicycle').
        """
        votes = self.track_class_votes.get(track_id)
        if not votes:
            return fallback_class
        # Dominant class with highest accumulated confidence
        return max(votes.items(), key=lambda x: x[1])[0]

    def get_cumulative_unique_counts_by_type(self) -> Dict[str, int]:
        """Calculates exact unique vehicle counts per vehicle type using consensus voting."""
        counts = {k: 0 for k in self.target_classes.values()}
        for t_id in self.all_seen_track_ids:
            c = self.get_consensus_class(t_id)
            if c in counts:
                counts[c] += 1
            else:
                counts[c] = counts.get(c, 0) + 1
        return counts

    def _resolve_model_path(self, model_name_or_path: Union[str, Path]) -> Path:
        """Locates model weights in local models/ directory or project paths."""
        p = Path(model_name_or_path)
        if p.exists():
            return p

        # Check in project models/ folder
        project_root = Path(__file__).resolve().parent.parent.parent
        in_models_dir = project_root / "models" / p.name
        if in_models_dir.exists():
            return in_models_dir

        return p

    def track_frame(
        self,
        frame: np.ndarray,
        frame_number: int = 0,
        video_timestamp: float = 0.0,
        conf_threshold: Optional[float] = None,
        imgsz: Optional[int] = None,
    ) -> FrameTrackingResult:
        """Processes a single video frame, tracks vehicles, and updates cumulative unique counts.

        Args:
            frame: OpenCV BGR image array.
            frame_number: Sequential frame index.
            video_timestamp: Video timestamp in seconds.
            conf_threshold: Optional override for confidence threshold.
            imgsz: Optional override for inference input size.

        Returns:
            FrameTrackingResult containing tracked detections and counts.
        """
        if frame is None or not isinstance(frame, np.ndarray) or frame.size == 0:
            raise ValueError("Input frame is invalid, empty, or corrupted.")

        conf = conf_threshold if conf_threshold is not None else self.conf_threshold
        inference_imgsz = imgsz if imgsz is not None else self.imgsz

        # Run ByteTrack via Ultralytics track API with persistent state & class-agnostic NMS
        results = self.model.track(
            source=frame,
            persist=True,
            tracker=self.tracker_type,
            conf=conf,
            iou=self.iou_threshold,
            classes=self.target_class_ids,
            agnostic_nms=self.agnostic_nms,
            imgsz=inference_imgsz,
            device=self.device,
            verbose=False,
        )

        detections: List[TrackedVehicleDetection] = []
        live_counts: Dict[str, int] = {name: 0 for name in self.target_classes.values()}

        if results and len(results) > 0:
            boxes = results[0].boxes
            if boxes is not None and len(boxes) > 0:
                xyxy_arr = boxes.xyxy.cpu().numpy()
                conf_arr = boxes.conf.cpu().numpy()
                cls_arr = boxes.cls.cpu().numpy().astype(int)
                track_ids = boxes.id.cpu().numpy().astype(int) if boxes.id is not None else None

                for i, (xyxy, score, cls_id) in enumerate(zip(xyxy_arr, conf_arr, cls_arr)):
                    if cls_id in self.target_classes:
                        raw_v_type = self.target_classes[cls_id]
                        x1, y1, x2, y2 = [int(round(coord)) for coord in xyxy]
                        area = max(0, x2 - x1) * max(0, y2 - y1)
                        cx = int((x1 + x2) / 2)
                        cy = int((y1 + y2) / 2)

                        # Assign persistent track ID
                        if track_ids is not None and i < len(track_ids):
                            t_id = int(track_ids[i])
                        else:
                            # Fallback if tracker dropped ID
                            t_id = self._untracked_id_seq
                            self._untracked_id_seq += 1

                        # Register confidence vote for track consensus
                        self.track_class_votes[t_id][raw_v_type] += float(score)
                        self.all_seen_track_ids.add(t_id)

                        # Determine smoothed consensus vehicle class
                        consensus_v_type = self.get_consensus_class(t_id, fallback_class=raw_v_type)

                        # Record trajectory history
                        self.track_trajectories[t_id].append((cx, cy))

                        det = TrackedVehicleDetection(
                            track_id=t_id,
                            class_id=int(cls_id),
                            vehicle_type=consensus_v_type,
                            confidence=float(score),
                            bounding_box=[x1, y1, x2, y2],
                            area=area,
                            centroid=(cx, cy),
                        )
                        detections.append(det)
                        live_counts[consensus_v_type] = live_counts.get(consensus_v_type, 0) + 1

        live_total = sum(live_counts.values())
        cum_counts = self.get_cumulative_unique_counts_by_type()
        cum_total = len(self.all_seen_track_ids)
        density = self.density_estimator.classify_density(live_total).value

        return FrameTrackingResult(
            frame_number=frame_number,
            video_timestamp=video_timestamp,
            detections=detections,
            live_counts_by_type=live_counts,
            live_total_vehicles=live_total,
            cumulative_unique_counts_by_type=cum_counts,
            cumulative_total_unique_vehicles=cum_total,
            traffic_density=density,
        )

    def annotate_frame(
        self,
        frame: np.ndarray,
        result: FrameTrackingResult,
        density_label: Optional[str] = None,
        show_hud: bool = True,
        show_trails: bool = True,
        fps: float = 0.0,
    ) -> np.ndarray:
        """Annotates video frame with resolution-scaled track IDs, bounding boxes, motion trails, and HUD banner."""
        annotated = frame.copy()
        h, w = annotated.shape[:2]

        current_density = density_label or result.traffic_density
        density_color = DENSITY_COLORS.get(current_density, (34, 197, 94))

        # Dynamic resolution scaling factor (normalized against 1280x720 baseline)
        res_scale = max(1.0, min(w, h * 16 // 9) / 1280.0)
        box_thick = max(2, int(round(2.2 * res_scale)))
        font_scale = max(0.55, 0.52 * res_scale)
        font_thick = max(1, int(round(1.5 * res_scale)))
        trail_thick = max(2, int(round(2.0 * res_scale)))
        trail_dot_r = max(4, int(round(4.0 * res_scale)))

        font = cv2.FONT_HERSHEY_SIMPLEX

        # 1. Draw Trajectory Motion Trails
        if show_trails:
            for det in result.detections:
                traj = self.track_trajectories.get(det.track_id, [])
                if len(traj) > 1:
                    pts = np.array(list(traj), dtype=np.int32).reshape((-1, 1, 2))
                    trail_color = CLASS_COLORS.get(det.vehicle_type, (0, 255, 0))
                    cv2.polylines(annotated, [pts], isClosed=False, color=trail_color, thickness=trail_thick, lineType=cv2.LINE_AA)
                    cv2.circle(annotated, det.centroid, trail_dot_r, trail_color, -1)

        # 2. Draw Bounding Boxes and High-Contrast Track ID Badges
        for det in result.detections:
            x1, y1, x2, y2 = det.bounding_box
            color = CLASS_COLORS.get(det.vehicle_type, (0, 255, 0))

            cv2.rectangle(annotated, (x1, y1), (x2, y2), color, box_thick)

            # Badge: #ID TYPE CONF
            badge_text = f"#{det.track_id} {det.vehicle_type.upper()} {det.confidence:.2f}"
            (text_w, text_h), baseline = cv2.getTextSize(badge_text, font, font_scale, font_thick)

            pad_x = int(6 * res_scale)
            pad_y = int(5 * res_scale)

            badge_y1 = max(0, y1 - text_h - 2 * pad_y)
            badge_y2 = y1
            badge_x2 = min(w, x1 + text_w + 2 * pad_x)

            # Draw solid saturated badge
            cv2.rectangle(annotated, (x1, badge_y1), (badge_x2, badge_y2), color, -1)
            cv2.rectangle(annotated, (x1, badge_y1), (badge_x2, badge_y2), (15, 23, 42), max(1, int(res_scale)))

            # High contrast text with dark drop shadow for maximum visibility
            text_pos = (x1 + pad_x, y1 - pad_y)
            # Outline / drop shadow
            cv2.putText(annotated, badge_text, text_pos, font, font_scale, (0, 0, 0), font_thick + 2, cv2.LINE_AA)
            # Crisp white text
            cv2.putText(annotated, badge_text, text_pos, font, font_scale, (255, 255, 255), font_thick, cv2.LINE_AA)

        # 3. Draw Top HUD Banner (Counters & Density Badge)
        if show_hud:
            hud_w = int(480 * res_scale)
            hud_h = int(120 * res_scale)
            hud_x = int(15 * res_scale)
            hud_y = int(15 * res_scale)

            overlay = annotated.copy()
            cv2.rectangle(overlay, (hud_x, hud_y), (hud_x + hud_w, hud_y + hud_h), (15, 23, 42), -1)
            cv2.addWeighted(overlay, 0.88, annotated, 0.12, 0, annotated)
            cv2.rectangle(annotated, (hud_x, hud_y), (hud_x + hud_w, hud_y + hud_h), (56, 189, 248), max(1, int(1.5 * res_scale)))

            hud_font_scale1 = max(0.48, 0.44 * res_scale)
            hud_font_scale2 = max(0.60, 0.58 * res_scale)
            hud_font_scale3 = max(0.46, 0.42 * res_scale)
            hud_thick1 = max(1, int(1.2 * res_scale))
            hud_thick2 = max(2, int(1.8 * res_scale))

            # Line 1: Header
            l1_y = hud_y + int(24 * res_scale)
            cv2.putText(annotated, "BusSense-AI | Vehicle Tracker & Density (Prototype)", (hud_x + int(12 * res_scale), l1_y), font, hud_font_scale1, (56, 189, 248), hud_thick1, cv2.LINE_AA)

            # Line 2: Density Badge
            l2_y = hud_y + int(52 * res_scale)
            cv2.putText(annotated, "TRAFFIC DENSITY: ", (hud_x + int(12 * res_scale), l2_y), font, hud_font_scale2, (255, 255, 255), hud_thick1, cv2.LINE_AA)
            (td_w, _), _ = cv2.getTextSize("TRAFFIC DENSITY: ", font, hud_font_scale2, hud_thick1)
            cv2.putText(annotated, f"[{current_density}]", (hud_x + int(12 * res_scale) + td_w, l2_y), font, hud_font_scale2, density_color, hud_thick2, cv2.LINE_AA)

            # Line 3: Live In Frame
            l3_y = hud_y + int(80 * res_scale)
            live_txt = f"Live Frame: {result.live_total_vehicles} (Cars:{result.live_counts_by_type.get('car',0)} Bus:{result.live_counts_by_type.get('bus',0)} Trk:{result.live_counts_by_type.get('truck',0)} Moto:{result.live_counts_by_type.get('motorcycle',0)})"
            cv2.putText(annotated, live_txt, (hud_x + int(12 * res_scale), l3_y), font, hud_font_scale3, (241, 245, 249), hud_thick1, cv2.LINE_AA)

            # Line 4: Cumulative Unique Count (Recount Prevention)
            l4_y = hud_y + int(106 * res_scale)
            cum_txt = f"Unique Vehicles: {result.cumulative_total_unique_vehicles} | Frame: {result.frame_number} | {fps:.1f} FPS"
            cv2.putText(annotated, cum_txt, (hud_x + int(12 * res_scale), l4_y), font, hud_font_scale3, (148, 163, 184), hud_thick1, cv2.LINE_AA)

        return annotated

    def process_video(
        self,
        video_path: Union[str, Path],
        gps_synchronizer: Optional[GPSVideoSynchronizer] = None,
        output_video_path: Optional[Union[str, Path]] = None,
        output_json_path: Optional[Union[str, Path]] = None,
        interval_seconds: float = DEFAULT_INTERVAL_SECONDS,
        max_frames: Optional[int] = None,
        conf_threshold: Optional[float] = None,
        imgsz: Optional[int] = None,
        show_progress: bool = True,
    ) -> Dict[str, Any]:
        """Processes an entire video feed with tracking, interval aggregation, and GPS synchronization.

        Args:
            video_path: Path to input MP4 video.
            gps_synchronizer: Instance of GPSVideoSynchronizer for attaching coordinates.
            output_video_path: Path to save annotated output MP4 video.
            output_json_path: Path to save structured measurements JSON.
            interval_seconds: Time interval window for density measurements.
            max_frames: Optional limit on frames to process.
            conf_threshold: Optional confidence threshold.
            imgsz: Optional inference resolution override (default: 640).
            show_progress: Whether to display progress in stdout.

        Returns:
            Dictionary containing metadata, summary, interval measurements, and frame tracking logs.
        """
        self.reset_state()
        self.density_estimator.gps_sync = gps_synchronizer
        self.density_estimator.interval_seconds = interval_seconds
        inference_imgsz = imgsz if imgsz is not None else self.imgsz

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
                fourcc = cv2.VideoWriter_fourcc(*"XVID")
                writer = cv2.VideoWriter(str(out_p), fourcc, fps, (width, height))

        frame_idx = 0
        frame_results: List[FrameTrackingResult] = []
        interval_measurements: List[IntervalTrafficMeasurement] = []
        start_time = time.time()

        # Interval tracking buffers
        current_interval_idx = 0
        interval_start_t = 0.0
        interval_active_ids: Set[int] = set()

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

                # Track frame with persistent ByteTrack state & class-agnostic NMS
                res = self.track_frame(
                    frame=frame,
                    frame_number=frame_idx,
                    video_timestamp=video_timestamp,
                    conf_threshold=conf_threshold,
                    imgsz=inference_imgsz,
                )
                frame_results.append(res)

                # Accumulate unique active track IDs in current interval
                for d in res.detections:
                    interval_active_ids.add(d.track_id)

                # Check if current interval time window has elapsed
                if (video_timestamp - interval_start_t) >= interval_seconds:
                    # Classify each unique active vehicle in interval by its track consensus class
                    int_counts: Dict[str, int] = {k: 0 for k in self.target_classes.values()}
                    for t_id in interval_active_ids:
                        c_type = self.get_consensus_class(t_id)
                        if c_type in int_counts:
                            int_counts[c_type] += 1
                        else:
                            int_counts[c_type] = int_counts.get(c_type, 0) + 1

                    measurement = self.density_estimator.create_interval_measurement(
                        interval_index=current_interval_idx,
                        start_time=interval_start_t,
                        end_time=video_timestamp,
                        car_count=int_counts.get("car", 0),
                        bus_count=int_counts.get("bus", 0),
                        truck_count=int_counts.get("truck", 0),
                        motorcycle_count=int_counts.get("motorcycle", 0),
                        bicycle_count=int_counts.get("bicycle", 0),
                        active_track_ids=sorted(list(interval_active_ids)),
                        unique_interval_track_ids=sorted(list(interval_active_ids)),
                    )
                    interval_measurements.append(measurement)

                    # Reset interval buffers
                    current_interval_idx += 1
                    interval_start_t = video_timestamp
                    interval_active_ids = set()

                # Annotate and write output frame
                if writer is not None:
                    calc_fps = 1.0 / max(1e-4, (time.time() - t_f_start))
                    # Use current or last known density for HUD
                    last_density = interval_measurements[-1].traffic_density if interval_measurements else res.traffic_density
                    annotated_frame = self.annotate_frame(
                        frame,
                        res,
                        density_label=last_density,
                        show_hud=True,
                        show_trails=True,
                        fps=calc_fps,
                    )
                    writer.write(annotated_frame)

                frame_idx += 1

                if show_progress and frame_idx % 30 == 0:
                    pct = (frame_idx / total_video_frames * 100) if total_video_frames > 0 else 0
                    print(f"[*] Tracking frame {frame_idx}/{total_video_frames or '?'} ({pct:.1f}%) | Unique Vehicles: {res.cumulative_total_unique_vehicles} | Live: {res.live_total_vehicles}", flush=True)

            # Flush final partial interval if frames remain
            if interval_active_ids or (frame_idx > 0 and len(interval_measurements) == 0):
                final_t = frame_idx / float(fps)
                int_counts = {k: 0 for k in self.target_classes.values()}
                for t_id in interval_active_ids:
                    c_type = self.get_consensus_class(t_id)
                    if c_type in int_counts:
                        int_counts[c_type] += 1
                    else:
                        int_counts[c_type] = int_counts.get(c_type, 0) + 1

                measurement = self.density_estimator.create_interval_measurement(
                    interval_index=current_interval_idx,
                    start_time=interval_start_t,
                    end_time=final_t,
                    car_count=int_counts.get("car", 0),
                    bus_count=int_counts.get("bus", 0),
                    truck_count=int_counts.get("truck", 0),
                    motorcycle_count=int_counts.get("motorcycle", 0),
                    bicycle_count=int_counts.get("bicycle", 0),
                    active_track_ids=sorted(list(interval_active_ids)),
                    unique_interval_track_ids=sorted(list(interval_active_ids)),
                )
                interval_measurements.append(measurement)

        finally:
            cap.release()
            if writer is not None:
                writer.release()

        elapsed = time.time() - start_time
        avg_fps = frame_idx / max(1e-4, elapsed)

        summary_payload = {
            "metadata": {
                "source_video": str(video_file),
                "model_weights": str(self.model_path),
                "tracker_type": self.tracker_type,
                "confidence_threshold": self.conf_threshold,
                "interval_seconds": interval_seconds,
                "video_resolution": f"{width}x{height}",
                "video_fps": float(fps),
                "total_frames_processed": frame_idx,
                "processing_time_seconds": round(elapsed, 2),
                "average_inference_fps": round(avg_fps, 2),
                "is_simulated": True,
                "disclaimer": "prototype traffic-density estimation — not scientifically calibrated",
            },
            "aggregate_statistics": {
                "total_unique_vehicles_counted": len(self.all_seen_track_ids),
                "unique_counts_by_type": {k: len(v) for k, v in self.seen_track_ids_by_type.items()},
                "total_interval_measurements": len(interval_measurements),
                "density_distribution": {
                    "LOW": sum(1 for m in interval_measurements if m.traffic_density == "LOW"),
                    "MEDIUM": sum(1 for m in interval_measurements if m.traffic_density == "MEDIUM"),
                    "HIGH": sum(1 for m in interval_measurements if m.traffic_density == "HIGH"),
                },
            },
            "interval_measurements": [m.to_dict() for m in interval_measurements],
            "frame_tracking_samples": [res.to_dict() for res in frame_results[::max(1, len(frame_results)//50)]],
        }

        if output_json_path:
            out_j = Path(output_json_path)
            out_j.parent.mkdir(parents=True, exist_ok=True)
            with open(out_j, "w", encoding="utf-8") as f:
                json.dump(summary_payload, f, indent=2)

        return summary_payload
