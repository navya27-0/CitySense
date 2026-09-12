"""Database session management and PostGIS configuration for BusSense-AI."""

from typing import Generator, Dict, Any
from sqlalchemy import create_engine, text
from sqlalchemy.orm import declarative_base, sessionmaker
from backend.config import settings

DATABASE_URL = settings.get_database_url()

# Database engine configuration with connection pooling, fast timeout, and pre-ping
engine = create_engine(
    DATABASE_URL,
    echo=settings.DEBUG,
    pool_pre_ping=True,
    pool_size=10,
    max_overflow=20,
    connect_args={"connect_timeout": 2},
)

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()

import time

_LAST_DB_CHECK_TIME = 0.0
_DB_IS_AVAILABLE = False
_DB_CHECK_TTL = 5.0  # seconds


def is_db_available() -> bool:
    """Checks and caches whether PostgreSQL database is reachable."""
    global _LAST_DB_CHECK_TIME, _DB_IS_AVAILABLE
    now = time.time()
    if now - _LAST_DB_CHECK_TIME < _DB_CHECK_TTL:
        return _DB_IS_AVAILABLE

    _LAST_DB_CHECK_TIME = now
    try:
        with engine.connect() as conn:
            conn.execute(text("SELECT 1"))
        _DB_IS_AVAILABLE = True
    except Exception:
        _DB_IS_AVAILABLE = False
    return _DB_IS_AVAILABLE


def get_db() -> Generator:
    """FastAPI dependency for yielding database sessions with immediate offline fallback."""
    if not is_db_available():
        yield None
        return

    db = None
    try:
        db = SessionLocal()
        yield db
    except Exception:
        yield None
    finally:
        if db is not None:
            try:
                db.close()
            except Exception:
                pass


def check_db_connection() -> Dict[str, Any]:
    """Tests active connectivity to PostgreSQL and checks PostGIS extension version.
    
    Returns:
        dict: Diagnostic details containing connectivity status, PostGIS version, and error message if any.
    """
    result = {
        "connected": False,
        "database_name": settings.DB_NAME,
        "host": settings.DB_HOST,
        "port": settings.DB_PORT,
        "postgis_installed": False,
        "postgis_version": None,
        "error": None,
    }

    try:
        with engine.connect() as conn:
            # 1. Test basic connectivity
            conn.execute(text("SELECT 1"))
            result["connected"] = True

            # 2. Test PostGIS extension
            try:
                postgis_query = conn.execute(text("SELECT PostGIS_Full_Version()")).scalar()
                result["postgis_installed"] = True
                result["postgis_version"] = postgis_query
            except Exception as pg_err:
                result["postgis_installed"] = False
                result["postgis_error"] = str(pg_err)
    except Exception as e:
        result["connected"] = False
        result["error"] = str(e)

    return result


def init_db():
    """Idempotently initializes database extension and creates all model tables."""
    with engine.connect() as conn:
        conn.execute(text("CREATE EXTENSION IF NOT EXISTS postgis;"))
        conn.commit()

    # Import models to ensure all metadata is registered
    import backend.models  # noqa: F401
    Base.metadata.create_all(bind=engine)
