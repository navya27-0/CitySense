"""REST endpoints for bus fleet status and spatial queries."""

from typing import List, Optional
from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session
from sqlalchemy import desc

from backend.database import get_db
from backend.models import Bus, Event, lat_lon_from_point
from backend.schemas.bus import (
    BusResponse,
    BusDetailResponse,
    BusListResponse,
)
from backend.schemas.event import EventResponse
from backend.routes.events import _db_event_to_response, _IN_MEMORY_EVENTS
from backend.routes.telemetry import _LATEST_BUS_TELEMETRY

router = APIRouter()


def _db_bus_to_response(b: Bus) -> BusResponse:
    """Converts an SQLAlchemy Bus instance to a BusResponse schema."""
    lat, lon = lat_lon_from_point(b.location)
    return BusResponse(
        bus_id=b.bus_id,
        route_id=b.route_id,
        latitude=lat,
        longitude=lon,
        speed=b.speed,
        heading=b.heading,
        status=b.status,
        last_seen=b.last_seen,
        is_simulated=True,
    )


@router.get("", response_model=List[BusResponse], summary="List all active transit buses")
def get_all_buses(
    status_filter: Optional[str] = Query(None, alias="status", description="Filter by operational status"),
    route_id: Optional[str] = Query(None, description="Filter by route ID"),
    db: Session = Depends(get_db),
):
    """Returns real-time fleet locations and telemetry status for all active transit buses."""
    results = []
    if db is not None:
        try:
            query = db.query(Bus)
            if status_filter:
                query = query.filter(Bus.status.ilike(status_filter))
            if route_id:
                query = query.filter(Bus.route_id == route_id)

            buses = query.all()
            for b in buses:
                results.append(_db_bus_to_response(b))

            if results:
                return results
        except Exception:
            pass

    # Fallback to in-memory telemetry state
    fallback = []
    for bus_resp in _LATEST_BUS_TELEMETRY.values():
        if status_filter and bus_resp.status.lower() != status_filter.lower():
            continue
        if route_id and bus_resp.route_id != route_id:
            continue
        fallback.append(
            BusResponse(
                bus_id=bus_resp.bus_id,
                route_id=bus_resp.route_id,
                latitude=bus_resp.latitude,
                longitude=bus_resp.longitude,
                speed=bus_resp.speed,
                heading=bus_resp.heading,
                status=bus_resp.status,
                last_seen=bus_resp.last_seen,
                is_simulated=True,
            )
        )

    return fallback


@router.get("/{bus_id}", response_model=BusDetailResponse, summary="Get details for a specific bus")
def get_bus_by_id(bus_id: str, db: Session = Depends(get_db)):
    """Retrieves full details, latest location, and recent urban events for a specific bus. Returns 404 if not found."""
    if db is not None:
        try:
            bus = db.query(Bus).filter(Bus.bus_id == bus_id).first()
            if bus:
                base = _db_bus_to_response(bus)
                recent_evts = db.query(Event).filter(Event.bus_id == bus_id).order_by(desc(Event.timestamp)).limit(10).all()
                evts_resp = [_db_event_to_response(e) for e in recent_evts]
                return BusDetailResponse(
                    **base.model_dump(),
                    active_events_count=len(evts_resp),
                    recent_events=evts_resp,
                )
        except Exception:
            pass

    # Fallback lookup in in-memory state
    if bus_id in _LATEST_BUS_TELEMETRY:
        loc = _LATEST_BUS_TELEMETRY[bus_id]
        recent = [e for e in _IN_MEMORY_EVENTS.values() if e.bus_id == bus_id][:10]
        return BusDetailResponse(
            bus_id=loc.bus_id,
            route_id=loc.route_id,
            latitude=loc.latitude,
            longitude=loc.longitude,
            speed=loc.speed,
            heading=loc.heading,
            status=loc.status,
            last_seen=loc.last_seen,
            active_events_count=len(recent),
            recent_events=recent,
            is_simulated=True,
        )

    raise HTTPException(
        status_code=status.HTTP_404_NOT_FOUND,
        detail=f"Bus with ID '{bus_id}' not found.",
    )
