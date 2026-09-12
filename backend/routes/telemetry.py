"""Telemetry ingestion and live fleet status routes.

NOTE: All endpoints handle SIMULATED TELEMETRY for prototype demonstration.
"""

from datetime import datetime, timezone
from typing import List, Optional
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from backend.database import get_db
from backend.models import Bus, Route, point_from_lat_lon, lat_lon_from_point
from backend.schemas.telemetry import (
    BusTelemetryInput,
    BusTelemetryBatchInput,
    BusLocationResponse,
    TelemetryResponse,
)
from backend.websocket import manager

router = APIRouter()


# In-memory latest telemetry fallback state for prototype resilience
_LATEST_BUS_TELEMETRY: Dict[str, BusLocationResponse] = {
    "BUS_101": BusLocationResponse(
        bus_id="BUS_101",
        route_id="216",
        latitude=17.3916,
        longitude=78.4350,
        speed=34.5,
        heading=115.0,
        status="active",
        last_seen=datetime.now(timezone.utc),
        is_simulated=True,
    ),
    "BUS_102": BusLocationResponse(
        bus_id="BUS_102",
        route_id="100",
        latitude=17.4340,
        longitude=78.5015,
        speed=26.0,
        heading=185.0,
        status="active",
        last_seen=datetime.now(timezone.utc),
        is_simulated=True,
    ),
    "BUS_103": BusLocationResponse(
        bus_id="BUS_103",
        route_id="49M",
        latitude=17.3688,
        longitude=78.5247,
        speed=18.0,
        heading=45.0,
        status="active",
        last_seen=datetime.now(timezone.utc),
        is_simulated=True,
    ),
}


@router.post("", response_model=TelemetryResponse, summary="Ingest single simulated bus telemetry")
async def ingest_telemetry(payload: BusTelemetryInput, db: Session = Depends(get_db)):
    """Receives simulated GPS telemetry from a bus sensing unit.
    
    1. Persists/updates location and motion state in PostgreSQL/PostGIS (when available).
    2. Broadcasts updated bus coordinates over WebSocket to live GIS clients.
    """
    ts = payload.timestamp or datetime.now(timezone.utc)
    route_id = payload.route_id or "N/A"

    # 1. Update or create bus record in PostgreSQL/PostGIS
    if db is not None:
        try:
            if payload.route_id:
                route = db.query(Route).filter_by(route_id=payload.route_id).first()
                if not route:
                    route = Route(
                        route_id=payload.route_id,
                        route_name=f"Route {payload.route_id} (Simulated)",
                    )
                    db.add(route)
                    db.flush()

            bus = db.query(Bus).filter_by(bus_id=payload.bus_id).first()
            if not bus:
                bus = Bus(
                    bus_id=payload.bus_id,
                    route_id=payload.route_id,
                    latitude=payload.latitude,
                    longitude=payload.longitude,
                    speed=payload.speed,
                    heading=payload.heading,
                    status=payload.status or "active",
                    last_seen=ts,
                )
                db.add(bus)
            else:
                if payload.route_id:
                    bus.route_id = payload.route_id
                bus.set_coordinates(payload.latitude, payload.longitude)
                bus.speed = payload.speed
                bus.heading = payload.heading
                bus.status = payload.status or bus.status
                bus.last_seen = ts

            db.commit()
            route_id = bus.route_id or route_id
        except Exception:
            try:
                db.rollback()
            except Exception:
                pass

    # Update in-memory fallback state
    loc_resp = BusLocationResponse(
        bus_id=payload.bus_id,
        route_id=route_id,
        latitude=payload.latitude,
        longitude=payload.longitude,
        speed=payload.speed,
        heading=payload.heading,
        status=payload.status or "active",
        last_seen=ts,
        is_simulated=True,
    )
    _LATEST_BUS_TELEMETRY[payload.bus_id] = loc_resp

    # 2. Broadcast live coordinates over WebSocket to frontend dashboards
    telemetry_data = {
        "bus_id": payload.bus_id,
        "route_id": route_id,
        "latitude": payload.latitude,
        "longitude": payload.longitude,
        "speed": payload.speed,
        "heading": payload.heading,
        "status": payload.status or "active",
        "timestamp": ts.isoformat(),
    }

    await manager.broadcast_buses({
        "type": "bus_telemetry",
        "is_simulated": True,
        "simulation_notice": "SIMULATED TELEMETRY FOR HACKATHON PROTOTYPE DEMONSTRATION",
        "data": telemetry_data,
    })

    return TelemetryResponse(
        success=True,
        message="Simulated telemetry processed and broadcasted",
        bus_id=payload.bus_id,
        is_simulated=True,
        data=loc_resp,
    )


@router.get("/buses", response_model=List[BusLocationResponse], summary="List all buses with latest simulated locations")
def get_all_buses(db: Session = Depends(get_db)):
    """Retrieves current active fleet positions and status from PostgreSQL/PostGIS or fallback state."""
    results = []
    if db is not None:
        try:
            buses = db.query(Bus).all()
            for b in buses:
                lat, lon = lat_lon_from_point(b.location)
                results.append(
                    BusLocationResponse(
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
                )
            if results:
                return results
        except Exception:
            pass

    # Fallback to in-memory state
    return list(_LATEST_BUS_TELEMETRY.values())
