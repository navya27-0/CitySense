"""Tests for Urban Analytics REST endpoints and delay calculations."""

import pytest
from datetime import datetime, timezone, timedelta
from unittest.mock import MagicMock
from fastapi.testclient import TestClient

from backend.main import app
from backend.database import get_db
from backend.models import (
    Bus,
    Route,
    RouteTrip,
    TrafficMeasurement,
    Event,
)


@pytest.fixture
def mock_db_with_data():
    """Returns a mock SQLAlchemy session populated with realistic fixtures."""
    now = datetime.now(timezone.utc)

    # 1. Routes
    r1 = Route(route_id="216", route_name="Route 216: Secunderabad - Mehdipatnam")
    r2 = Route(route_id="10", route_name="Route 10: Secunderabad - Charminar")

    # 2. Buses
    b1 = Bus(bus_id="BUS_101", route_id="216", latitude=17.3850, longitude=78.4867, speed=35.0, heading=180, status="active", last_seen=now)
    b2 = Bus(bus_id="BUS_102", route_id="10", latitude=17.4340, longitude=78.5015, speed=25.0, heading=90, status="active", last_seen=now)

    # 3. Route Trips: delay = actual_duration - expected_duration
    # Trip 1: Expected 40m, Actual 48m -> Delay = +8m
    t1 = RouteTrip(
        trip_id="TRIP_001",
        bus_id="BUS_101",
        route_id="216",
        start_time=now - timedelta(hours=2),
        expected_duration=40.0,
        actual_duration=48.0,
        delay_minutes=8.0,
    )
    # Trip 2: Expected 30m, Actual 28m -> Delay = -2m
    t2 = RouteTrip(
        trip_id="TRIP_002",
        bus_id="BUS_102",
        route_id="10",
        start_time=now - timedelta(hours=1),
        expected_duration=30.0,
        actual_duration=28.0,
        delay_minutes=-2.0,
    )

    # 4. Traffic Measurements
    tm1 = TrafficMeasurement(
        measurement_id="TM_001",
        bus_id="BUS_101",
        latitude=17.4440,
        longitude=78.3810,
        timestamp=now - timedelta(minutes=45),
        car_count=30,
        bus_count=5,
        truck_count=3,
        motorcycle_count=12,
        total_vehicle_count=50,
        traffic_density="high",
    )
    tm2 = TrafficMeasurement(
        measurement_id="TM_002",
        bus_id="BUS_102",
        latitude=17.4340,
        longitude=78.5015,
        timestamp=now - timedelta(minutes=20),
        car_count=15,
        bus_count=2,
        truck_count=1,
        motorcycle_count=7,
        total_vehicle_count=25,
        traffic_density="low",
    )

    # 5. Events (Road defects & incidents)
    e1 = Event(
        event_id="EVT_001",
        bus_id="BUS_101",
        event_type="POTHOLE",
        confidence=0.95,
        latitude=17.3862,
        longitude=78.4855,
        timestamp=now - timedelta(minutes=30),
        severity="critical",
        status="detected",
    )
    e1.bus = b1
    e2 = Event(
        event_id="EVT_002",
        bus_id="BUS_101",
        event_type="WATERLOGGING",
        confidence=0.88,
        latitude=17.3910,
        longitude=78.4820,
        timestamp=now - timedelta(minutes=25),
        severity="medium",
        status="detected",
    )
    e2.bus = b1
    e3 = Event(
        event_id="EVT_003",
        bus_id="BUS_102",
        event_type="RASH_DRIVING",
        confidence=0.92,
        latitude=17.4350,
        longitude=78.5020,
        timestamp=now - timedelta(minutes=15),
        severity="critical",
        status="detected",
    )
    e3.bus = b2

    # Link relationships on buses
    b1.trips = [t1]
    b1.events = [e1, e2]
    b1.traffic_measurements = [tm1]

    b2.trips = [t2]
    b2.events = [e3]
    b2.traffic_measurements = [tm2]

    # Mock Session with query dispatching
    mock_session = MagicMock()

    def mock_query(model):
        query_mock = MagicMock()
        query_mock.filter.return_value = query_mock
        query_mock.order_by.return_value = query_mock
        query_mock.limit.return_value = query_mock

        if model == TrafficMeasurement:
            query_mock.all.return_value = [tm1, tm2]
            query_mock.count.return_value = 2
        elif model == Event:
            query_mock.all.return_value = [e1, e2, e3]
            query_mock.count.return_value = 3
        elif model == RouteTrip:
            query_mock.all.return_value = [t1, t2]
            query_mock.count.return_value = 2
        elif model == Bus:
            query_mock.all.return_value = [b1, b2]
            query_mock.count.return_value = 2
        elif model == Route:
            query_mock.all.return_value = [r1, r2]
            query_mock.count.return_value = 2
        else:
            query_mock.all.return_value = []
            query_mock.count.return_value = 0
        return query_mock

    mock_session.query.side_effect = mock_query
    return mock_session


