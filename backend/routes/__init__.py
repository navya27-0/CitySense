"""API routes package unifying all BusSense-AI REST endpoints."""

from fastapi import APIRouter
from backend.routes.health import router as health_router
from backend.routes.telemetry import router as telemetry_router
from backend.routes.events import router as events_router
from backend.routes.buses import router as buses_router
from backend.routes.traffic import router as traffic_router
from backend.routes.video_processing import router as video_processing_router
from backend.routes.analytics import router as analytics_router
from backend.routes.reports import router as reports_router
from backend.routes.edge_metrics import router as edge_metrics_router

api_router = APIRouter(prefix="/api")

# Register route modules
api_router.include_router(health_router, prefix="/health", tags=["Health"])
api_router.include_router(events_router, prefix="/events", tags=["Events"])
api_router.include_router(telemetry_router, prefix="/telemetry", tags=["Telemetry"])
api_router.include_router(buses_router, prefix="/buses", tags=["Buses"])
api_router.include_router(traffic_router, tags=["Traffic & Heatmap"])
api_router.include_router(video_processing_router, tags=["Video Processing"])
api_router.include_router(analytics_router, tags=["Urban Analytics"])
api_router.include_router(reports_router, tags=["Incident Reports & PDF Export"])
api_router.include_router(edge_metrics_router, prefix="/edge-metrics", tags=["Edge Processing Metrics"])

__all__ = ["api_router"]
