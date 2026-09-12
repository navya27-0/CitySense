"""Event model representing urban detections (defects, incidents, congestion)."""

import uuid
from datetime import datetime, timezone
from typing import Optional, Dict, Any
from sqlalchemy import Column, String, Float, DateTime, ForeignKey, Index, JSON
from sqlalchemy.orm import relationship
from geoalchemy2 import Geometry
from backend.database import Base
from backend.models.spatial_utils import point_from_lat_lon, lat_lon_from_point


class Event(Base):
    """Represents an urban sensing event detected by an edge AI bus unit."""
    __tablename__ = "events"

    event_id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()), index=True)
    bus_id = Column(String(50), ForeignKey("buses.bus_id", ondelete="CASCADE"), nullable=False, index=True)
    event_type = Column(String(50), nullable=False, index=True)  # pothole, road_defect, congestion, stalled_vehicle, etc.
    confidence = Column(Float, nullable=False, default=1.0)
    
    # PostGIS Point geometry (EPSG:4326) with automatic GiST index
    location = Column(Geometry(geometry_type="POINT", srid=4326, spatial_index=True), nullable=False)
    
    timestamp = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), nullable=False, index=True)
    image_path = Column(String(500), nullable=True)
    video_timestamp = Column(Float, nullable=True)  # Video playback timestamp in seconds
    severity = Column(String(20), default="medium", nullable=False, index=True)  # low, medium, high, critical
    status = Column(String(30), default="detected", nullable=False, index=True)  # detected, verified, resolved, dismissed
    event_metadata = Column("metadata", JSON, nullable=True)  # Extra attributes e.g. bbox, area, OCR details

    # Relationships
    bus = relationship("Bus", back_populates="events")
    vehicle_detections = relationship("VehicleDetection", back_populates="event", cascade="all, delete-orphan")

    __table_args__ = (
        Index("idx_events_type_timestamp", "event_type", "timestamp"),
        Index("idx_events_bus_timestamp", "bus_id", "timestamp"),
    )

    def __init__(self, **kwargs):
        lat = kwargs.pop("latitude", None)
        lon = kwargs.pop("longitude", None)
        meta = kwargs.pop("metadata", None)
        if meta is not None and "event_metadata" not in kwargs:
            kwargs["event_metadata"] = meta
        if lat is not None and lon is not None and "location" not in kwargs:
            kwargs["location"] = point_from_lat_lon(lat, lon)
        super().__init__(**kwargs)

    @property
    def metadata_dict(self) -> Optional[Dict[str, Any]]:
        return self.event_metadata

    @property
    def latitude(self) -> Optional[float]:
        lat, _ = lat_lon_from_point(self.location)
        return lat

    @latitude.setter
    def latitude(self, val: float):
        current_lon = self.longitude or 0.0
        self.location = point_from_lat_lon(val, current_lon)

    @property
    def longitude(self) -> Optional[float]:
        _, lon = lat_lon_from_point(self.location)
        return lon

    @longitude.setter
    def longitude(self, val: float):
        current_lat = self.latitude or 0.0
        self.location = point_from_lat_lon(current_lat, val)

    def set_coordinates(self, latitude: float, longitude: float):
        self.location = point_from_lat_lon(latitude, longitude)

    def __repr__(self) -> str:
        return f"<Event event_id={self.event_id} type={self.event_type} bus_id={self.bus_id} severity={self.severity}>"
