"""Pydantic schemas package for request/response serialization."""

from backend.schemas.telemetry import (
    BusTelemetryInput,
    BusTelemetryBatchInput,
    BusLocationResponse,
    TelemetryResponse,
)
from backend.schemas.event import (
    EventBase,
    EventCreate,
    EventResponse,
    EventListResponse,
)
from backend.schemas.bus import (
    BusBase,
    BusResponse,
    BusDetailResponse,
    BusListResponse,
)
from backend.schemas.traffic import (
    TrafficMeasurementBase,
    TrafficMeasurementCreate,
    TrafficMeasurementResponse,
    TrafficListResponse,
    HeatmapPoint,
    HeatmapResponse,
)
from backend.schemas.video_processing import (
    VideoProcessResponse,
    JobStatusResponse,
)
from backend.schemas.analytics import (
    AnalyticsMeta,
    AnalyticsSummaryResponse,
    VehicleCountsResponse,
    TrafficDensityResponse,
    CongestionHotspotsResponse,
    EventsByTypeResponse,
    EventsByLocationResponse,
    EventsByTimeResponse,
    RouteDelaysResponse,
    BusActivityResponse,
    RoadDefectsFrequencyResponse,
)

__all__ = [
    "BusTelemetryInput",
    "BusTelemetryBatchInput",
    "BusLocationResponse",
    "TelemetryResponse",
    "EventBase",
    "EventCreate",
    "EventResponse",
    "EventListResponse",
    "BusBase",
    "BusResponse",
    "BusDetailResponse",
    "BusListResponse",
    "TrafficMeasurementBase",
    "TrafficMeasurementCreate",
    "TrafficMeasurementResponse",
    "TrafficListResponse",
    "HeatmapPoint",
    "HeatmapResponse",
    "VideoProcessResponse",
    "JobStatusResponse",
    "AnalyticsMeta",
    "AnalyticsSummaryResponse",
    "VehicleCountsResponse",
    "TrafficDensityResponse",
    "CongestionHotspotsResponse",
    "EventsByTypeResponse",
    "EventsByLocationResponse",
    "EventsByTimeResponse",
    "RouteDelaysResponse",
    "BusActivityResponse",
    "RoadDefectsFrequencyResponse",
]
