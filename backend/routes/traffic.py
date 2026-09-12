"""REST endpoints for traffic density and spatial heatmap queries."""

from datetime import datetime, timezone
from typing import List, Optional, Dict, Any
from fastapi import APIRouter, Depends, Query, status
from sqlalchemy.orm import Session
from sqlalchemy import desc

from backend.database import get_db
from backend.models import TrafficMeasurement, Event, lat_lon_from_point
from backend.schemas.traffic import (
    TrafficMeasurementResponse,
    TrafficListResponse,
    HeatmapPoint,
    HeatmapResponse,
)

router = APIRouter()

# In-memory fallback measurements
_IN_MEMORY_TRAFFIC: List[TrafficMeasurementResponse] = []


def _db_traffic_to_response(m: TrafficMeasurement) -> TrafficMeasurementResponse:
    """Converts an SQLAlchemy TrafficMeasurement model instance to schema."""
    lat, lon = lat_lon_from_point(m.location)
    return TrafficMeasurementResponse(
        measurement_id=m.measurement_id,
        bus_id=m.bus_id,
        latitude=lat if lat is not None else 0.0,
        longitude=lon if lon is not None else 0.0,
        car_count=m.car_count,
        bus_count=m.bus_count,
        truck_count=m.truck_count,
        motorcycle_count=m.motorcycle_count,
        total_vehicle_count=m.total_vehicle_count,
        traffic_density=m.traffic_density.upper(),
        timestamp=m.timestamp,
        is_simulated=True,
    )


@router.get("/traffic", response_model=TrafficListResponse, summary="List traffic density measurements")
def get_traffic_measurements(
    bus_id: Optional[str] = Query(None, description="Filter by bus fleet ID"),
    density: Optional[str] = Query(None, description="Filter by density (LOW, MEDIUM, HIGH, SEVERE)"),
    limit: int = Query(50, ge=1, le=500, description="Max records to return"),
    offset: int = Query(0, ge=0, description="Records offset"),
    db: Session = Depends(get_db),
):
    """Retrieves periodic traffic density window measurements with pagination and filtering."""
    if db is not None:
        try:
            query = db.query(TrafficMeasurement)
            if bus_id:
                query = query.filter(TrafficMeasurement.bus_id == bus_id)
            if density:
                query = query.filter(TrafficMeasurement.traffic_density.ilike(density))

            total = query.count()
            records = query.order_by(desc(TrafficMeasurement.timestamp)).offset(offset).limit(limit).all()
            meas_list = [_db_traffic_to_response(r) for r in records]

            return TrafficListResponse(
                total=total,
                count=len(meas_list),
                limit=limit,
                offset=offset,
                measurements=meas_list,
                is_simulated=True,
            )
        except Exception:
            pass

    # In-memory fallback
    filtered = list(_IN_MEMORY_TRAFFIC)
    if bus_id:
        filtered = [m for m in filtered if m.bus_id == bus_id]
    if density:
        filtered = [m for m in filtered if m.traffic_density.upper() == density.upper()]

    total = len(filtered)
    paged = filtered[offset : offset + limit]

    return TrafficListResponse(
        total=total,
        count=len(paged),
        limit=limit,
        offset=offset,
        measurements=paged,
        is_simulated=True,
    )


@router.get("/heatmap", response_model=HeatmapResponse, summary="Retrieve spatial heatmap data")
def get_spatial_heatmap(
    category: Optional[str] = Query(None, description="Filter by category: DEFECTS, INCIDENTS, TRAFFIC, ALL"),
    min_weight: float = Query(0.1, ge=0.0, le=10.0, description="Minimum weight threshold"),
    bus_id: Optional[str] = Query(None, description="Filter by bus ID"),
    db: Session = Depends(get_db),
):
    """Aggregates geographic points with severity-weighted intensity values for GIS map layers."""
    points: List[HeatmapPoint] = []
    cat_upper = category.upper() if category else "ALL"

    if db is not None:
        try:
            # 1. Road Defects and Incidents
            if cat_upper in ("DEFECTS", "INCIDENTS", "ALL"):
                eq = db.query(Event)
                if bus_id:
                    eq = eq.filter(Event.bus_id == bus_id)
                events = eq.limit(500).all()

                for e in events:
                    lat, lon = lat_lon_from_point(e.location)
                    if lat is None or lon is None:
                        continue

                    # Severity to numerical weight mapping
                    sev = e.severity.lower()
                    if sev == "critical":
                        weight = 4.0
                    elif sev == "high":
                        weight = 3.0
                    elif sev == "medium":
                        weight = 2.0
                    else:
                        weight = 1.0

                    if weight >= min_weight:
                        points.append(
                            HeatmapPoint(
                                latitude=lat,
                                longitude=lon,
                                weight=weight,
                                intensity=sev,
                                event_type=e.event_type,
                                severity=e.severity.upper(),
                                bus_id=e.bus_id,
                                timestamp=e.timestamp,
                            )
                        )

            # 2. Traffic Congestion Points
            if cat_upper in ("TRAFFIC", "ALL"):
                tq = db.query(TrafficMeasurement)
                if bus_id:
                    tq = tq.filter(TrafficMeasurement.bus_id == bus_id)
                traffic_records = tq.limit(500).all()

                for t in traffic_records:
                    lat, lon = lat_lon_from_point(t.location)
                    if lat is None or lon is None:
                        continue

                    density = t.traffic_density.upper()
                    if density == "SEVERE" or density == "HIGH":
                        weight = 3.5
                        intensity = "high"
                    elif density == "MEDIUM":
                        weight = 2.0
                        intensity = "medium"
                    else:
                        weight = 0.8
                        intensity = "low"

                    if weight >= min_weight:
                        points.append(
                            HeatmapPoint(
                                latitude=lat,
                                longitude=lon,
                                weight=weight,
                                intensity=intensity,
                                event_type=f"TRAFFIC_{density}",
                                severity=density,
                                bus_id=t.bus_id,
                                timestamp=t.timestamp,
                            )
                        )

            if points:
                return HeatmapResponse(
                    total_points=len(points),
                    points=points,
                    filters_applied={"category": cat_upper, "min_weight": min_weight, "bus_id": bus_id},
                    is_simulated=True,
                )
        except Exception:
            pass

    # Fallback points if database is empty or offline
    fallback_points = [
        HeatmapPoint(latitude=17.385044, longitude=78.486671, weight=3.0, intensity="high", event_type="POTHOLE", severity="HIGH", bus_id="BUS_101"),
        HeatmapPoint(latitude=17.391600, longitude=78.435000, weight=2.0, intensity="medium", event_type="DAMAGED_ROAD", severity="MEDIUM", bus_id="BUS_101"),
        HeatmapPoint(latitude=17.439900, longitude=78.498300, weight=3.5, intensity="high", event_type="TRAFFIC_HIGH", severity="HIGH", bus_id="BUS_102"),
    ]
    return HeatmapResponse(
        total_points=len(fallback_points),
        points=fallback_points,
        filters_applied={"category": cat_upper, "min_weight": min_weight, "bus_id": bus_id},
        is_simulated=True,
    )
