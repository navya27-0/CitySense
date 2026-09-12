"""Pydantic schemas for bus fleet telemetry ingestion and broadcasting.

NOTE: All schemas enforce explicit SIMULATED TELEMETRY labeling for prototype demonstration.
"""

from datetime import datetime, timezone
from typing import Optional, Dict, Any, List
from pydantic import BaseModel, Field


class BusTelemetryInput(BaseModel):
    """Input payload for a single bus telemetry packet."""
    bus_id: str = Field(..., description="Unique bus identifier, e.g. BUS_101", json_schema_extra={"example": "BUS_101"})
    route_id: Optional[str] = Field(None, description="Assigned transit route ID", json_schema_extra={"example": "216"})
    latitude: float = Field(..., ge=-90.0, le=90.0, description="WGS84 Latitude", json_schema_extra={"example": 28.7180})
    longitude: float = Field(..., ge=-180.0, le=180.0, description="WGS84 Longitude", json_schema_extra={"example": 77.0720})
    speed: float = Field(default=0.0, ge=0.0, description="Vehicle speed in km/h", json_schema_extra={"example": 35.5})
    heading: float = Field(default=0.0, ge=0.0, le=360.0, description="Direction heading in degrees", json_schema_extra={"example": 100.8})
    status: Optional[str] = Field(default="active", description="Operational status: active, idle, maintenance", json_schema_extra={"example": "active"})
    timestamp: Optional[datetime] = Field(default_factory=lambda: datetime.now(timezone.utc), description="Timestamp of telemetry capture")


class BusTelemetryBatchInput(BaseModel):
    """Input payload for multiple simultaneous bus telemetry packets."""
    telemetry: List[BusTelemetryInput]


class BusLocationResponse(BaseModel):
    """Details of current bus location and telemetry state."""
    bus_id: str
    route_id: Optional[str] = None
    latitude: Optional[float] = None
    longitude: Optional[float] = None
    speed: float = 0.0
    heading: float = 0.0
    status: str = "active"
    last_seen: datetime
    is_simulated: bool = True


class TelemetryResponse(BaseModel):
    """Standard API response for telemetry ingestion."""
    success: bool = True
    message: str = "Simulated telemetry processed successfully"
    bus_id: str
    is_simulated: bool = True
    simulation_notice: str = "SIMULATED TELEMETRY FOR HACKATHON PROTOTYPE DEMONSTRATION"
    data: BusLocationResponse
