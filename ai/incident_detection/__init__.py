"""Incident Detection Engine Module for BusSense-AI.

Exports:
- IncidentDetector: End-to-end incident engine.
- IncidentConfig: Centralized threshold configuration.
- IncidentRecord: Standardized incident event dataclass.
- IncidentType, IncidentSeverity, IncidentStatus: Enumerations.
- BaseIncidentRule, IncidentCandidate: Rule plugin interface.
- RashDrivingRule: Heuristic rule for rash driving / erratic weaving.
- HitAndRunRule: Heuristic rule for suspected hit-and-run scenarios.
"""

from ai.incident_detection.config import (
    IncidentConfig,
    IncidentRecord,
    IncidentType,
    IncidentSeverity,
    IncidentStatus,
    DISCLAIMER_TEXT,
)
from ai.incident_detection.rules.base import BaseIncidentRule, IncidentCandidate
from ai.incident_detection.rules.rash_driving import RashDrivingRule
from ai.incident_detection.rules.hit_and_run import HitAndRunRule
from ai.incident_detection.detector import IncidentDetector

__all__ = [
    "IncidentDetector",
    "IncidentConfig",
    "IncidentRecord",
    "IncidentType",
    "IncidentSeverity",
    "IncidentStatus",
    "DISCLAIMER_TEXT",
    "BaseIncidentRule",
    "IncidentCandidate",
    "RashDrivingRule",
    "HitAndRunRule",
]
