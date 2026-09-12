"""Suspected Hit and Run heuristic rule implementation.

================================================================================
DISCLAIMER:
All incident classifications are PROTOTYPE HEURISTIC ESTIMATIONS — rule-based
detections, NOT forensic or legal determinations.
================================================================================
"""

import math
from typing import Dict, Any, List, Optional, Tuple
import numpy as np

from ai.incident_detection.config import (
    IncidentConfig,
    IncidentType,
    IncidentSeverity,
)
from ai.incident_detection.rules.base import BaseIncidentRule, IncidentCandidate


def _compute_iou(boxA: List[int], boxB: List[int]) -> float:
    """Computes Intersection-over-Union (IoU) between two bounding boxes [x1, y1, x2, y2]."""
    xA = max(boxA[0], boxB[0])
    yA = max(boxA[1], boxB[1])
    xB = min(boxA[2], boxB[2])
    yB = min(boxA[3], boxB[3])

    inter_w = max(0, xB - xA)
    inter_h = max(0, yB - yA)
    inter_area = inter_w * inter_h

    boxA_area = max(0, boxA[2] - boxA[0]) * max(0, boxA[3] - boxA[1])
    boxB_area = max(0, boxB[2] - boxB[0]) * max(0, boxB[3] - boxB[1])

    union_area = boxA_area + boxB_area - inter_area
    if union_area <= 0:
        return 0.0
    return float(inter_area / union_area)


