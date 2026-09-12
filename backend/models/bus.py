"""Bus fleet model representing mobile sensing public transit units."""

from datetime import datetime, timezone
from typing import Optional
from sqlalchemy import Column, String, Float, DateTime, ForeignKey, Index
from sqlalchemy.orm import relationship
from geoalchemy2 import Geometry
from backend.database import Base
from backend.models.spatial_utils import point_from_lat_lon, lat_lon_from_point


class Bus(Base):
    """Represents a public transit bus equipped with mobile sensing unit."""
    __tablename__ = "buses"

    bus_id = Column(String(50), primary_key=True, index=True)
    route_id = Column(String(50), ForeignKey("routes.route_id", ondelete="SET NULL"), nullable=True, index=True)
    
    # PostGIS Point geometry (EPSG:4326) with automatic GiST spatial index
    location = Column(Geometry(geometry_type="POINT", srid=4326, spatial_index=True), nullable=True)
    
    speed = Column(Float, default=0.0, nullable=False)  # in km/h
    heading = Column(Float, default=0.0, nullable=False)  # in degrees (0-360)
    status = Column(String(30), default="active", nullable=False, index=True)  # active, idle, maintenance, offline
    last_seen = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc), nullable=False)

    # Relationships
    route = relationship("Route", back_populates="buses")
    events = relationship("Event", back_populates="bus", cascade="all, delete-orphan")
    traffic_measurements = relationship("TrafficMeasurement", back_populates="bus", cascade="all, delete-orphan")
    trips = relationship("RouteTrip", back_populates="bus", cascade="all, delete-orphan")

    def __init__(self, **kwargs):
        lat = kwargs.pop("latitude", None)
        lon = kwargs.pop("longitude", None)
        if lat is not None and lon is not None and "location" not in kwargs:
            kwargs["location"] = point_from_lat_lon(lat, lon)
        super().__init__(**kwargs)

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
        return f"<Bus bus_id={self.bus_id} route_id={self.route_id} status={self.status}>"
