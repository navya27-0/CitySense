"""Unit and schema tests for BusSense-AI PostgreSQL + PostGIS models and spatial utilities (Hyderabad Region)."""

import pytest
from datetime import datetime, timezone
from backend.models import (
    Route,
    Bus,
    Event,
    VehicleDetection,
    TrafficMeasurement,
    RouteTrip,
    point_from_lat_lon,
    lat_lon_from_point,
)
from geoalchemy2.elements import WKTElement


def test_spatial_utilities():
    """Test WKT Point creation and coordinate extraction."""
    lat, lon = 17.3850, 78.4860
    point = point_from_lat_lon(latitude=lat, longitude=lon)
    assert isinstance(point, WKTElement)
    assert point.srid == 4326

    extracted_lat, extracted_lon = lat_lon_from_point(point)
    assert extracted_lat == pytest.approx(lat, abs=1e-4)
    assert extracted_lon == pytest.approx(lon, abs=1e-4)


def test_route_model_instantiation():
    """Test Route model instantiation."""
    route = Route(
        route_id="216",
        route_name="Mehdipatnam to Hitec City",
        start_location="Mehdipatnam Terminal",
        destination="Cyber Towers / Hitec City",
    )
    assert route.route_id == "216"
    assert route.route_name == "Mehdipatnam to Hitec City"


def test_bus_model_instantiation():
    """Test Bus model with PostGIS geometry coordinates."""
    bus = Bus(
        bus_id="BUS_101",
        route_id="216",
        latitude=17.3916,
        longitude=78.4350,
        speed=35.5,
        heading=115.0,
        status="active",
    )
    assert bus.bus_id == "BUS_101"
    assert bus.latitude == pytest.approx(17.3916, abs=1e-4)
    assert bus.longitude == pytest.approx(78.4350, abs=1e-4)
    assert bus.speed == 35.5
    assert bus.heading == 115.0
    assert bus.status == "active"


def test_event_model_instantiation():
    """Test Event model with PostGIS coordinates, severity, and metadata."""
    event = Event(
        event_id="evt-1001",
        bus_id="BUS_101",
        event_type="pothole",
        confidence=0.92,
        latitude=17.3920,
        longitude=78.4340,
        severity="high",
        status="detected",
        video_timestamp=14.5,
        metadata={"depth_est_cm": 8.5, "bbox": [100, 150, 200, 250]},
    )
    assert event.event_id == "evt-1001"
    assert event.event_type == "pothole"
    assert event.confidence == 0.92
    assert event.latitude == pytest.approx(17.3920, abs=1e-4)
    assert event.longitude == pytest.approx(78.4340, abs=1e-4)
    assert event.severity == "high"
    assert event.event_metadata["depth_est_cm"] == 8.5


def test_vehicle_detection_model():
    """Test VehicleDetection model instantiation."""
    vd = VehicleDetection(
        detection_id="det-5001",
        event_id="evt-1001",
        vehicle_type="car",
        tracking_id=42,
        confidence=0.88,
        registration_number="TS09AB1234",
        registration_confidence=0.95,
    )
    assert vd.vehicle_type == "car"
    assert vd.tracking_id == 42
    assert vd.registration_number == "TS09AB1234"


def test_traffic_measurement_model():
    """Test TrafficMeasurement model and auto-sum total vehicle calculation."""
    tm = TrafficMeasurement(
        bus_id="BUS_101",
        latitude=17.3916,
        longitude=78.4350,
        car_count=10,
        bus_count=2,
        truck_count=1,
        motorcycle_count=5,
        traffic_density="high",
    )
    assert tm.total_vehicle_count == 18
    assert tm.traffic_density == "high"
    assert tm.latitude == pytest.approx(17.3916, abs=1e-4)


def test_route_trip_model():
    """Test RouteTrip model and delay calculation."""
    trip = RouteTrip(
        trip_id="trip-9001",
        bus_id="BUS_101",
        route_id="216",
        expected_duration=45.0,
        actual_duration=55.0,
    )
    trip.calculate_delay()
    assert trip.delay_minutes == 10.0