@pytest.fixture
def mock_db_empty():
    """Returns a mock SQLAlchemy session representing an empty database."""
    mock_session = MagicMock()
    query_mock = MagicMock()
    query_mock.filter.return_value = query_mock
    query_mock.order_by.return_value = query_mock
    query_mock.all.return_value = []
    query_mock.count.return_value = 0
    mock_session.query.return_value = query_mock
    return mock_session


# ==============================================================================
# TESTS FOR URBAN ANALYTICS
# ==============================================================================

def test_analytics_summary_endpoint(mock_db_with_data):
    """Verifies top-level KPI summary calculations."""
    app.dependency_overrides[get_db] = lambda: mock_db_with_data
    client = TestClient(app)
    try:
        resp = client.get("/api/analytics/summary")
        assert resp.status_code == 200
        data = resp.json()
        assert data["meta"]["has_data"] is True
        assert data["total_vehicles_counted"] == 75  # 50 + 25
        assert data["active_fleet_buses"] == 2
        assert data["total_events_detected"] == 3
        assert data["road_defects_count"] == 2  # Pothole + Waterlogging
        assert data["safety_incidents_count"] == 1  # Rash driving
        assert data["active_congestion_hotspots"] == 1  # TM_001 with 'high' density
    finally:
        app.dependency_overrides.clear()


def test_vehicle_counts_analytics(mock_db_with_data):
    """Verifies vehicle classification aggregations."""
    app.dependency_overrides[get_db] = lambda: mock_db_with_data
    client = TestClient(app)
    try:
        resp = client.get("/api/analytics/vehicle-counts")
        assert resp.status_code == 200
        data = resp.json()
        assert data["meta"]["has_data"] is True
        assert data["total_count"] == 75
        categories = {c["category"]: c["count"] for c in data["by_category"]}
        assert categories["Cars"] == 45
        assert categories["Buses"] == 7
        assert categories["Trucks"] == 4
        assert categories["Motorcycles"] == 19
        assert len(data["timeline"]) == 2
    finally:
        app.dependency_overrides.clear()


def test_traffic_density_distribution(mock_db_with_data):
    """Verifies traffic density level groupings."""
    app.dependency_overrides[get_db] = lambda: mock_db_with_data
    client = TestClient(app)
    try:
        resp = client.get("/api/analytics/traffic-density")
        assert resp.status_code == 200
        data = resp.json()
        assert data["meta"]["has_data"] is True
        assert data["total_measurements"] == 2
        dist = {d["density_level"]: d["sample_count"] for d in data["distribution"]}
        assert dist["HIGH"] == 1
        assert dist["LOW"] == 1
    finally:
        app.dependency_overrides.clear()


def test_congestion_hotspots_endpoint(mock_db_with_data):
    """Verifies congestion hotspots ranking."""
    app.dependency_overrides[get_db] = lambda: mock_db_with_data
    client = TestClient(app)
    try:
        resp = client.get("/api/analytics/congestion-hotspots")
        assert resp.status_code == 200
        data = resp.json()
        assert data["meta"]["has_data"] is True
        assert len(data["hotspots"]) >= 1
        top = data["hotspots"][0]
        assert top["density_level"] == "HIGH"
        assert top["observed_vehicles"] == 50
    finally:
        app.dependency_overrides.clear()


def test_events_by_type_endpoint(mock_db_with_data):
    """Verifies events by type distribution."""
    app.dependency_overrides[get_db] = lambda: mock_db_with_data
    client = TestClient(app)
    try:
        resp = client.get("/api/analytics/events-by-type")
        assert resp.status_code == 200
        data = resp.json()
        assert data["meta"]["has_data"] is True
        assert data["total_events"] == 3
        types = {t["event_type"]: t["count"] for t in data["types"]}
        assert types["POTHOLE"] == 1
        assert types["WATERLOGGING"] == 1
        assert types["RASH_DRIVING"] == 1
    finally:
        app.dependency_overrides.clear()


def test_events_by_location_endpoint(mock_db_with_data):
    """Verifies events grouped by transit route corridors."""
    app.dependency_overrides[get_db] = lambda: mock_db_with_data
    client = TestClient(app)
    try:
        resp = client.get("/api/analytics/events-by-location")
        assert resp.status_code == 200
        data = resp.json()
        assert data["meta"]["has_data"] is True
        assert data["total_events"] == 3
        assert len(data["locations"]) >= 1
    finally:
        app.dependency_overrides.clear()


def test_events_by_time_endpoint(mock_db_with_data):
    """Verifies events timeline time-series."""
    app.dependency_overrides[get_db] = lambda: mock_db_with_data
    client = TestClient(app)
    try:
        resp = client.get("/api/analytics/events-by-time")
        assert resp.status_code == 200
        data = resp.json()
        assert data["meta"]["has_data"] is True
        assert len(data["timeline"]) >= 1
    finally:
        app.dependency_overrides.clear()


