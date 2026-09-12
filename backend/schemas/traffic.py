"""Pydantic schemas for traffic density measurements and spatial heatmap aggregation."""

from datetime import datetime, timezone
from typing import Optional, List, Dict, Any
from pydantic import BaseModel, Field


class TrafficMeasurementBase(BaseModel):
    """Core traffic density measurement attributes."""
    bus_id: str = Field(..., description="Unique transit bus ID", json_schema_extra={"example": "BUS_101"})
    latitude: float = Field(..., ge=-90.0, le=90.0, description="Latitude", json_schema_extra={"example": 17.385044})
    longitude: float = Field(..., ge=-180.0, le=180.0, description="Longitude", json_schema_extra={"example": 78.486671})
    car_count: int = Field(default=0, ge=0, description="Number of cars counted")
    bus_count: int = Field(default=0, ge=0, description="Number of buses counted")
    truck_count: int = Field(default=0, ge=0, description="Number of trucks counted")
    motorcycle_count: int = Field(default=0, ge=0, description="Number of motorcycles counted")
    total_vehicle_count: Optional[int] = Field(default=0, ge=0, description="Total vehicles counted")
    traffic_density: str = Field(default="LOW", description="LOW, MEDIUM, HIGH, SEVERE", json_schema_extra={"example": "MEDIUM"})
    timestamp: datetime = Field(default_factory=lambda: datetime.now(timezone.utc), description="Measurement timestamp")


class TrafficMeasurementCreate(TrafficMeasurementBase):
    """Payload for creating a traffic density measurement."""
    measurement_id: Optional[str] = None


class TrafficMeasurementResponse(TrafficMeasurementBase):
    """Response payload for traffic density measurement."""
    measurement_id: str
    is_simulated: bool = True
    disclaimer: str = "prototype traffic-density estimation — not scientifically calibrated"


class TrafficListResponse(BaseModel):
    """Paginated collection of traffic density records."""
    total: int
    count: int
    limit: int
    offset: int
    measurements: List[TrafficMeasurementResponse]
    is_simulated: bool = True


class HeatmapPoint(BaseModel):
    """A single spatial heatmap node with coordinates, intensity weight, and category."""
    latitude: float
    longitude: float
    weight: float = Field(default=1.0, description="Intensity weight between 0.1 and 10.0")
    intensity: str = Field(default="medium", description="Qualitative category: low, medium, high, critical")
    event_type: str = Field(default="ROAD_DEFECT", description="Event type: POTHOLE, DAMAGED_ROAD, RASH_DRIVING, CONGESTION, etc.")
    severity: Optional[str] = None
    bus_id: Optional[str] = None
    timestamp: Optional[datetime] = None


class HeatmapResponse(BaseModel):
    """Aggregated spatial heatmap data for GIS visualization."""
    total_points: int
    points: List[HeatmapPoint]
    filters_applied: Dict[str, Any] = Field(default_factory=dict)
    is_simulated: bool = True
    disclaimer: str = "prototype spatial aggregation — for demonstration visualization"
