"""Video-GPS Synchronization Module for BusSense-AI Edge AI Pipeline.

================================================================================
SYNCHRONIZATION SPECIFICATION & ARCHITECTURAL ASSUMPTIONS:
================================================================================
1. SINGLE SOURCE OF TRUTH:
   This module (`GPSVideoSynchronizer`) is the ONLY GPS-timestamp synchronization
   implementation in this project. Prompts 5, 6, 7, 8, and 9 MUST import and use
   `GPSVideoSynchronizer` from this file (`ai.pipeline.gps_sync`). They must NOT
   implement ad hoc timestamp-matching logic.

2. INPUT DATA CONTRACT:
   - Video Stream: Frame timestamp in seconds from video origin (e.g., t = 0.0, 1.5, 3.5s)
     or absolute datetime.
   - GPS CSV: Standard CSV with columns `timestamp,latitude,longitude,speed,heading`.

3. TEMPORAL ALIGNMENT ASSUMPTIONS:
   - By default, t = 0.0s in the video corresponds to the earliest valid timestamp
     recorded in the GPS CSV, unless an explicit `video_start_time` (ISO or datetime)
     is passed during initialization or query.
   - If the video duration exceeds the GPS log (video continues after GPS ends), the
     synchronizer clamps to the final known GPS coordinate with
     `interpolation_status="out_of_range_clamped"`.
   - If video frames precede the first GPS timestamp, the synchronizer clamps to the
     first known GPS coordinate with `interpolation_status="out_of_range_clamped"`.
   - Missing or malformed rows (NaN, bad strings, corrupted lines) are sanitized during loading.
   - Duplicate timestamps are deduplicated, keeping the earliest valid observation.
   - Unsorted GPS rows are automatically sorted chronologically.

4. INTERPOLATION LOGIC:
   - Exact Match: If a GPS sample matches the target timestamp within tolerance (< 1ms),
     the exact observation is returned (`interpolation_status="exact_match"`).
   - Linear Interpolation: For frame timestamps bounded by t1 and t2 (t1 < t < t2),
     coordinates and speed are linearly interpolated. Heading is interpolated along the
     shortest angular arc across 0°/360° (`interpolation_status="interpolated"`).
   - Nearest Neighbor Fallback: Used when `interpolate=False` or when the time gap
     exceeds `max_interpolation_gap_seconds` (`interpolation_status="nearest_neighbor"`).

NOTE: All generated positions and AI events are SIMULATED TELEMETRY for the
SIH26124 prototype demonstration.
================================================================================
"""

import math
import logging
from datetime import datetime, timezone, timedelta
from pathlib import Path
from typing import Dict, Any, Optional, Union, Tuple, List
import pandas as pd
import numpy as np

logger = logging.getLogger(__name__)


def interpolate_heading(heading1: float, heading2: float, alpha: float) -> float:
    """Interpolate between two compass headings (0-360 degrees) along shortest angular path."""
    diff = (heading2 - heading1 + 180) % 360 - 180
    interp = (heading1 + diff * alpha) % 360
    return round(float(interp), 1)


