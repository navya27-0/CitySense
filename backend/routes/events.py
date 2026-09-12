"""REST endpoints for urban sensing events (road defects, incidents, congestion)."""

import uuid
from datetime import datetime, timezone
from typing import List, Optional, Dict, Any
from fastapi import APIRouter, Depends, HTTPException, Query, Response, status
from sqlalchemy.orm import Session
from sqlalchemy import desc

from backend.database import get_db
from backend.models import Event, Bus, Route, lat_lon_from_point
from backend.schemas.event import (
    EventCreate,
    EventResponse,
    EventListResponse,
    EventStatusUpdate,
)
from backend.websocket import manager
from backend.services.pdf_report import generate_single_incident_pdf, generate_batch_incidents_pdf

router = APIRouter()

# In-memory fallback event storage for offline development resilience
_IN_MEMORY_EVENTS: Dict[str, EventResponse] = {
    "defect_001": EventResponse(
        event_id="defect_001",
        bus_id="BUS_101",
        route_id="216",
        event_type="POTHOLE",
        event_category="ROAD_DEFECT",
        confidence=0.92,
        latitude=17.3985,
        longitude=78.4480,
        severity="HIGH",
        status="detected",
        image_path="/evidence/events/roaddefect_BUS101_POTHOLE_000000.jpg",
        video_timestamp=1.2,
        details={"area_px": 14200, "depth_estimate": "medium"},
        timestamp=datetime.now(timezone.utc),
        is_simulated=True,
    ),
    "defect_002": EventResponse(
        event_id="defect_002",
        bus_id="BUS_101",
        route_id="216",
        event_type="DAMAGED_ROAD",
        event_category="ROAD_DEFECT",
        confidence=0.88,
        latitude=17.4120,
        longitude=78.4620,
        severity="MEDIUM",
        status="detected",
        image_path="/evidence/events/roaddefect_BUS101_DAMAGED_ROAD_000000.jpg",
        video_timestamp=2.8,
        details={"crack_pattern": "alligator", "length_m": 4.5},
        timestamp=datetime.now(timezone.utc),
        is_simulated=True,
    ),
    "defect_003": EventResponse(
        event_id="defect_003",
        bus_id="BUS_102",
        route_id="100",
        event_type="WATERLOGGING",
        event_category="ROAD_DEFECT",
        confidence=0.95,
        latitude=17.4380,
        longitude=78.4890,
        severity="HIGH",
        status="detected",
        image_path="/evidence/events/roaddefect_BUS101_WATERLOGGING_000210.jpg",
        video_timestamp=4.1,
        details={"water_spread": "lane_blocking", "risk": "hydroplaning"},
        timestamp=datetime.now(timezone.utc),
        is_simulated=True,
    ),
    "defect_004": EventResponse(
        event_id="defect_004",
        bus_id="BUS_103",
        route_id="49M",
        event_type="DAMAGED_SIGNBOARD",
        event_category="ROAD_DEFECT",
        confidence=0.84,
        latitude=17.3750,
        longitude=78.5120,
        severity="LOW",
        status="detected",
        image_path="/evidence/events/roaddefect_BUS101_DAMAGED_SIGNBOARD_000300.jpg",
        video_timestamp=6.0,
        details={"type": "speed_limit_sign", "damage": "bent_post"},
        timestamp=datetime.now(timezone.utc),
        is_simulated=True,
    ),
    "incident_001": EventResponse(
        event_id="incident_001",
        bus_id="BUS_101",
        route_id="216",
        event_type="RASH_DRIVING",
        event_category="TRAFFIC_INCIDENT",
        confidence=0.91,
        latitude=17.4050,
        longitude=78.4550,
        severity="CRITICAL",
        status="NEW",
        image_path="/evidence/incidents/incident_BUS_101_RASH_DRIVING_0001_000005.jpg",
        video_timestamp=0.8,
        details={"registration_number": "TS09EA1234", "kinematic_trigger": "High-speed slalom weaving (280 norm-px/s)"},
        timestamp=datetime.now(timezone.utc),
        is_simulated=True,
    ),
    "incident_002": EventResponse(
        event_id="incident_002",
        bus_id="BUS_102",
        route_id="100",
        event_type="SUSPECTED_HIT_AND_RUN",
        event_category="TRAFFIC_INCIDENT",
        confidence=0.87,
        latitude=17.4290,
        longitude=78.4950,
        severity="CRITICAL",
        status="NEW",
        image_path="/evidence/incidents/incident_BUS_101_RASH_DRIVING_0002_000116.jpg",
        video_timestamp=3.5,
        details={"registration_number": "TS07UK9876", "kinematic_trigger": "Inter-vehicle collision overlap + flight acceleration surge"},
        timestamp=datetime.now(timezone.utc),
        is_simulated=True,
    ),
    "traffic_001": EventResponse(
        event_id="traffic_001",
        bus_id="BUS_101",
        route_id="216",
        event_type="HIGH_DENSITY_CONGESTION",
        event_category="TRAFFIC_DENSITY",
        confidence=0.94,
        latitude=17.4180,
        longitude=78.4720,
        severity="HIGH",
        status="detected",
        image_path=None,
        video_timestamp=5.0,
        details={"vehicle_count": 42, "density_level": "HIGH", "avg_speed_kmh": 12.4},
        timestamp=datetime.now(timezone.utc),
        is_simulated=True,
    ),
}


