"""Vehicle detection model for detailed object recognition and ANPR/OCR records."""

import uuid
from datetime import datetime, timezone
from sqlalchemy import Column, String, Float, Integer, DateTime, ForeignKey, Index
from sqlalchemy.orm import relationship
from backend.database import Base


class VehicleDetection(Base):
    """Represents a specific vehicle detection, tracking ID, and optional license plate OCR."""
    __tablename__ = "vehicle_detections"

    detection_id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()), index=True)
    event_id = Column(String(36), ForeignKey("events.event_id", ondelete="CASCADE"), nullable=True, index=True)
    vehicle_type = Column(String(50), nullable=False)  # car, bus, truck, motorcycle, auto_rickshaw
    tracking_id = Column(Integer, nullable=True, index=True)
    confidence = Column(Float, nullable=False, default=1.0)
    registration_number = Column(String(50), nullable=True, index=True)  # Extracted license plate (OCR)
    registration_confidence = Column(Float, nullable=True)
    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), nullable=False)

    # Relationships
    event = relationship("Event", back_populates="vehicle_detections")

    def __repr__(self) -> str:
        return f"<VehicleDetection detection_id={self.detection_id} type={self.vehicle_type} plate={self.registration_number}>"
