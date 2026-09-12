"""Application configuration module for BusSense-AI.

Loads environment variables dynamically using pathlib for cross-platform compatibility.
"""

from pathlib import Path
from typing import Optional
from pydantic_settings import BaseSettings, SettingsConfigDict

# Base directory paths (dynamically resolved to project root)
BASE_DIR = Path(__file__).resolve().parent.parent


class Settings(BaseSettings):
    # Application configuration
    APP_NAME: str = "BusSense-AI"
    APP_ENV: str = "development"
    DEBUG: bool = True
    HOST: str = "127.0.0.1"
    PORT: int = 8000

    # Database configuration (PostgreSQL + PostGIS)
    DB_HOST: str = "127.0.0.1"
    DB_PORT: int = 5432
    DB_USER: str = "postgres"
    DB_PASSWORD: str = "postgres"
    DB_NAME: str = "bussense_db"
    DATABASE_URL: Optional[str] = None

    # WebSocket configuration
    WS_HEARTBEAT_INTERVAL: int = 30

    # Project directories
    DATA_DIR: Path = BASE_DIR / "data"
    VIDEOS_DIR: Path = BASE_DIR / "data" / "videos"
    GPS_DIR: Path = BASE_DIR / "data" / "gps"
    MOCK_DIR: Path = BASE_DIR / "data" / "mock"
    OUTPUT_DIR: Path = BASE_DIR / "data" / "outputs"
    EVENTS_OUTPUT_DIR: Path = BASE_DIR / "data" / "outputs" / "events"
    MODELS_DIR: Path = BASE_DIR / "models"

    model_config = SettingsConfigDict(
        env_file=str(BASE_DIR / ".env"),
        env_file_encoding="utf-8",
        extra="ignore",
    )

    def get_database_url(self) -> str:
        if self.DATABASE_URL:
            return self.DATABASE_URL
        return f"postgresql+psycopg2://{self.DB_USER}:{self.DB_PASSWORD}@{self.DB_HOST}:{self.DB_PORT}/{self.DB_NAME}"


settings = Settings()
