"""Pydantic schemas for urban analytics module."""

from datetime import datetime
from typing import List, Optional, Dict, Any
from pydantic import BaseModel, Field


# ==============================================================================
# 0. COMMON FILTER & META SCHEMAS
# ==============================================================================

class AnalyticsMeta(BaseModel):
    """Metadata for analytics query responses."""
    generated_at: datetime = Field(default_factory=datetime.utcnow)
    time_range: str = Field("all", description="Applied time range filter (1h, 6h, 24h, 7d, 30d, all, custom)")
    start_time: Optional[datetime] = None
    end_time: Optional[datetime] = None
    route_id: Optional[str] = None
    bus_id: Optional[str] = None
    has_data: bool = Field(True, description="True if database contains sufficient data, false otherwise")
    message: Optional[str] = None


# ==============================================================================
# 1. SUMMARY METRICS CARD SCHEMA
# ==============================================================================

class AnalyticsSummaryResponse(BaseModel):
    """Top-level summary KPIs for the urban analytics dashboard."""
    meta: AnalyticsMeta
    total_vehicles_counted: int = 0
    avg_traffic_density_index: float = 0.0  # Normalized 0.0 - 1.0 (Low to Severe)
    active_congestion_hotspots: int = 0
    total_events_detected: int = 0
    road_defects_count: int = 0
    safety_incidents_count: int = 0
    avg_route_delay_minutes: float = 0.0
    active_fleet_buses: int = 0
    on_time_trip_rate_pct: float = 0.0  # Percentage of trips with delay <= 0


# ==============================================================================
# 2. VEHICLE COUNTS
# ==============================================================================

class VehicleTypeCount(BaseModel):
    category: str  # car, bus, truck, motorcycle
    count: int = 0
    percentage: float = 0.0

class VehicleCountTimelineItem(BaseModel):
    timestamp: datetime
    label: str  # Formatted hour/date
    car_count: int = 0
    bus_count: int = 0
    truck_count: int = 0
    motorcycle_count: int = 0
    total_count: int = 0

class VehicleCountsResponse(BaseModel):
    meta: AnalyticsMeta
    total_count: int = 0
    by_category: List[VehicleTypeCount] = []
    timeline: List[VehicleCountTimelineItem] = []


# ==============================================================================
# 3. TRAFFIC DENSITY DISTRIBUTION
# ==============================================================================

class DensityDistributionItem(BaseModel):
    density_level: str  # LOW, MEDIUM, HIGH, SEVERE
    sample_count: int = 0
    percentage: float = 0.0

class TrafficDensityResponse(BaseModel):
    meta: AnalyticsMeta
    distribution: List[DensityDistributionItem] = []
    average_density_label: str = "LOW"
    total_measurements: int = 0


# ==============================================================================
# 4. CONGESTION HOTSPOTS
# ==============================================================================

class HotspotItem(BaseModel):
    hotspot_id: str
    location_name: str
    route_id: Optional[str] = None
    latitude: float
    longitude: float
    density_level: str  # HIGH, SEVERE, etc.
    observed_vehicles: int = 0
    avg_speed_kmh: Optional[float] = None
    measurement_count: int = 1
    last_detected: datetime

class CongestionHotspotsResponse(BaseModel):
    meta: AnalyticsMeta
    hotspots: List[HotspotItem] = []
    total_hotspots: int = 0


# ==============================================================================
# 5. EVENTS BY TYPE
# ==============================================================================

class EventTypeItem(BaseModel):
    event_type: str
    category: str
    count: int = 0
    percentage: float = 0.0

class EventsByTypeResponse(BaseModel):
    meta: AnalyticsMeta
    total_events: int = 0
    types: List[EventTypeItem] = []


# ==============================================================================
# 6. EVENTS BY LOCATION / ROUTE
# ==============================================================================

class EventLocationItem(BaseModel):
    location_identifier: str  # Route ID or corridor name
    route_name: Optional[str] = None
    defect_count: int = 0
    incident_count: int = 0
    congestion_count: int = 0
    total_count: int = 0

