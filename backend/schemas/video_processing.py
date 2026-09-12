"""Pydantic schemas for asynchronous video processing jobs."""

from datetime import datetime, timezone
from typing import Optional, List, Dict, Any
from pydantic import BaseModel, Field


class VideoProcessResponse(BaseModel):
    """Immediate response returned upon queuing a video processing job."""
    job_id: str = Field(..., description="Unique asynchronous job identifier")
    status: str = Field(default="queued", description="Job status: queued, processing, completed, failed")
    message: str = "Video processing job accepted and queued in background"
    bus_id: str
    route_id: str
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    status_url: str = Field(..., description="Polling URL for job progress and status")
    websocket_url: str = "/ws/events"
    is_simulated: bool = True


class JobStatusResponse(BaseModel):
    """Detailed progress and execution status of a video processing job."""
    job_id: str
    status: str  # queued, processing, completed, failed
    progress_pct: float = Field(default=0.0, ge=0.0, le=100.0, description="Percentage of frames processed")
    bus_id: str
    route_id: str
    created_at: datetime
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None
    elapsed_seconds: Optional[float] = None
    total_frames: Optional[int] = None
    processed_frames: int = 0
    fps: Optional[float] = None
    events_generated: int = 0
    events_by_category: Dict[str, int] = Field(default_factory=dict)
    unique_vehicles_counted: int = 0
    output_video: Optional[str] = None
    output_json: Optional[str] = None
    evidence_dir: Optional[str] = None
    error: Optional[str] = None
    results: Optional[Dict[str, Any]] = None
    events: Optional[List[Dict[str, Any]]] = None
    is_simulated: bool = True
    disclaimer: str = "prototype heuristic estimation — rule-based detection, not forensic determination"
