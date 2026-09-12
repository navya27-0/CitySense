"""Automatic Number-Plate Recognition (ANPR) Module for BusSense-AI."""

from ai.anpr.validator import PlateValidator, ValidationResult
from ai.anpr.ocr_engine import OCREngine, PlateOCRResult
from ai.anpr.plate_detector import PlateDetector, PlateDetection
from ai.anpr.pipeline import ANPRPipeline, PlateIncidentRecord

__all__ = [
    "PlateValidator",
    "ValidationResult",
    "OCREngine",
    "PlateOCRResult",
    "PlateDetector",
    "PlateDetection",
    "ANPRPipeline",
    "PlateIncidentRecord",
]
