"""Pydantic schemas for transit bus fleet management and spatial tracking."""

from datetime import datetime, timezone
from typing import Optional, List, Dict, Any
from pydantic import BaseModel, Field
from backend.schemas.event import EventResponse


class BusBase(BaseModel):
    """Core bus fleet attributes."""
    bus_id: str = Field(..., description="Unique transit bus fleet ID", json_schema_extra={"example": "BUS_101"})
    route_id: Optional[str] = Field(None, description="Assigned transit route ID", json_schema_extra={"example": "216"})
    latitude: Optional[float] = Field(None, ge=-90.0, le=90.0, description="Current latitude", json_schema_extra={"example": 17.385044})
    longitude: Optional[float] = Field(None, ge=-180.0, le=180.0, description="Current longitude", json_schema_extra={"example": 78.486671})
    speed: float = Field(default=0.0, ge=0.0, description="Current speed in km/h", json_schema_extra={"example": 32.5})
    heading: float = Field(default=0.0, ge=0.0, le=360.0, description="Current heading in degrees", json_schema_extra={"example": 180.0})
    status: str = Field(default="active", description="Status: active, idle, maintenance, offline", json_schema_extra={"example": "active"})
    last_seen: datetime = Field(default_factory=lambda: datetime.now(timezone.utc), description="Last telemetry update timestamp")


class BusResponse(BusBase):
    """Standard bus response payload."""
    is_simulated: bool = True


class BusDetailResponse(BusResponse):
    """Detailed bus status including active detected events."""
    active_events_count: int = 0
    recent_events: List[EventResponse] = Field(default_factory=list)


class BusListResponse(BaseModel):
    """List response of active fleet buses."""
    total: int
    buses: List[BusResponse]
    is_simulated: bool = True
