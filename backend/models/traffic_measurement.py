"""Traffic measurement model for aggregated vehicle counts and density measurements."""

import uuid
from datetime import datetime, timezone
from typing import Optional
from sqlalchemy import Column, String, Integer, DateTime, ForeignKey, Index
from sqlalchemy.orm import relationship
from geoalchemy2 import Geometry
from backend.database import Base
from backend.models.spatial_utils import point_from_lat_lon, lat_lon_from_point


class TrafficMeasurement(Base):
    """Represents a periodic traffic density and vehicle count measurement taken by a bus unit."""
    __tablename__ = "traffic_measurements"

    measurement_id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()), index=True)
    bus_id = Column(String(50), ForeignKey("buses.bus_id", ondelete="CASCADE"), nullable=False, index=True)
    
    # PostGIS Point geometry (EPSG:4326) with automatic GiST index
    location = Column(Geometry(geometry_type="POINT", srid=4326, spatial_index=True), nullable=False)
    
    timestamp = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), nullable=False, index=True)
    car_count = Column(Integer, default=0, nullable=False)
    bus_count = Column(Integer, default=0, nullable=False)
    truck_count = Column(Integer, default=0, nullable=False)
    motorcycle_count = Column(Integer, default=0, nullable=False)
    total_vehicle_count = Column(Integer, default=0, nullable=False)
    traffic_density = Column(String(30), default="low", nullable=False)  # low, moderate, high, severe

    # Relationships
    bus = relationship("Bus", back_populates="traffic_measurements")

    __table_args__ = (
        Index("idx_traffic_bus_timestamp", "bus_id", "timestamp"),
    )

    def __init__(self, **kwargs):
        lat = kwargs.pop("latitude", None)
        lon = kwargs.pop("longitude", None)
        if lat is not None and lon is not None and "location" not in kwargs:
            kwargs["location"] = point_from_lat_lon(lat, lon)
        
        # Calculate total vehicle count automatically if not provided
        if "total_vehicle_count" not in kwargs:
            c = kwargs.get("car_count", 0)
            b = kwargs.get("bus_count", 0)
            t = kwargs.get("truck_count", 0)
            m = kwargs.get("motorcycle_count", 0)
            kwargs["total_vehicle_count"] = c + b + t + m

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
        return f"<TrafficMeasurement id={self.measurement_id} total_vehicles={self.total_vehicle_count} density={self.traffic_density}>"
