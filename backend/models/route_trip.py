"""Route trip model for transit schedule delay analysis."""

import uuid
from datetime import datetime, timezone
from sqlalchemy import Column, String, Float, DateTime, ForeignKey, Index
from sqlalchemy.orm import relationship
from backend.database import Base


class RouteTrip(Base):
    """Represents a scheduled or executed trip by a bus on a specific route."""
    __tablename__ = "route_trips"

    trip_id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()), index=True)
    bus_id = Column(String(50), ForeignKey("buses.bus_id", ondelete="CASCADE"), nullable=False, index=True)
    route_id = Column(String(50), ForeignKey("routes.route_id", ondelete="CASCADE"), nullable=False, index=True)
    start_time = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), nullable=False, index=True)
    end_time = Column(DateTime(timezone=True), nullable=True)
    expected_duration = Column(Float, nullable=False)  # Duration in minutes
    actual_duration = Column(Float, nullable=True)  # Duration in minutes
    delay_minutes = Column(Float, default=0.0, nullable=False)

    # Relationships
    bus = relationship("Bus", back_populates="trips")
    route = relationship("Route", back_populates="trips")

    __table_args__ = (
        Index("idx_trips_route_bus", "route_id", "bus_id"),
    )

    def calculate_delay(self):
        """Calculates delay_minutes based on actual vs expected duration."""
        if self.actual_duration is not None and self.expected_duration is not None:
            self.delay_minutes = max(0.0, self.actual_duration - self.expected_duration)

    def __repr__(self) -> str:
        return f"<RouteTrip trip_id={self.trip_id} bus_id={self.bus_id} route_id={self.route_id} delay={self.delay_minutes}m>"
