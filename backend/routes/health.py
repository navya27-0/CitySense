"""Health check endpoints for system diagnostics and database connectivity verification."""

from fastapi import APIRouter, Response, status
from backend.config import settings
from backend.database import check_db_connection

router = APIRouter()


@router.get("")
def health_check(response: Response):
    """System and database connectivity health check endpoint.
    
    Performs live queries to PostgreSQL and PostGIS to verify database health.
    Returns HTTP 200 if healthy, or HTTP 503 if database connectivity fails.
    """
    db_status = check_db_connection()

    if not db_status["connected"]:
        response.status_code = status.HTTP_503_SERVICE_UNAVAILABLE
        return {
            "status": "unhealthy",
            "app_name": settings.APP_NAME,
            "environment": settings.APP_ENV,
            "database": {
                "status": "disconnected",
                "host": db_status["host"],
                "port": db_status["port"],
                "database": db_status["database_name"],
                "error": db_status["error"],
            },
            "postgis": {
                "installed": False,
            },
        }

    return {
        "status": "healthy",
        "app_name": settings.APP_NAME,
        "environment": settings.APP_ENV,
        "database": {
            "status": "connected",
            "host": db_status["host"],
            "port": db_status["port"],
            "database": db_status["database_name"],
        },
        "postgis": {
            "installed": db_status["postgis_installed"],
            "version": db_status["postgis_version"],
        },
        "mode": "prototype_simulation",
    }
