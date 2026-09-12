"""Base class and data contracts for pluggable incident detection rules.

================================================================================
DISCLAIMER:
All rule evaluations are heuristic, rule-based algorithms for prototype detection.
================================================================================
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Dict, Any, List, Optional, Tuple
import numpy as np

from ai.incident_detection.config import (
    IncidentConfig,
    IncidentType,
    IncidentSeverity,
    DISCLAIMER_TEXT,
)


@dataclass
class IncidentCandidate:
    """Represents a rule-triggered incident candidate prior to final record generation."""
    incident_type: IncidentType
    event_confidence: float
    severity: IncidentSeverity
    reasoning: str
    details: Dict[str, Any] = field(default_factory=dict)


class BaseIncidentRule(ABC):
    """Abstract interface for all incident detection heuristics and ML models."""

    def __init__(self, name: str, incident_type: IncidentType):
        self.name = name
        self.incident_type = incident_type

    @abstractmethod
    def evaluate(
        self,
        track_id: int,
        track_state: Dict[str, Any],
        all_tracks_state: Dict[int, Dict[str, Any]],
        frame_meta: Dict[str, Any],
        config: IncidentConfig,
    ) -> Optional[IncidentCandidate]:
        """Evaluates a single vehicle track for incident criteria.

        Args:
            track_id: Persistent ID of the vehicle being evaluated.
            track_state: Historical kinematics and states for this vehicle:
                         {
                             'centroids': [(x, y), ...],
                             'timestamps': [t0, t1, ...],
                             'boxes': [[x1, y1, x2, y2], ...],
                             'velocities': [v_px_s, ...],
                             'vehicle_type': 'car'|'bus'|'truck'|'motorcycle',
                             'last_seen_frame': int
                         }
            all_tracks_state: State dictionary for all active and recently observed tracks.
            frame_meta: Metadata for current frame (e.g. frame_number, width, height, fps, etc.).
            config: Centralized threshold configuration.

        Returns:
            Optional[IncidentCandidate] if criteria are met, else None.
        """
        pass
