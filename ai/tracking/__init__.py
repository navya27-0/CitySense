"""Vehicle Tracking & Traffic Density Estimation Package for BusSense-AI.

NOTE: All density classifications are prototype traffic-density estimations
for the SIH26124 mobile urban intelligence demonstration.
"""

from ai.tracking.density_estimator import (
    TrafficDensityEstimator,
    IntervalTrafficMeasurement,
    TrafficDensity,
    DEFAULT_LOW_DENSITY_MAX,
    DEFAULT_MEDIUM_DENSITY_MAX,
    DEFAULT_HIGH_DENSITY_MIN,
    DEFAULT_INTERVAL_SECONDS,
)
from ai.tracking.tracker import (
    VehicleTracker,
    TrackedVehicleDetection,
    FrameTrackingResult,
    TARGET_VEHICLE_CLASSES,
    CLASS_COLORS,
    DENSITY_COLORS,
)

__all__ = [
    "TrafficDensityEstimator",
    "IntervalTrafficMeasurement",
    "TrafficDensity",
    "DEFAULT_LOW_DENSITY_MAX",
    "DEFAULT_MEDIUM_DENSITY_MAX",
    "DEFAULT_HIGH_DENSITY_MIN",
    "DEFAULT_INTERVAL_SECONDS",
    "VehicleTracker",
    "TrackedVehicleDetection",
    "FrameTrackingResult",
    "TARGET_VEHICLE_CLASSES",
    "CLASS_COLORS",
    "DENSITY_COLORS",
]
