"""Unit and integration tests for Incident Reporting, Status Lifecycle, and PDF Generation."""

import pytest
from fastapi.testclient import TestClient
from backend.main import app
from backend.services.pdf_report import generate_single_incident_pdf, generate_batch_incidents_pdf


@pytest.fixture
def client():
    """TestClient fixture with proper lifespan management."""
    with TestClient(app) as c:
        yield c


def test_status_update_lifecycle(client):
    """Verify PATCH /api/events/{event_id}/status transitions through lifecycle statuses."""
    # 1. Create a test incident
    create_res = client.post("/api/events", json={
        "bus_id": "BUS_101",
        "route_id": "216",
        "event_type": "RASH_DRIVING",
        "event_category": "TRAFFIC_INCIDENT",
        "confidence": 0.92,
        "latitude": 17.4050,
        "longitude": 78.4550,
        "severity": "CRITICAL",
        "status": "NEW",
        "details": {
            "registration_number": "TS09EA1234",
            "ocr_confidence": 0.95,
            "kinematic_trigger": "High-speed slalom weaving (280 norm-px/s)",
        },
    })
    assert create_res.status_code == 201
    evt_id = create_res.json()["event_id"]
    assert create_res.json()["status"] == "NEW"

    # 2. Transition to UNDER_REVIEW
    res_review = client.patch(f"/api/events/{evt_id}/status", json={"status": "UNDER_REVIEW"})
    assert res_review.status_code == 200
    assert res_review.json()["status"] == "UNDER_REVIEW"

    # Verify retrieval reflects new status
    get_res = client.get(f"/api/events/{evt_id}")
    assert get_res.status_code == 200
    assert get_res.json()["status"] == "UNDER_REVIEW"

    # 3. Transition to RESOLVED
    res_resolved = client.patch(f"/api/events/{evt_id}/status", json={"status": "RESOLVED"})
    assert res_resolved.status_code == 200
    assert res_resolved.json()["status"] == "RESOLVED"

    # 4. Transition to FALSE_POSITIVE
    res_fp = client.patch(f"/api/events/{evt_id}/status", json={"status": "FALSE_POSITIVE"})
    assert res_fp.status_code == 200
    assert res_fp.json()["status"] == "FALSE_POSITIVE"

    # 5. Transition back to NEW
    res_new = client.patch(f"/api/events/{evt_id}/status", json={"status": "NEW"})
    assert res_new.status_code == 200
    assert res_new.json()["status"] == "NEW"


def test_status_update_validation_errors(client):
    """Verify invalid status inputs return 422 Unprocessable Entity."""
    res_invalid = client.patch("/api/events/defect_001/status", json={"status": "INVALID_CUSTOM_STATUS"})
    assert res_invalid.status_code == 422
    assert "must be one of" in res_invalid.json()["detail"].lower()

    # Non-existent event returns 404
    res_notfound = client.patch("/api/events/non_existent_event_999999/status", json={"status": "RESOLVED"})
    assert res_notfound.status_code == 404


def test_single_incident_pdf_export_endpoint(client):
    """Verify GET /api/reports/incidents/{event_id}/pdf and /api/events/{event_id}/pdf return valid PDF bytes."""
    # Seed incident
    create_res = client.post("/api/events", json={
        "bus_id": "BUS_102",
        "route_id": "100",
        "event_type": "SUSPECTED_HIT_AND_RUN",
        "event_category": "TRAFFIC_INCIDENT",
        "confidence": 0.88,
        "latitude": 17.4290,
        "longitude": 78.4950,
        "severity": "CRITICAL",
        "status": "NEW",
        "details": {
            "registration_number": "TS07UK9876",
            "ocr_confidence": 0.91,
            "kinematic_trigger": "Collision proximity overlap followed by acceleration flight surge",
        },
    })
    evt_id = create_res.json()["event_id"]

    # Endpoint 1: /api/reports/incidents/{event_id}/pdf
    res1 = client.get(f"/api/reports/incidents/{evt_id}/pdf")
    assert res1.status_code == 200
    assert res1.headers["content-type"] == "application/pdf"
    assert "attachment" in res1.headers["content-disposition"] or "inline" in res1.headers["content-disposition"]
    assert res1.content.startswith(b"%PDF-")
    assert len(res1.content) > 1000

    # Endpoint 2: /api/events/{event_id}/pdf
    res2 = client.get(f"/api/events/{evt_id}/pdf")
    assert res2.status_code == 200
    assert res2.headers["content-type"] == "application/pdf"
    assert res2.content.startswith(b"%PDF-")
    assert len(res2.content) > 1000

    # Non-existent event returns 404
    bad_res = client.get("/api/reports/incidents/non_existent_id_404/pdf")
    assert bad_res.status_code == 404


def test_batch_incidents_pdf_export_endpoint(client):
    """Verify GET /api/reports/incidents/batch-pdf returns a valid summary PDF."""
    res = client.get("/api/reports/incidents/batch-pdf")
    assert res.status_code == 200
    assert res.headers["content-type"] == "application/pdf"
    assert res.content.startswith(b"%PDF-")
    assert len(res.content) > 1000

    # Test with query filters
    res_filtered = client.get("/api/reports/incidents/batch-pdf?status=NEW&severity=CRITICAL")
    assert res_filtered.status_code == 200
    assert res_filtered.headers["content-type"] == "application/pdf"
    assert res_filtered.content.startswith(b"%PDF-")


def test_pdf_report_service_direct():
    """Directly tests generate_single_incident_pdf and generate_batch_incidents_pdf methods."""
    sample_incident = {
        "event_id": "INC-TEST-001",
        "bus_id": "BUS_101",
        "route_id": "216",
        "event_type": "RASH_DRIVING",
        "event_category": "TRAFFIC_INCIDENT",
        "confidence": 0.94,
        "latitude": 17.3850,
        "longitude": 78.4866,
        "severity": "CRITICAL",
        "status": "UNDER_REVIEW",
        "video_timestamp": 3.2,
        "details": {
            "registration_number": "TS09EA1234",
            "ocr_confidence": 0.96,
            "kinematic_trigger": "High-speed slalom weaving (280 norm-px/s)",
        },
    }

    # Test single incident generation
    single_pdf = generate_single_incident_pdf(sample_incident)
    assert isinstance(single_pdf, bytes)
    assert single_pdf.startswith(b"%PDF-")
    assert len(single_pdf) > 2000

    # Test batch summary generation
    batch_pdf = generate_batch_incidents_pdf([sample_incident, {**sample_incident, "event_id": "INC-TEST-002"}])
    assert isinstance(batch_pdf, bytes)
    assert batch_pdf.startswith(b"%PDF-")
    assert len(batch_pdf) > 2000
