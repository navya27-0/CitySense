"""Road Defect Detection Package for BusSense-AI.

Covers:
- Potholes (POTHOLE)
- Damaged roads / Cracks / Rutting (DAMAGED_ROAD)
- Missing road dividers / Broken medians (MISSING_DIVIDER)
- Missing / faded zebra crossings (MISSING_ZEBRA_CROSSING)
- Damaged / missing traffic signboards (DAMAGED_SIGNBOARD)
- Road waterlogging / Flooding (WATERLOGGING)
"""

from ai.road_defect_detection.detector import (
    RoadDefectDetector,
    RoadDefectType,
    RoadDefectSeverity,
    RoadDefectDetection,
    RoadDefectEvent,
    DEFECT_COLORS,
    SEVERITY_COLORS,
)

__all__ = [
    "RoadDefectDetector",
    "RoadDefectType",
    "RoadDefectSeverity",
    "RoadDefectDetection",
    "RoadDefectEvent",
    "DEFECT_COLORS",
    "SEVERITY_COLORS",
]
