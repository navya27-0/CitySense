"""Pydantic schemas for Edge Processing metrics and bandwidth demonstration."""

from typing import Optional, Dict, Any
from pydantic import BaseModel, Field


class SlimEventPayload(BaseModel):
    """The minimal event payload transmitted from edge to backend.
    
    This is the exact data contract that crosses the network boundary.
    Everything else (raw video frames, intermediate CV tensors, tracking state)
    stays on the edge device and is never uploaded.
    """
    event_type: str = Field(..., description="Detection category (e.g. POTHOLE, RASH_DRIVING)")
    confidence: float = Field(..., ge=0.0, le=1.0, description="AI model confidence score")
    bus_id: str = Field(..., description="Transit bus fleet identifier")
    timestamp: str = Field(..., description="ISO-8601 UTC timestamp from GPS synchronizer")
    latitude: float = Field(..., ge=-90.0, le=90.0)
    longitude: float = Field(..., ge=-180.0, le=180.0)
    tracking_id: Optional[int] = Field(None, description="ByteTrack vehicle tracking ID (if applicable)")
    registration_number: Optional[str] = Field(None, description="ANPR-extracted license plate (if available)")
    evidence_image_ref: Optional[str] = Field(None, description="Path to single evidence frame (not full video)")


class EdgeMetricsResponse(BaseModel):
    """Response schema for GET /api/edge-metrics.

    All bandwidth figures are estimates derived from this prototype's actual
    processing dimensions — not generalized industry benchmarks.
    """
    frames_processed_locally: int = Field(..., description="Total video frames processed on the edge device")
    events_generated: int = Field(..., description="Structured events emitted by the AI pipeline")
    video_resolution: str = Field("1920x1080", description="Resolution of processed video (WxH)")
    video_fps: float = Field(30.0, description="Frame rate of source video")
    raw_frame_size_bytes: int = Field(..., description="Size of a single uncompressed BGR frame in bytes")
    raw_video_data_bytes: int = Field(..., description="Estimated total raw video data (frames × frame_size)")
    raw_video_data_display: str = Field(..., description="Human-readable raw video size (e.g. '1.17 GB')")
    transmitted_event_data_bytes: int = Field(..., description="Total JSON payload bytes of all slim events")
    transmitted_event_data_display: str = Field(..., description="Human-readable transmitted event size")
    evidence_images_bytes: int = Field(0, description="Total bytes of evidence image files transmitted")
    evidence_images_display: str = Field("0 B", description="Human-readable evidence images size")
    total_transmitted_bytes: int = Field(..., description="Events + evidence images total")
    total_transmitted_display: str = Field(..., description="Human-readable total transmitted size")
    bandwidth_reduction_pct: float = Field(..., ge=0.0, le=100.0, description="Estimated bandwidth reduction percentage")
    per_event_payload_example: Dict[str, Any] = Field(
        default_factory=dict,
        description="Example of a single slim event payload showing what crosses the wire"
    )
    events_payload_fields: list = Field(
        default_factory=lambda: [
            "event_type", "confidence", "bus_id", "timestamp",
            "latitude", "longitude", "tracking_id",
            "registration_number", "evidence_image_ref"
        ],
        description="Exhaustive list of fields transmitted per event"
    )
    disclaimer: str = Field(
        default="Estimate based on this prototype's processing run — not a general industry claim.",
        description="Mandatory disclaimer for all bandwidth reduction figures"
    )
    is_simulated: bool = Field(True, description="Whether this data comes from prototype/demo processing")
