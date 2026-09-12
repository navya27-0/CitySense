"""Unit and integration tests for frontend dashboard serving and static assets."""

import pytest
from fastapi.testclient import TestClient
from backend.main import app

client = TestClient(app)


def test_root_serves_dashboard_html():
    """Verify GET / returns 200 OK with HTML content."""
    res = client.get("/")
    assert res.status_code == 200
    assert "text/html" in res.headers.get("content-type", "")
    assert "CitySense" in res.text
    assert "city-gis-map" in res.text


def test_dashboard_route_serves_html():
    """Verify GET /dashboard returns 200 OK with HTML content."""
    res = client.get("/dashboard")
    assert res.status_code == 200
    assert "text/html" in res.headers.get("content-type", "")
    assert "CitySense" in res.text


def test_frontend_css_and_js_static_assets():
    """Verify CSS and JS static assets are accessible."""
    css_res = client.get("/css/style.css")
    assert css_res.status_code == 200

    leaflet_css_res = client.get("/css/leaflet-custom.css")
    assert leaflet_css_res.status_code == 200
    assert "marker-cluster" in leaflet_css_res.text
    assert "marker-defect-pothole" in leaflet_css_res.text
    assert "marker-defect-waterlogging" in leaflet_css_res.text

    js_app_res = client.get("/js/app.js")
    assert js_app_res.status_code == 200
    assert "CitySenseApplication" in js_app_res.text
    assert "onGisFilterChange" in js_app_res.text

    js_map_res = client.get("/js/map.js")
    assert js_map_res.status_code == 200
    assert "GisMapEngine" in js_map_res.text
    assert "TRANSIT_ROUTES" in js_map_res.text
    assert "updateHeatmap" in js_map_res.text
    assert "renderRoadConditionLayer" in js_map_res.text
    assert "applyFilters" in js_map_res.text


def test_gis_filter_elements_in_html():
    """Verify HTML template contains GIS filter toolbar and layer switchers."""
    res = client.get("/")
    assert res.status_code == 200
    assert "gis-filter-event-type" in res.text
    assert "gis-filter-severity" in res.text
    assert "layer-toggle-heatmap" in res.text
    assert "layer-toggle-routes" in res.text
    assert "layer-toggle-condition" in res.text


def test_heatmap_api_endpoint_integration():
    """Verify /api/heatmap returns point data for the Leaflet heat layer."""
    res = client.get("/api/heatmap?category=TRAFFIC")
    assert res.status_code == 200
    data = res.json()
    assert "points" in data
    assert "total_points" in data
    assert len(data["points"]) > 0
    pt = data["points"][0]
    assert "latitude" in pt
    assert "longitude" in pt
    assert "weight" in pt


def test_api_info_endpoint():
    """Verify GET /api-info returns JSON metadata."""
    res = client.get("/api-info")
    assert res.status_code == 200
    data = res.json()
    assert data["project"] == "BusSense-AI"
    assert "websockets" in data


def test_urban_analytics_elements_in_html():
    """Verify HTML template contains all 9 analytics chart canvases and time filter bar."""
    res = client.get("/")
    assert res.status_code == 200
    assert "chart-vehicle-counts" in res.text
    assert "chart-traffic-density" in res.text
    assert "chart-congestion-hotspots" in res.text
    assert "chart-events-by-type" in res.text
    assert "chart-events-by-location" in res.text
    assert "chart-events-by-time" in res.text
    assert "chart-route-delays" in res.text
    assert "chart-bus-activity" in res.text
    assert "chart-road-defects-frequency" in res.text
    assert "analytics-time-filters" in res.text
    assert "kpi-total-vehicles" in res.text


def test_table_sorting_and_focus_map_in_html():
    """Verify sortable table headers and Focus on Map action in HTML."""
    res = client.get("/")
    assert res.status_code == 200
    assert "sortFleetTable" in res.text
    assert "sortTrafficTable" in res.text
    assert "focusSelectedBusOnMap" in res.text


def test_od_matrix_elements_in_html():
    """Verify HTML template contains OD Matrix elements, disclaimer notice, and controls."""
    res = client.get("/")
    assert res.status_code == 200
    assert "od-matrix-card" in res.text
    assert "od-filter-route" in res.text
    assert "od-matrix-heatmap-grid" in res.text
    assert "od-segments-table-body" in res.text
    assert "od-total-pairs" in res.text
    assert "od-total-trips" in res.text
    assert "NOT passenger-level" in res.text
    assert "btn-toggle-od-grid" in res.text
    assert "exportODMatrix" in res.text


def test_edge_metrics_dashboard_cards_in_html():
    """Verify the Edge Processing Efficiency panel is present on the dashboard."""
    res = client.get("/")
    assert res.status_code == 200
    assert "edge-metrics-panel" in res.text
    assert "edge-frames-processed" in res.text
    assert "edge-events-generated" in res.text
    assert "edge-raw-size" in res.text
    assert "edge-transmitted-size" in res.text
    assert "edge-bandwidth-pct" in res.text
    assert "BANDWIDTH OPTIMIZED" in res.text
    assert "not a generalized industry claim" in res.text


def test_architecture_view_elements_in_html():
    """Verify the Edge Architecture view and its key sections exist in the HTML."""
    res = client.get("/")
    assert res.status_code == 200
    assert 'id="view-architecture"' in res.text
    assert 'data-view="view-architecture"' in res.text
    assert "Edge AI Processing Architecture" in res.text
    assert "arch-compare-before" in res.text
    assert "arch-compare-after" in res.text
    assert "arch-pipeline-flow" in res.text
    assert "arch-payload-json" in res.text
    assert "arch-disclaimer-banner" in res.text
    assert "evidence_image_ref" in res.text
    assert "Prototype Measurement Disclaimer" in res.text
    assert "arch-reduction" in res.text
