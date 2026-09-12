"""Prototype Traffic Density Estimation Module for BusSense-AI.

================================================================================
DISCLAIMER:
All traffic density calculations, classifications (LOW / MEDIUM / HIGH), and
derived vehicle statistics in this module are PROTOTYPE TRAFFIC-DENSITY ESTIMATIONS
developed for hackathon demonstration purposes. They are NOT scientifically calibrated
or certified for production municipal traffic engineering without field calibration.
================================================================================

Integrates with GPSVideoSynchronizer (ai/pipeline/gps_sync.py) as the single source
of truth for attaching geographic coordinates (latitude, longitude, speed, heading)
to each aggregated time interval.
"""

from enum import Enum
from dataclasses import dataclass, field, asdict
from typing import Dict, Any, List, Optional, Union
from pathlib import Path
import logging

from ai.pipeline.gps_sync import GPSVideoSynchronizer

logger = logging.getLogger(__name__)

# ==============================================================================
# CONFIGURABLE TRAFFIC DENSITY THRESHOLD CONSTANTS
# ==============================================================================
# Vehicles observed within an interval or active in a scene:
#   0 - 2 vehicles  -> LOW
#   3 - 5 vehicles  -> MEDIUM
#   6+ vehicles     -> HIGH
DEFAULT_LOW_DENSITY_MAX: int = 2
DEFAULT_MEDIUM_DENSITY_MAX: int = 5
DEFAULT_HIGH_DENSITY_MIN: int = 6
DEFAULT_INTERVAL_SECONDS: float = 1.0


class TrafficDensity(str, Enum):
    """Enumeration of prototype traffic density levels."""
    LOW = "LOW"
    MEDIUM = "MEDIUM"
    HIGH = "HIGH"


@dataclass
class IntervalTrafficMeasurement:
    """Represents an aggregated traffic density measurement for a discrete time window."""
    interval_index: int
    video_timestamp_start: float
    video_timestamp_end: float
    timestamp: str  # ISO-8601 UTC timestamp from GPS
    latitude: float
    longitude: float
    speed_kmh: float
    heading_deg: float
    car_count: int
    bus_count: int
    truck_count: int
    motorcycle_count: int
    bicycle_count: int
    total_vehicle_count: int
    traffic_density: str
    active_track_ids: List[int] = field(default_factory=list)
    unique_interval_track_ids: List[int] = field(default_factory=list)
    is_simulated: bool = True
    disclaimer: str = "prototype traffic-density estimation — not scientifically calibrated"

    def to_dict(self) -> Dict[str, Any]:
        """Converts dataclass to dictionary."""
        return asdict(self)


class TrafficDensityEstimator:
    """Estimates and classifies traffic density over configurable time windows.
    
    Uses GPSVideoSynchronizer as the single source of truth for attaching spatial
    coordinates to time-interval traffic measurements.
    """

    def __init__(
        self,
        gps_synchronizer: Optional[GPSVideoSynchronizer] = None,
        low_max: int = DEFAULT_LOW_DENSITY_MAX,
        medium_max: int = DEFAULT_MEDIUM_DENSITY_MAX,
        interval_seconds: float = DEFAULT_INTERVAL_SECONDS,
    ):
        """Initializes the TrafficDensityEstimator.

        Args:
            gps_synchronizer: Instance of GPSVideoSynchronizer (or None for mock zero coords).
            low_max: Maximum count inclusive for LOW density.
            medium_max: Maximum count inclusive for MEDIUM density (> medium_max is HIGH).
            interval_seconds: Duration in seconds for each aggregated measurement interval.
        """
        if low_max >= medium_max:
            raise ValueError(f"low_max ({low_max}) must be strictly less than medium_max ({medium_max})")

        self.gps_sync = gps_synchronizer
        self.low_max = low_max
        self.medium_max = medium_max
        self.interval_seconds = max(0.1, float(interval_seconds))

    def classify_density(self, vehicle_count: int) -> TrafficDensity:
        """Classifies vehicle count into LOW, MEDIUM, or HIGH density using configurable thresholds.

        Args:
            vehicle_count: Number of vehicles detected/counted in the interval.

        Returns:
            TrafficDensity (LOW / MEDIUM / HIGH).
        """
        if vehicle_count <= self.low_max:
            return TrafficDensity.LOW
        elif vehicle_count <= self.medium_max:
            return TrafficDensity.MEDIUM
        else:
            return TrafficDensity.HIGH

    def create_interval_measurement(
        self,
        interval_index: int,
        start_time: float,
        end_time: float,
        car_count: int,
        bus_count: int,
        truck_count: int,
        motorcycle_count: int,
        bicycle_count: int = 0,
        active_track_ids: Optional[List[int]] = None,
        unique_interval_track_ids: Optional[List[int]] = None,
    ) -> IntervalTrafficMeasurement:
        """Constructs an interval measurement with synchronized GPS coordinates and density rating.

        Args:
            interval_index: Sequence index of the measurement window.
            start_time: Start timestamp of interval in video seconds.
            end_time: End timestamp of interval in video seconds.
            car_count: Number of cars counted.
            bus_count: Number of buses counted.
            truck_count: Number of trucks counted.
            motorcycle_count: Number of motorcycles counted.
            bicycle_count: Number of bicycles counted.
            active_track_ids: Currently tracked vehicle IDs.
            unique_interval_track_ids: Unique vehicle IDs observed in this interval.

        Returns:
            IntervalTrafficMeasurement object with GPS position attached.
        """
        total_vehicles = car_count + bus_count + truck_count + motorcycle_count + bicycle_count
        density = self.classify_density(total_vehicles)

        mid_timestamp = (start_time + end_time) / 2.0

        # Retrieve geographic position via GPSVideoSynchronizer (Single Source of Truth)
        if self.gps_sync is not None:
            pos = self.gps_sync.get_position(video_timestamp=mid_timestamp, interpolate=True)
            iso_timestamp = pos.get("gps_timestamp") or pos.get("interpolated_timestamp") or ""
            latitude = pos.get("latitude", 0.0)
            longitude = pos.get("longitude", 0.0)
            speed_kmh = pos.get("speed", 0.0)
            heading_deg = pos.get("heading", 0.0)
        else:
            # Standalone fallback when GPS log is omitted
            iso_timestamp = "2026-09-09T00:00:00Z"
            latitude = 17.3850
            longitude = 78.4867
            speed_kmh = 0.0
            heading_deg = 0.0

        return IntervalTrafficMeasurement(
            interval_index=interval_index,
            video_timestamp_start=round(start_time, 3),
            video_timestamp_end=round(end_time, 3),
            timestamp=iso_timestamp,
            latitude=latitude,
            longitude=longitude,
            speed_kmh=speed_kmh,
            heading_deg=heading_deg,
            car_count=car_count,
            bus_count=bus_count,
            truck_count=truck_count,
            motorcycle_count=motorcycle_count,
            bicycle_count=bicycle_count,
            total_vehicle_count=total_vehicles,
            traffic_density=density.value,
            active_track_ids=active_track_ids or [],
            unique_interval_track_ids=unique_interval_track_ids or [],
            is_simulated=True,
            disclaimer="prototype traffic-density estimation — not scientifically calibrated",
        )