def _db_event_to_response(e: Event) -> EventResponse:
    """Converts an SQLAlchemy Event model instance to an EventResponse schema."""
    lat, lon = lat_lon_from_point(e.location)
    meta = e.metadata_dict or {}
    return EventResponse(
        event_id=e.event_id,
        bus_id=e.bus_id,
        route_id=meta.get("route_id"),
        event_type=e.event_type,
        event_category=meta.get("event_category", "ROAD_DEFECT"),
        confidence=e.confidence,
        latitude=lat if lat is not None else 0.0,
        longitude=lon if lon is not None else 0.0,
        severity=e.severity.upper(),
        status=e.status,
        image_path=e.image_path,
        video_timestamp=e.video_timestamp,
        details=meta.get("details", {}),
        timestamp=e.timestamp,
        is_simulated=True,
        disclaimer=meta.get("disclaimer", "prototype heuristic estimation — rule-based detection, not forensic determination"),
    )


@router.post("", response_model=EventResponse, status_code=status.HTTP_201_CREATED, summary="Create/Ingest an urban sensing event")
async def create_event(payload: EventCreate, db: Session = Depends(get_db)):
    """Receives and persists a single urban sensing event, stores evidence image reference,
    and broadcasts the event immediately over WebSocket `/ws/events`.
    """
    event_id = payload.event_id or f"evt_{uuid.uuid4().hex[:12]}"
    ts = payload.timestamp or datetime.now(timezone.utc)

    # 1. Attempt PostgreSQL/PostGIS persistence
    if db is not None:
        try:
            # Ensure bus exists
            bus = db.query(Bus).filter_by(bus_id=payload.bus_id).first()
            if not bus:
                bus = Bus(
                    bus_id=payload.bus_id,
                    route_id=payload.route_id,
                    latitude=payload.latitude,
                    longitude=payload.longitude,
                    status="active",
                )
                db.add(bus)
                db.flush()

            evt = Event(
                event_id=event_id,
                bus_id=payload.bus_id,
                event_type=payload.event_type,
                confidence=payload.confidence,
                latitude=payload.latitude,
                longitude=payload.longitude,
                severity=payload.severity.lower(),
                status=payload.status,
                image_path=payload.image_path,
                video_timestamp=payload.video_timestamp,
                timestamp=ts,
                metadata={
                    "event_category": payload.event_category,
                    "route_id": payload.route_id,
                    "details": payload.details,
                    "is_simulated": True,
                },
            )
            db.add(evt)
            db.commit()
            db.refresh(evt)
            resp = _db_event_to_response(evt)
            _IN_MEMORY_EVENTS[event_id] = resp
        except Exception:
            if db:
                db.rollback()
            resp = EventResponse(
                event_id=event_id,
                bus_id=payload.bus_id,
                route_id=payload.route_id,
                event_type=payload.event_type,
                event_category=payload.event_category,
                confidence=payload.confidence,
                latitude=payload.latitude,
                longitude=payload.longitude,
                severity=payload.severity.upper(),
                status=payload.status,
                image_path=payload.image_path,
                video_timestamp=payload.video_timestamp,
                details=payload.details or {},
                timestamp=ts,
                is_simulated=True,
            )
            _IN_MEMORY_EVENTS[event_id] = resp
    else:
        resp = EventResponse(
            event_id=event_id,
            bus_id=payload.bus_id,
            route_id=payload.route_id,
            event_type=payload.event_type,
            event_category=payload.event_category,
            confidence=payload.confidence,
            latitude=payload.latitude,
            longitude=payload.longitude,
            severity=payload.severity.upper(),
            status=payload.status,
            image_path=payload.image_path,
            video_timestamp=payload.video_timestamp,
            details=payload.details or {},
            timestamp=ts,
            is_simulated=True,
        )
        _IN_MEMORY_EVENTS[event_id] = resp

    # 2. Broadcast event over WebSocket
    await manager.broadcast_events({
        "type": "event_created",
        "is_simulated": True,
        "event": resp.model_dump(mode="json"),
    })

    return resp


