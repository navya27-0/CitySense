"""Route model representing designated transit routes."""

from datetime import datetime, timezone
from sqlalchemy import Column, String, DateTime, Index
from sqlalchemy.orm import relationship
from backend.database import Base


class Route(Base):
    """Represents a public transit route."""
    __tablename__ = "routes"

    route_id = Column(String(50), primary_key=True, index=True)
    route_name = Column(String(100), nullable=False)
    start_location = Column(String(255), nullable=True)
    destination = Column(String(255), nullable=True)
    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), nullable=False)

    # Relationships
    buses = relationship("Bus", back_populates="route", cascade="all, delete-orphan")
    trips = relationship("RouteTrip", back_populates="route", cascade="all, delete-orphan")

    def __repr__(self) -> str:
        return f"<Route route_id={self.route_id} name={self.route_name}>"