class HitAndRunRule(BaseIncidentRule):
    """Detects suspected hit-and-run scenarios:
    1. Close proximity / collision encounter with another vehicle or sudden impact deceleration.
    2. Followed by rapid post-encounter speed surge / acceleration.
    3. Trajectory directed rapidly toward the boundary or sudden departure from the monitored scene.
    """

    def __init__(self):
        super().__init__(
            name="HitAndRunHeuristicRule",
            incident_type=IncidentType.SUSPECTED_HIT_AND_RUN,
        )

    def evaluate(
        self,
        track_id: int,
        track_state: Dict[str, Any],
        all_tracks_state: Dict[int, Dict[str, Any]],
        frame_meta: Dict[str, Any],
        config: IncidentConfig,
    ) -> Optional[IncidentCandidate]:
        """Evaluates vehicle track for suspected hit-and-run heuristic patterns."""
        centroids: List[Tuple[int, int]] = track_state.get("centroids", [])
        timestamps: List[float] = track_state.get("timestamps", [])
        boxes: List[List[int]] = track_state.get("boxes", [])

        if len(centroids) < config.min_track_history_frames or len(boxes) < config.min_track_history_frames:
            return None

        # Look back up to observation window
        window = min(len(centroids), config.hit_and_run_observation_window_frames)
        pts = np.array(centroids[-window:], dtype=np.float64)
        ts = np.array(timestamps[-window:], dtype=np.float64)
        recent_boxes = boxes[-window:]

        # Resolution scale factor (normalized to 1280x720 baseline)
        w = frame_meta.get("width", 1280)
        h = frame_meta.get("height", 720)
        res_scale = max(0.2, min(w, h * 16 // 9) / 1280.0)
        pts_norm = pts / res_scale

        fps = frame_meta.get("fps", config.frame_rate_fps) or config.frame_rate_fps
        d_pos = np.diff(pts_norm, axis=0)
        d_dist = np.linalg.norm(d_pos, axis=1)
        d_time = np.diff(ts)
        dt_safe = np.where(d_time > 0.001, d_time, 1.0 / fps)
        speeds = d_dist / dt_safe if len(d_dist) > 0 else np.array([])

        if len(speeds) < 4:
            return None

        # 1. Search for Timestamp-Synchronized Proximity Encounter with another vehicle
        proximity_found = False
        min_encounter_dist = float("inf")
        max_encounter_iou = 0.0
        encounter_idx = -1
        encounter_partner_id = None

        current_cx, current_cy = centroids[-1]

        # Scan historical points in window (excluding the very latest frame to allow post-encounter observation)
        for t_step in range(0, window - 3):
            t_curr = ts[t_step]
            bA = recent_boxes[t_step]
            cA_norm = pts_norm[t_step]
            
            for other_id, other_state in all_tracks_state.items():
                if other_id == track_id:
                    continue
                other_boxes = other_state.get("boxes", [])
                other_centroids = other_state.get("centroids", [])
                other_timestamps = other_state.get("timestamps", [])
                
                # Find matching historical index for other vehicle at the EXACT same timestamp
                for o_idx, o_time in enumerate(other_timestamps):
                    if abs(o_time - t_curr) <= (0.75 / fps):  # Frame-accurate timestamp match
                        other_box = other_boxes[o_idx]
                        other_c_norm = np.array(other_centroids[o_idx]) / res_scale
                        
                        dist = float(np.linalg.norm(cA_norm - other_c_norm))
                        iou = _compute_iou(bA, other_box)
                        
                        if dist <= config.hit_and_run_proximity_distance_px or iou >= config.hit_and_run_min_iou_overlap:
                            proximity_found = True
                            if dist < min_encounter_dist:
                                min_encounter_dist = dist
                                max_encounter_iou = max(max_encounter_iou, iou)
                                encounter_idx = t_step
                                encounter_partner_id = other_id

        # Must have a confirmed physical collision encounter with another vehicle
        if not proximity_found or encounter_idx < 0:
            return None

        # Must be within collision threshold
        if min_encounter_dist > config.hit_and_run_proximity_distance_px and max_encounter_iou < config.hit_and_run_min_iou_overlap:
            return None

        # 2. Check Post-Encounter Flight & Speed Surge
        split_point = max(1, encounter_idx)
        pre_encounter_speeds = speeds[:split_point]
        post_encounter_speeds = speeds[split_point:]

        if len(post_encounter_speeds) < 2:
            return None

        pre_speed_avg = float(np.mean(pre_encounter_speeds)) if len(pre_encounter_speeds) > 0 else 1.0
        post_speed_max = float(np.max(post_encounter_speeds)) if len(post_encounter_speeds) > 0 else 0.0
        post_speed_avg = float(np.mean(post_encounter_speeds)) if len(post_encounter_speeds) > 0 else 0.0

        surge_ratio = post_speed_max / max(10.0, pre_speed_avg)
        
        # Must show high absolute departure speed and rapid acceleration surge away from collision
        if post_speed_max < config.hit_and_run_min_departure_speed_px_s or surge_ratio < config.hit_and_run_speed_surge_ratio:
            return None

        # 3. Check Directional Departure Towards Scene Boundary
        margin = config.hit_and_run_boundary_margin_px * (res_scale if res_scale > 0 else 1.0)
        
        is_near_boundary = (
            current_cx <= margin or current_cx >= w - margin or
            current_cy <= margin or current_cy >= h - margin
        )

        # 4. Calculate Confidence Score
        conf_scores: List[float] = []
        reasons: List[str] = []

        partner_str = f"with vehicle #{encounter_partner_id}" if encounter_partner_id else ""
        reasons.append(f"Physical collision encounter (dist: {min_encounter_dist:.1f} px, IoU: {max_encounter_iou:.2f}) {partner_str}".strip())
        conf_scores.append(0.78 + 0.14 * min(1.0, max_encounter_iou / 0.30))

        reasons.append(
            f"Rapid flight / departure surge ({surge_ratio:.2f}x pre-collision velocity, "
            f"post-speed: {post_speed_max:.1f} norm-px/s)"
        )
        conf_scores.append(0.75 + 0.15 * min(1.0, (surge_ratio - 1.0) / 2.0))

        if is_near_boundary:
            reasons.append("Fleeing trajectory directed rapidly out of scene boundary")
            conf_scores.append(0.75)

        event_conf = min(0.98, float(np.mean(conf_scores) + 0.04 * (len(conf_scores) - 1)))
        
        if event_conf < config.hit_and_run_min_event_confidence:
            return None

        # Severity Assessment
        if event_conf >= 0.85 or max_encounter_iou > 0.20:
            severity = IncidentSeverity.CRITICAL
        elif event_conf >= 0.75 or surge_ratio >= 2.0:
            severity = IncidentSeverity.HIGH
        else:
            severity = IncidentSeverity.MEDIUM

        diagnostic_details = {
            "proximity_distance_px": round(min_encounter_dist, 1) if proximity_found else None,
            "max_iou_overlap": round(max_encounter_iou, 3),
            "encounter_partner_track_id": encounter_partner_id,
            "pre_encounter_speed_px_s": round(pre_speed_avg, 2),
            "post_encounter_max_speed_px_s": round(post_speed_max, 2),
            "speed_surge_ratio": round(surge_ratio, 2),
            "is_near_boundary": is_near_boundary,
            "triggered_indicators": reasons,
        }

        return IncidentCandidate(
            incident_type=IncidentType.SUSPECTED_HIT_AND_RUN,
            event_confidence=round(event_conf, 3),
            severity=severity,
            reasoning="; ".join(reasons),
            details=diagnostic_details,
        )