@router.get("", response_model=EventListResponse, summary="List urban sensing events with filtering")
def list_events(
    event_type: Optional[str] = Query(None, description="Filter by event type (e.g. POTHOLE, RASH_DRIVING)"),
    severity: Optional[str] = Query(None, description="Filter by severity (LOW, MEDIUM, HIGH, CRITICAL)"),
    bus_id: Optional[str] = Query(None, description="Filter by bus fleet identifier"),
    status_filter: Optional[str] = Query(None, alias="status", description="Filter by event status"),
    limit: int = Query(50, ge=1, le=500, description="Max records to return"),
    offset: int = Query(0, ge=0, description="Records offset for pagination"),
    db: Session = Depends(get_db),
):
    """Retrieves urban sensing events with support for multi-attribute filtering and pagination."""
    if db is not None:
        try:
            query = db.query(Event)
            if event_type:
                query = query.filter(Event.event_type.ilike(f"%{event_type}%"))
            if severity:
                query = query.filter(Event.severity.ilike(severity.lower()))
            if bus_id:
                query = query.filter(Event.bus_id == bus_id)
            if status_filter:
                query = query.filter(Event.status.ilike(status_filter))

            total = query.count()
            records = query.order_by(desc(Event.timestamp)).offset(offset).limit(limit).all()

            events_list = [_db_event_to_response(r) for r in records]
            return EventListResponse(
                total=total,
                count=len(events_list),
                limit=limit,
                offset=offset,
                events=events_list,
                is_simulated=True,
            )
        except Exception:
            pass

    # In-memory fallback query
    filtered = list(_IN_MEMORY_EVENTS.values())
    if event_type:
        filtered = [e for e in filtered if event_type.lower() in e.event_type.lower()]
    if severity:
        filtered = [e for e in filtered if e.severity.lower() == severity.lower()]
    if bus_id:
        filtered = [e for e in filtered if e.bus_id == bus_id]
    if status_filter:
        filtered = [e for e in filtered if e.status.lower() == status_filter.lower()]

    total = len(filtered)
    paged = filtered[offset : offset + limit]

    return EventListResponse(
        total=total,
        count=len(paged),
        limit=limit,
        offset=offset,
        events=paged,
        is_simulated=True,
    )


@router.get("/{event_id}", response_model=EventResponse, summary="Get single urban sensing event")
def get_event_by_id(event_id: str, db: Session = Depends(get_db)):
    """Retrieves full details for a single urban event by its unique ID. Returns 404 if not found."""
    if db is not None:
        try:
            evt = db.query(Event).filter(Event.event_id == event_id).first()
            if evt:
                return _db_event_to_response(evt)
        except Exception:
            pass

    if event_id in _IN_MEMORY_EVENTS:
        return _IN_MEMORY_EVENTS[event_id]

    raise HTTPException(
        status_code=status.HTTP_404_NOT_FOUND,
        detail=f"Event with ID '{event_id}' not found.",
    )


@router.patch("/{event_id}/status", response_model=EventResponse, summary="Update event/incident lifecycle status")
async def update_event_status(event_id: str, payload: EventStatusUpdate, db: Session = Depends(get_db)):
    """Updates the lifecycle status of an event/incident (NEW, UNDER_REVIEW, RESOLVED, FALSE_POSITIVE).
    Persists change to PostgreSQL/PostGIS database and broadcasts real-time update via WebSockets.
    """
    valid_statuses = {"NEW", "UNDER_REVIEW", "RESOLVED", "FALSE_POSITIVE", "DETECTED", "VERIFIED", "DISMISSED"}
    normalized_status = payload.status.strip().upper()
    if normalized_status not in valid_statuses:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"Invalid status '{payload.status}'. Must be one of: NEW, UNDER_REVIEW, RESOLVED, FALSE_POSITIVE.",
        )

    updated_resp: Optional[EventResponse] = None

    # 1. Update DB if available
    if db is not None:
        try:
            evt = db.query(Event).filter(Event.event_id == event_id).first()
            if evt:
                evt.status = normalized_status
                db.commit()
                db.refresh(evt)
                updated_resp = _db_event_to_response(evt)
        except Exception:
            if db:
                db.rollback()

    # 2. Update memory store
    if event_id in _IN_MEMORY_EVENTS:
        existing = _IN_MEMORY_EVENTS[event_id]
        updated_dict = existing.model_dump()
        updated_dict["status"] = normalized_status
        updated_resp = EventResponse(**updated_dict)
        _IN_MEMORY_EVENTS[event_id] = updated_resp

    if not updated_resp:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Event with ID '{event_id}' not found.",
        )

    # 3. Broadcast status update over WebSocket
    await manager.broadcast_events({
        "type": "event_status_updated",
        "event_id": event_id,
        "status": normalized_status,
        "event": updated_resp.model_dump(mode="json"),
    })

    return updated_resp


@router.get("/{event_id}/pdf", summary="Export Single Incident Dossier PDF")
def export_single_incident_pdf(event_id: str, db: Session = Depends(get_db)):
    """Generates and downloads a Single Incident Dossier PDF with clear ground-truth vs AI demarcation."""
    evt_resp: Optional[EventResponse] = None
    if db is not None:
        try:
            evt = db.query(Event).filter(Event.event_id == event_id).first()
            if evt:
                evt_resp = _db_event_to_response(evt)
        except Exception:
            pass

    if not evt_resp and event_id in _IN_MEMORY_EVENTS:
        evt_resp = _IN_MEMORY_EVENTS[event_id]

    if not evt_resp:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Event with ID '{event_id}' not found for report generation.",
        )

    pdf_bytes = generate_single_incident_pdf(evt_resp)
    filename = f"CitySense_Incident_{event_id}.pdf"
    
    return Response(
        content=pdf_bytes,
        media_type="application/pdf",
        headers={
            "Content-Disposition": f'inline; filename="{filename}"',
            "Cache-Control": "no-cache",
        },
    )