class GPSVideoSynchronizer:
    """Synchronizes video frame timestamps with GPS telemetry logs."""

    def __init__(
        self,
        gps_source: Union[str, Path, pd.DataFrame, List[Dict[str, Any]]],
        video_start_time: Optional[Union[str, datetime]] = None,
        bus_id: str = "BUS_101",
        camera_id: str = "CAM_FRONT_01",
        max_interpolation_gap_seconds: float = 15.0,
    ):
        """Initialize GPS-Video Synchronizer.

        Args:
            gps_source: File path to GPS CSV, pandas DataFrame, or list of dicts.
            video_start_time: Optional absolute start timestamp of video.
            bus_id: Bus fleet identifier.
            camera_id: Bus camera sensor identifier.
            max_interpolation_gap_seconds: Maximum time gap (in seconds) allowed for interpolation.
        """
        self.bus_id = bus_id
        self.camera_id = camera_id
        self.max_interpolation_gap_seconds = max_interpolation_gap_seconds
        self.gps_df = self._load_and_clean_gps(gps_source)

        if len(self.gps_df) == 0:
            raise ValueError("No valid GPS records found after data sanitization.")

        # Determine reference start time
        self.first_gps_time: datetime = self.gps_df["dt"].iloc[0]
        self.last_gps_time: datetime = self.gps_df["dt"].iloc[-1]

        if video_start_time is not None:
            if isinstance(video_start_time, str):
                self.video_start_time = datetime.fromisoformat(video_start_time.replace("Z", "+00:00"))
            else:
                self.video_start_time = video_start_time
            if self.video_start_time.tzinfo is None:
                self.video_start_time = self.video_start_time.replace(tzinfo=timezone.utc)
        else:
            self.video_start_time = self.first_gps_time

    def _load_and_clean_gps(self, gps_source: Union[str, Path, pd.DataFrame, List[Dict[str, Any]]]) -> pd.DataFrame:
        """Loads, cleans, deduplicates, and sorts GPS logs."""
        if hasattr(gps_source, "read"):
            df = pd.read_csv(gps_source)
        elif isinstance(gps_source, (str, Path)):
            path = Path(gps_source)
            if not path.exists():
                raise FileNotFoundError(f"GPS trajectory file not found: {path}")
            df = pd.read_csv(path)
        elif isinstance(gps_source, pd.DataFrame):
            df = gps_source.copy()
        elif isinstance(gps_source, list):
            df = pd.DataFrame(gps_source)
        else:
            raise TypeError(f"Unsupported gps_source type: {type(gps_source)}")

        # Normalize column names for user-uploaded CSV flexibility
        col_rename = {}
        for col in df.columns:
            c_low = str(col).strip().lower().replace(" ", "_")
            if c_low in ("lat", "latitude", "lat_deg", "y"):
                col_rename[col] = "latitude"
            elif c_low in ("lon", "lng", "longitude", "long", "lon_deg", "x"):
                col_rename[col] = "longitude"
            elif c_low in ("time", "timestamp", "datetime", "date_time", "utc_time", "iso_time", "ts"):
                col_rename[col] = "timestamp"
            elif c_low in ("spd", "speed", "speed_kmh", "speed_mps", "velocity"):
                col_rename[col] = "speed"
            elif c_low in ("hdg", "heading", "bearing", "course", "angle"):
                col_rename[col] = "heading"
        if col_rename:
            df = df.rename(columns=col_rename)

        # Ensure required columns exist
        required_cols = {"timestamp", "latitude", "longitude"}
        if not required_cols.issubset(df.columns):
            raise ValueError(f"GPS source missing required columns: {required_cols - set(df.columns)}")

        # Standardize optional columns
        if "speed" not in df.columns:
            df["speed"] = 0.0
        if "heading" not in df.columns:
            df["heading"] = 0.0

        # Parse timestamps to UTC datetimes
        def parse_dt(ts):
            if pd.isna(ts):
                return None
            try:
                if isinstance(ts, (int, float)):
                    # Unix epoch timestamp in seconds
                    return datetime.fromtimestamp(ts, tz=timezone.utc)
                if isinstance(ts, datetime):
                    return ts if ts.tzinfo else ts.replace(tzinfo=timezone.utc)
                dt = datetime.fromisoformat(str(ts).replace("Z", "+00:00"))
                return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)
            except Exception:
                return None

        df["dt"] = df["timestamp"].apply(parse_dt)

        # Drop invalid timestamp rows
        df = df.dropna(subset=["dt"])

        # Coerce numeric columns and drop invalid coordinate rows
        df["latitude"] = pd.to_numeric(df["latitude"], errors="coerce")
        df["longitude"] = pd.to_numeric(df["longitude"], errors="coerce")
        df["speed"] = pd.to_numeric(df["speed"], errors="coerce").fillna(0.0)
        df["heading"] = pd.to_numeric(df["heading"], errors="coerce").fillna(0.0)

        # Coordinate bounds check
        df = df.dropna(subset=["latitude", "longitude"])
        df = df[(df["latitude"].between(-90.0, 90.0)) & (df["longitude"].between(-180.0, 180.0))]

        # Sort chronologically by datetime
        df = df.sort_values(by="dt").reset_index(drop=True)

        # Deduplicate duplicate timestamps, keeping first observation
        df = df.drop_duplicates(subset=["dt"], keep="first").reset_index(drop=True)

        # Precompute epoch seconds for fast bisect / search
        df["epoch"] = df["dt"].apply(lambda t: t.timestamp())

        return df

    def get_position(
        self,
        video_timestamp: Union[float, int, datetime, str],
        interpolate: bool = True,
    ) -> Dict[str, Any]:
        """Calculates synchronized GPS coordinates for a given video frame timestamp.

        Args:
            video_timestamp: Relative seconds from video start (e.g., 3.5) OR absolute datetime/ISO string.
            interpolate: If True, performs linear interpolation between bounding GPS points.

        Returns:
            dict containing:
                - latitude (float)
                - longitude (float)
                - speed (float, km/h)
                - heading (float, degrees)
                - gps_timestamp (ISO string)
                - interpolation_status (str: exact_match, interpolated, nearest_neighbor, out_of_range_clamped)
                - bus_id (str)
                - camera_id (str)
                - is_simulated (bool: True)
        """
        # 1. Resolve target absolute datetime and epoch
        if isinstance(video_timestamp, (int, float)):
            target_dt = self.video_start_time + timedelta(seconds=float(video_timestamp))
            rel_seconds = float(video_timestamp)
        elif isinstance(video_timestamp, str):
            target_dt = datetime.fromisoformat(video_timestamp.replace("Z", "+00:00"))
            if target_dt.tzinfo is None:
                target_dt = target_dt.replace(tzinfo=timezone.utc)
            rel_seconds = (target_dt - self.video_start_time).total_seconds()
        elif isinstance(video_timestamp, datetime):
            target_dt = video_timestamp if video_timestamp.tzinfo else video_timestamp.replace(tzinfo=timezone.utc)
            rel_seconds = (target_dt - self.video_start_time).total_seconds()
        else:
            raise TypeError(f"Invalid video_timestamp type: {type(video_timestamp)}")

        target_epoch = target_dt.timestamp()
        epochs = self.gps_df["epoch"].values

        # 2. Check Boundary Out-of-Range Conditions (Clamping)
        if target_epoch <= epochs[0]:
            row = self.gps_df.iloc[0]
            status = "exact_match" if abs(target_epoch - epochs[0]) < 1e-3 else "out_of_range_clamped"
            return self._build_result(
                lat=row["latitude"],
                lon=row["longitude"],
                speed=row["speed"],
                heading=row["heading"],
                dt=row["dt"],
                video_timestamp=rel_seconds,
                status=status,
            )

        if target_epoch >= epochs[-1]:
            row = self.gps_df.iloc[-1]
            status = "exact_match" if abs(target_epoch - epochs[-1]) < 1e-3 else "out_of_range_clamped"
            return self._build_result(
                lat=row["latitude"],
                lon=row["longitude"],
                speed=row["speed"],
                heading=row["heading"],
                dt=row["dt"],
                video_timestamp=rel_seconds,
                status=status,
            )

        # 3. Locate bounding index in sorted GPS epochs
        idx = int(np.searchsorted(epochs, target_epoch))
        t1_epoch, t2_epoch = epochs[idx - 1], epochs[idx]

        # Check for exact matches
        if abs(target_epoch - t1_epoch) < 1e-3:
            row = self.gps_df.iloc[idx - 1]
            return self._build_result(row["latitude"], row["longitude"], row["speed"], row["heading"], row["dt"], rel_seconds, "exact_match")
        if abs(target_epoch - t2_epoch) < 1e-3:
            row = self.gps_df.iloc[idx]
            return self._build_result(row["latitude"], row["longitude"], row["speed"], row["heading"], row["dt"], rel_seconds, "exact_match")

        row1 = self.gps_df.iloc[idx - 1]
        row2 = self.gps_df.iloc[idx]
        gap = t2_epoch - t1_epoch

        # 4. Interpolate if enabled and within maximum time gap
        if interpolate and gap <= self.max_interpolation_gap_seconds:
            alpha = (target_epoch - t1_epoch) / gap
            interp_lat = float(row1["latitude"] + alpha * (row2["latitude"] - row1["latitude"]))
            interp_lon = float(row1["longitude"] + alpha * (row2["longitude"] - row1["longitude"]))
            interp_speed = float(row1["speed"] + alpha * (row2["speed"] - row1["speed"]))
            interp_heading = interpolate_heading(float(row1["heading"]), float(row2["heading"]), alpha)

            return self._build_result(
                lat=interp_lat,
                lon=interp_lon,
                speed=interp_speed,
                heading=interp_heading,
                dt=target_dt,
                video_timestamp=rel_seconds,
                status="interpolated",
            )

        # 5. Fallback: Nearest Neighbor
        nearest_row = row1 if (target_epoch - t1_epoch) < (t2_epoch - target_epoch) else row2
        return self._build_result(
            lat=nearest_row["latitude"],
            lon=nearest_row["longitude"],
            speed=nearest_row["speed"],
            heading=nearest_row["heading"],
            dt=nearest_row["dt"],
            video_timestamp=rel_seconds,
            status="nearest_neighbor",
        )

    def _build_result(
        self,
        lat: float,
        lon: float,
        speed: float,
        heading: float,
        dt: datetime,
        video_timestamp: float,
        status: str,
    ) -> Dict[str, Any]:
        """Constructs standardized position result."""
        return {
            "latitude": round(float(lat), 6),
            "longitude": round(float(lon), 6),
            "speed": round(float(speed), 2),
            "heading": round(float(heading), 1),
            "gps_timestamp": dt.isoformat(),
            "video_timestamp": round(float(video_timestamp), 3),
            "interpolation_status": status,
            "bus_id": self.bus_id,
            "camera_id": self.camera_id,
            "is_simulated": True,
        }

    def create_ai_event(
        self,
        event_type: str,
        confidence: float,
        video_timestamp: Union[float, int, datetime],
        severity: str = "medium",
        image_path: Optional[str] = None,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """Generates a fully synchronized AI detection event with inherited GPS position.

        Every AI detection from Prompts 5, 6, 7, 8, 9 must use this structure.
        """
        pos = self.get_position(video_timestamp)
        return {
            "event_type": event_type,
            "confidence": round(float(confidence), 3),
            "severity": severity,
            "video_timestamp": pos["video_timestamp"],
            "gps_timestamp": pos["gps_timestamp"],
            "latitude": pos["latitude"],
            "longitude": pos["longitude"],
            "speed": pos["speed"],
            "heading": pos["heading"],
            "bus_id": pos["bus_id"],
            "camera_id": pos["camera_id"],
            "interpolation_status": pos["interpolation_status"],
            "image_path": image_path,
            "metadata": metadata or {},
            "is_simulated": True,
            "simulation_notice": "SIMULATED TELEMETRY & AI EVENT FOR PROTOTYPE DEMONSTRATION",
        }