def test_route_delays_calculation_formula(mock_db_with_data):
    """Strictly verifies calculation: delay = actual_duration - expected_duration."""
    app.dependency_overrides[get_db] = lambda: mock_db_with_data
    client = TestClient(app)
    try:
        resp = client.get("/api/analytics/route-delays")
        assert resp.status_code == 200
        data = resp.json()
        assert data["meta"]["has_data"] is True
        assert data["formula"] == "delay = actual_duration - expected_duration"
        routes = {r["route_id"]: r for r in data["routes"]}
        
        # Route 216: 48 - 40 = 8.0 delay
        assert "216" in routes
        assert routes["216"]["avg_delay_minutes"] == 8.0
        assert routes["216"]["avg_expected_duration_min"] == 40.0
        assert routes["216"]["avg_actual_duration_min"] == 48.0

        # Route 10: 28 - 30 = -2.0 delay (on-time)
        assert "10" in routes
        assert routes["10"]["avg_delay_minutes"] == -2.0
        assert routes["10"]["on_time_trips"] == 1
    finally:
        app.dependency_overrides.clear()


def test_bus_activity_endpoint(mock_db_with_data):
    """Verifies bus productivity metrics."""
    app.dependency_overrides[get_db] = lambda: mock_db_with_data
    client = TestClient(app)
    try:
        resp = client.get("/api/analytics/bus-activity")
        assert resp.status_code == 200
        data = resp.json()
        assert data["meta"]["has_data"] is True
        assert data["total_buses"] == 2
        fleet = {b["bus_id"]: b for b in data["fleet"]}
        assert fleet["BUS_101"]["trips_completed"] == 1
        assert fleet["BUS_101"]["total_events_logged"] == 2
    finally:
        app.dependency_overrides.clear()


def test_road_defects_frequency_by_subtype(mock_db_with_data):
    """Verifies defect counts mapped across official BEL subtypes."""
    app.dependency_overrides[get_db] = lambda: mock_db_with_data
    client = TestClient(app)
    try:
        resp = client.get("/api/analytics/road-defects-frequency")
        assert resp.status_code == 200
        data = resp.json()
        assert data["meta"]["has_data"] is True
        assert data["total_defects"] == 2  # Pothole + Waterlogging
        subtypes = {s["subtype"]: s for s in data["subtypes"]}
        assert subtypes["POTHOLE"]["count"] == 1
        assert subtypes["POTHOLE"]["critical_count"] == 1
        assert subtypes["WATERLOGGING"]["count"] == 1
    finally:
        app.dependency_overrides.clear()


def test_insufficient_data_empty_database(mock_db_empty):
    """Verifies that empty database queries return has_data=False and 'Insufficient data' rather than error."""
    app.dependency_overrides[get_db] = lambda: mock_db_empty
    client = TestClient(app)
    try:
        resp = client.get("/api/analytics/summary")
        assert resp.status_code == 200
        data = resp.json()
        assert data["meta"]["has_data"] is False
        assert "Insufficient data" in data["meta"]["message"]

        resp = client.get("/api/analytics/route-delays")
        assert resp.status_code == 200
        assert resp.json()["meta"]["has_data"] is False
        assert "Insufficient data" in resp.json()["meta"]["message"]
    finally:
        app.dependency_overrides.clear()


def test_od_matrix_endpoint_success(mock_db_with_data):
    """Verifies GET /api/analytics/od-matrix returns structured OD pairs, summary, and non-passenger disclaimer."""
    app.dependency_overrides[get_db] = lambda: mock_db_with_data
    client = TestClient(app)
    try:
        resp = client.get("/api/analytics/od-matrix")
        assert resp.status_code == 200
        data = resp.json()
        assert data["meta"]["has_data"] is True
        
        # Verify Summary & Disclaimer
        summary = data["summary"]
        assert summary["total_od_pairs"] > 0
        assert summary["total_trips_analyzed"] > 0
        assert "NOT passenger-level" in summary["disclaimer"]
        assert "inferred" in summary["disclaimer"].lower()

        # Verify OD Pairs
        assert len(data["od_pairs"]) > 0
        first_pair = data["od_pairs"][0]
        assert "origin_stop" in first_pair
        assert "destination_stop" in first_pair
        assert first_pair["trip_count"] >= 1
        assert first_pair["avg_duration_minutes"] > 0
        assert first_pair["avg_speed_kmh"] > 0
        assert first_pair["distance_km"] > 0
        assert len(first_pair["buses_observed"]) > 0

        # Verify Matrix Grid & Stops by Route
        assert "216" in data["stops_by_route"]
        assert isinstance(data["matrix_grid"], dict)
        assert len(data["matrix_grid"]) > 0
    finally:
        app.dependency_overrides.clear()


def test_od_matrix_route_filtering(mock_db_with_data):
    """Verifies route-specific filtering on OD matrix."""
    app.dependency_overrides[get_db] = lambda: mock_db_with_data
    client = TestClient(app)
    try:
        resp = client.get("/api/analytics/od-matrix?route_id=216")
        assert resp.status_code == 200
        data = resp.json()
        assert data["meta"]["has_data"] is True
        assert len(data["od_pairs"]) > 0
        for p in data["od_pairs"]:
            assert p["route_id"] == "216"
    finally:
        app.dependency_overrides.clear()


