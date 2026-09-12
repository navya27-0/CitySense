"""REST endpoints for PDF incident reports and executive audits in CitySense."""

from datetime import datetime, timezone
from typing import Optional, List
from fastapi import APIRouter, Depends, HTTPException, Query, Response, status
from sqlalchemy.orm import Session
from sqlalchemy import desc

from backend.database import get_db
from backend.models import Event
from backend.routes.events import _IN_MEMORY_EVENTS, _db_event_to_response
from backend.schemas.event import EventResponse
from backend.services.pdf_report import generate_single_incident_pdf, generate_batch_incidents_pdf

router = APIRouter(prefix="/reports", tags=["Incident Reports & PDF Export"])


@router.get("/incidents/{event_id}/pdf", summary="Export Single Incident Dossier PDF")
def get_incident_pdf(event_id: str, db: Session = Depends(get_db)):
    """Generates and serves a Single Incident Dossier PDF with ground-truth vs. AI demarcation."""
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
            detail=f"Incident event '{event_id}' not found.",
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


@router.get("/incidents/pdf", summary="Export Batch/Summary Incident Audit PDF")
@router.get("/incidents/batch-pdf", summary="Export Batch Incident Audit PDF (Alias)")
def get_batch_incidents_pdf(
    status_filter: Optional[str] = Query(None, alias="status", description="Filter by status: NEW, UNDER_REVIEW, RESOLVED, FALSE_POSITIVE"),
    severity: Optional[str] = Query(None, description="Filter by severity: LOW, MEDIUM, HIGH, CRITICAL"),
    bus_id: Optional[str] = Query(None, description="Filter by bus fleet identifier"),
    route_id: Optional[str] = Query(None, description="Filter by transit route ID"),
    db: Session = Depends(get_db),
):
    """Generates and serves an Executive Incident Audit & Triage Summary PDF.
    Filters by status, severity, bus, or route as requested.
    """
    incident_events: List[EventResponse] = []

    if db is not None:
        try:
            query = db.query(Event).filter(
                (Event.event_type.ilike("%RASH%")) | 
                (Event.event_type.ilike("%HIT%")) | 
                (Event.event_type.ilike("%INCIDENT%"))
            )
            if status_filter:
                query = query.filter(Event.status.ilike(status_filter))
            if severity:
                query = query.filter(Event.severity.ilike(severity))
            if bus_id:
                query = query.filter(Event.bus_id == bus_id)

            records = query.order_by(desc(Event.timestamp)).limit(100).all()
            for r in records:
                resp = _db_event_to_response(r)
                if route_id and resp.route_id != route_id:
                    continue
                incident_events.append(resp)
        except Exception:
            pass

    if not incident_events:
        # Filter in-memory events
        for e in _IN_MEMORY_EVENTS.values():
            cat = (e.event_category or "").upper()
            etype = (e.event_type or "").upper()
            if cat == "TRAFFIC_INCIDENT" or "RASH" in etype or "HIT" in etype:
                if status_filter and e.status.upper() != status_filter.upper():
                    continue
                if severity and e.severity.upper() != severity.upper():
                    continue
                if bus_id and e.bus_id != bus_id:
                    continue
                if route_id and (e.route_id or "216") != route_id:
                    continue
                incident_events.append(e)

    if not incident_events:
        # If no incidents matching filter, include fallback sample incident
        incident_events = [
            EventResponse(
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
                details={"registration_number": "TS09EA1234", "ocr_confidence": 0.94, "kinematic_trigger": "High-speed slalom weaving (280 norm-px/s)"},
                timestamp=datetime.now(timezone.utc),
                is_simulated=True,
            )
        ]

    pdf_bytes = generate_batch_incidents_pdf(incident_events)
    filename = f"CitySense_Incident_Audit_Summary_{datetime.now(timezone.utc).strftime('%Y%m%d')}.pdf"

    return Response(
        content=pdf_bytes,
        media_type="application/pdf",
        headers={
            "Content-Disposition": f'inline; filename="{filename}"',
            "Cache-Control": "no-cache",
        },
    )
