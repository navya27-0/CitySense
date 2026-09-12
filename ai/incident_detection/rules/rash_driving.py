"""Rash Driving heuristic rule implementation.

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


class RashDrivingRule(BaseIncidentRule):
    """Detects rash driving patterns: erratic lateral weaving, sudden acceleration spikes,
    excessive speed relative to the camera frame, and abrupt swerving angles.
    """

    def __init__(self):
        super().__init__(
            name="RashDrivingHeuristicRule",
            incident_type=IncidentType.RASH_DRIVING,
        )

    def evaluate(
        self,
        track_id: int,
        track_state: Dict[str, Any],
        all_tracks_state: Dict[int, Dict[str, Any]],
        frame_meta: Dict[str, Any],
        config: IncidentConfig,
    ) -> Optional[IncidentCandidate]:
        """Evaluates vehicle track kinematics for rash driving behavior."""
        centroids: List[Tuple[int, int]] = track_state.get("centroids", [])
        timestamps: List[float] = track_state.get("timestamps", [])
        
        if len(centroids) < config.min_track_history_frames or len(timestamps) < config.min_track_history_frames:
            return None

        # Extract recent trajectory window (up to last 20 points)
        raw_pts = np.array(centroids[-20:], dtype=np.float64)
        raw_ts = np.array(timestamps[-20:], dtype=np.float64)

        # Resolution scale factor (normalized to 1280x720 baseline)
        w = frame_meta.get("width", 1280)
        h = frame_meta.get("height", 720)
        res_scale = max(0.2, min(w, h * 16 // 9) / 1280.0)
        pts_norm = raw_pts / res_scale

        # 1. 5-point moving average smoothing to eliminate tracker bounding box jitter
        if len(pts_norm) >= 7:
            k = np.ones(5) / 5.0
            sx = np.convolve(pts_norm[:, 0], k, mode="valid")
            sy = np.convolve(pts_norm[:, 1], k, mode="valid")
            s_pts = np.column_stack([sx, sy])
            s_ts = raw_ts[2:-2]
        elif len(pts_norm) >= 5:
            k = np.ones(3) / 3.0
            sx = np.convolve(pts_norm[:, 0], k, mode="valid")
            sy = np.convolve(pts_norm[:, 1], k, mode="valid")
            s_pts = np.column_stack([sx, sy])
            s_ts = raw_ts[1:-1]
        else:
            s_pts = pts_norm
            s_ts = raw_ts

        # 2. Compute instantaneous velocities (normalized pixels per second) on smoothed trajectory
        d_pos = np.diff(s_pts, axis=0)  # (n-1, 2)
        d_dist = np.linalg.norm(d_pos, axis=1)  # (n-1,)
        d_time = np.diff(s_ts)  # (n-1,)
        
        fps = frame_meta.get("fps", config.frame_rate_fps) or config.frame_rate_fps
        dt_safe = np.where(d_time > 0.001, d_time, 1.0 / fps)
        
        speeds = d_dist / dt_safe  # normalized px/s
        if len(speeds) < 4:
            return None

        max_speed = float(np.max(speeds))
        avg_speed = float(np.mean(speeds))
        p90_speed = float(np.percentile(speeds, 90))

        # 3. Compute Accelerations on Smoothed Velocity
        if len(speeds) >= 3:
            accels = np.abs(np.diff(speeds) / dt_safe[1:])
            max_accel = float(np.max(accels))
        else:
            max_accel = 0.0

        # 4. Compute Lateral Trajectory Deviation & Zero-Crossings (Slalom Weaving)
        start_pt = s_pts[0]
        end_pt = s_pts[-1]
        baseline_vec = end_pt - start_pt
        total_disp = float(np.linalg.norm(baseline_vec))

        lat_std = 0.0
        zero_crossings = 0
        max_lat_speed = 0.0

        if total_disp > 30.0:  # Meaningful total travel displacement
            unit_long = baseline_vec / total_disp
            unit_lat = np.array([-unit_long[1], unit_long[0]])
            lat_offsets = np.dot(s_pts - start_pt, unit_lat)
            lat_std = float(np.std(lat_offsets))
            
            # Detrend lateral offsets to find real slalom oscillations / zero-crossings
            detrended = lat_offsets - np.linspace(lat_offsets[0], lat_offsets[-1], len(lat_offsets))
            zero_crossings = int(np.sum(np.diff(np.sign(detrended) != 0)))
            
            # Lateral velocity
            lat_diffs = np.abs(np.diff(lat_offsets))
            max_lat_speed = float(np.max(lat_diffs / dt_safe))

        # 5. Compute Angular Swerve on Vectors with Significant Motion (> 10 norm-px)
        sig_motion_mask = d_dist > 10.0
        max_heading_change_deg = 0.0
        if np.sum(sig_motion_mask) >= 2:
            sig_pos = d_pos[sig_motion_mask]
            headings = np.arctan2(sig_pos[:, 1], sig_pos[:, 0])
            d_hdg = np.abs(np.diff(np.unwrap(headings)))
            if len(d_hdg) > 0:
                max_heading_change_deg = float(np.max(np.degrees(d_hdg)))

        # 6. Evaluate Strict Rule Trigger Conditions for Genuine Reckless Driving
        reasons: List[str] = []
        conf_scores: List[float] = []

        # Trigger Pattern 1: Aggressive Slalom Weaving (multiple oscillations across path at high speed)
        is_slalom = (
            zero_crossings >= config.rash_min_zero_crossings
            and lat_std >= config.rash_min_lateral_std_px
            and avg_speed >= 260.0
            and max_lat_speed >= config.rash_min_lateral_speed_px_s
            and total_disp >= 100.0
        )
        if is_slalom:
            conf_scores.append(0.82 + 0.14 * min(1.0, lat_std / 30.0))
            reasons.append(
                f"Aggressive slalom lane weaving ({zero_crossings} reversals, "
                f"lat_std: {lat_std:.1f} px, lat_speed: {max_lat_speed:.1f} px/s)"
            )

        # Trigger Pattern 2: Aggressive High-Speed Cutting / Sharp Swerve
        is_aggressive_cut = (
            max_heading_change_deg >= config.rash_max_heading_change_deg
            and avg_speed >= config.rash_avg_speed_threshold_px_s
            and max_lat_speed >= 180.0
            and total_disp >= 80.0
        )
        if is_aggressive_cut:
            conf_scores.append(0.80 + 0.16 * min(1.0, max_heading_change_deg / 60.0))
            reasons.append(
                f"High-speed aggressive swerve/cut ({max_heading_change_deg:.1f}° "
                f"at {avg_speed:.1f} norm-px/s)"
            )

        # Trigger Pattern 3: Extreme Outlier Speed with Violent Lateral Maneuver
        is_extreme_speed = (
            avg_speed >= config.rash_avg_speed_threshold_px_s
            and p90_speed >= config.rash_speed_threshold_px_s
            and max_lat_speed >= 250.0
            and total_disp >= 150.0
        )
        if is_extreme_speed:
            conf_scores.append(0.84 + 0.12 * min(1.0, avg_speed / 600.0))
            reasons.append(
                f"Extreme reckless speed with lateral surge ({avg_speed:.1f} norm-px/s, "
                f"p90: {p90_speed:.1f} px/s, lat_spd: {max_lat_speed:.1f} px/s)"
            )

        # Supporting Indicator: Velocity acceleration spike / jerk during reckless maneuvers
        if max_accel >= config.rash_accel_threshold_px_s2 and conf_scores:
            conf_scores.append(0.70 + 0.20 * min(1.0, max_accel / 800.0))
            reasons.append(f"Sudden acceleration spike ({max_accel:.1f} norm-px/s²)")

        # If no primary reckless driving pattern was met, suppress false alarm
        if not conf_scores:
            return None

        # Composite Event Confidence
        event_conf = min(0.98, float(np.mean(conf_scores) + 0.04 * (len(conf_scores) - 1)))
        
        if event_conf < config.rash_min_event_confidence:
            return None

        # Severity Classification
        if event_conf >= 0.88 or avg_speed >= 450.0 or is_slalom:
            severity = IncidentSeverity.HIGH
        elif event_conf >= 0.75 or len(reasons) >= 2:
            severity = IncidentSeverity.MEDIUM
        else:
            severity = IncidentSeverity.LOW

        diagnostic_details = {
            "max_speed_px_s": round(max_speed, 2),
            "avg_speed_px_s": round(avg_speed, 2),
            "p90_speed_px_s": round(p90_speed, 2),
            "max_accel_px_s2": round(max_accel, 2),
            "lateral_std_px": round(lat_std, 2),
            "zero_crossings": zero_crossings,
            "max_lateral_speed_px_s": round(max_lat_speed, 2),
            "max_heading_change_deg": round(max_heading_change_deg, 1),
            "total_displacement_px": round(total_disp, 1),
            "triggered_indicators": reasons,
        }

        return IncidentCandidate(
            incident_type=IncidentType.RASH_DRIVING,
            event_confidence=round(event_conf, 3),
            severity=severity,
            reasoning="; ".join(reasons),
            details=diagnostic_details,
        )
