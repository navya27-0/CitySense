"""Vehicle detection and counting module using Ultralytics YOLO."""

from ai.vehicle_detection.detector import (
    VehicleDetector,
    SingleDetection,
    FrameDetectionResult,
    TARGET_VEHICLE_CLASSES,
)

__all__ = [
    "VehicleDetector",
    "SingleDetection",
    "FrameDetectionResult",
    "TARGET_VEHICLE_CLASSES",
]