class EventsByLocationResponse(BaseModel):
    meta: AnalyticsMeta
    locations: List[EventLocationItem] = []
    total_events: int = 0


# ==============================================================================
# 7. EVENTS BY TIME (TIMELINE)
# ==============================================================================

class EventTimelineItem(BaseModel):
    timestamp: datetime
    label: str
    defects: int = 0
    incidents: int = 0
    congestion: int = 0
    total: int = 0

class EventsByTimeResponse(BaseModel):
    meta: AnalyticsMeta
    timeline: List[EventTimelineItem] = []
    total_events: int = 0


# ==============================================================================
# 8. ROUTE DELAYS
# ==============================================================================

class RouteDelayItem(BaseModel):
    route_id: str
    route_name: str
    total_trips: int = 0
    avg_expected_duration_min: float = 0.0
    avg_actual_duration_min: float = 0.0
    avg_delay_minutes: float = 0.0  # actual_duration - expected_duration
    max_delay_minutes: float = 0.0
    on_time_trips: int = 0
    on_time_rate_pct: float = 0.0

class RouteDelaysResponse(BaseModel):
    meta: AnalyticsMeta
    formula: str = "delay = actual_duration - expected_duration"
    routes: List[RouteDelayItem] = []
    overall_avg_delay_minutes: float = 0.0
    overall_on_time_pct: float = 0.0


# ==============================================================================
# 9. BUS ACTIVITY
# ==============================================================================

class BusActivityItem(BaseModel):
    bus_id: str
    route_id: Optional[str] = None
    status: str
    speed_kmh: float = 0.0
    last_seen: datetime
    trips_completed: int = 0
    total_events_logged: int = 0
    traffic_measurements_taken: int = 0

class BusActivityResponse(BaseModel):
    meta: AnalyticsMeta
    fleet: List[BusActivityItem] = []
    total_buses: int = 0
    active_buses: int = 0


# ==============================================================================
# 10. ROAD-DEFECT FREQUENCY BY SUBTYPE
# ==============================================================================

class DefectSubtypeFrequencyItem(BaseModel):
    subtype: str  # POTHOLE, DAMAGED_ROAD, WATERLOGGING, MISSING_DIVIDER, DAMAGED_SIGNBOARD
    display_name: str
    count: int = 0
    percentage: float = 0.0
    critical_count: int = 0
    high_count: int = 0
    medium_count: int = 0
    low_count: int = 0

class RoadDefectsFrequencyResponse(BaseModel):
    meta: AnalyticsMeta
    subtypes: List[DefectSubtypeFrequencyItem] = []
    total_defects: int = 0


# ==============================================================================
# 11. ORIGIN-DESTINATION (OD) MATRIX SCHEMAS
# ==============================================================================

class ODPairItem(BaseModel):
    pair_id: str
    route_id: str
    origin_stop: str
    destination_stop: str
    origin_lat: float
    origin_lon: float
    dest_lat: float
    dest_lon: float
    trip_count: int = 0
    avg_duration_minutes: float = 0.0
    avg_speed_kmh: float = 0.0
    distance_km: float = 0.0
    buses_observed: List[str] = []


class ODMatrixSummary(BaseModel):
    total_od_pairs: int = 0
    total_trips_analyzed: int = 0
    busiest_corridor: Optional[str] = None
    busiest_pair: Optional[str] = None
    avg_trip_duration_minutes: float = 0.0
    data_source: str = "Simulated Fleet Telemetry (Bus Stop Segment Inference)"
    disclaimer: str = "Fleet Telemetry Inferred: Based on vehicle transit segments between designated stops — NOT passenger-level tracking."


class ODMatrixResponse(BaseModel):
    meta: AnalyticsMeta
    summary: ODMatrixSummary
    od_pairs: List[ODPairItem] = []
    stops_by_route: Dict[str, List[str]] = {}
    matrix_grid: Dict[str, Dict[str, int]] = {}

