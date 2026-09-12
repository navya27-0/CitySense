"""Pydantic schemas for urban sensing events (road defects, incidents, congestion)."""

from datetime import datetime, timezone
from typing import Optional, Dict, Any, List
from pydantic import BaseModel, Field


class EventBase(BaseModel):
    """Base fields common to urban sensing events."""
    bus_id: str = Field(..., description="Unique bus fleet identifier", json_schema_extra={"example": "BUS_101"})
    event_type: str = Field(..., description="Subtype: POTHOLE, DAMAGED_ROAD, RASH_DRIVING, SUSPECTED_HIT_AND_RUN, etc.", json_schema_extra={"example": "POTHOLE"})
    event_category: Optional[str] = Field(default="ROAD_DEFECT", description="Category: ROAD_DEFECT, TRAFFIC_INCIDENT, TRAFFIC_DENSITY", json_schema_extra={"example": "ROAD_DEFECT"})
    confidence: float = Field(default=1.0, ge=0.0, le=1.0, description="Confidence score between 0.0 and 1.0", json_schema_extra={"example": 0.88})
    latitude: float = Field(..., ge=-90.0, le=90.0, description="WGS84 Latitude", json_schema_extra={"example": 17.385044})
    longitude: float = Field(..., ge=-180.0, le=180.0, description="WGS84 Longitude", json_schema_extra={"example": 78.486671})
    severity: str = Field(default="medium", description="Severity level: low, medium, high, critical", json_schema_extra={"example": "high"})
    status: str = Field(default="detected", description="Status: detected, verified, resolved, dismissed, NEW", json_schema_extra={"example": "detected"})
    image_path: Optional[str] = Field(default=None, description="Path or URL to saved evidence image", json_schema_extra={"example": "/evidence/road_defects/defect_BUS_101_POTHOLE_000045.jpg"})
    video_timestamp: Optional[float] = Field(default=None, ge=0.0, description="Relative timestamp in video (seconds)", json_schema_extra={"example": 1.5})
    details: Optional[Dict[str, Any]] = Field(default_factory=dict, description="Metadata dictionary (bounding box, OCR info, kinematics)", json_schema_extra={"example": {"bounding_box": [100, 200, 300, 400]}})
    timestamp: Optional[datetime] = Field(default_factory=lambda: datetime.now(timezone.utc), description="Timestamp of event occurrence")


class EventCreate(EventBase):
    """Payload for creating a new urban sensing event."""
    event_id: Optional[str] = Field(default=None, description="Optional custom unique event ID (auto-generated if omitted)")
    route_id: Optional[str] = Field(default=None, description="Assigned route ID if known", json_schema_extra={"example": "216"})


class EventResponse(EventBase):
    """Serialized urban sensing event response."""
    event_id: str
    route_id: Optional[str] = None
    is_simulated: bool = True
    disclaimer: str = "prototype heuristic estimation — rule-based detection, not forensic determination"


class EventStatusUpdate(BaseModel):
    """Payload for updating an event or incident lifecycle status."""
    status: str = Field(..., description="NEW, UNDER_REVIEW, RESOLVED, FALSE_POSITIVE", json_schema_extra={"example": "UNDER_REVIEW"})


class EventListResponse(BaseModel):
    """Paginated collection of urban sensing events."""
    total: int
    count: int
    limit: int
    offset: int
    events: List[EventResponse]
    is_simulated: bool = True
