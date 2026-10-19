"""Runtime settings (environment variables with the DEFLOCK_ prefix)."""

from __future__ import annotations

from pathlib import Path

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="DEFLOCK_", extra="ignore")

    app_env: str = Field(default="development", description="development | test | production")
    project_root: Path = Field(default=Path("/app"), description="Directory holding configs/ and data/boundaries/")
    region_config: Path = Path("configs/regions/colorado.yaml")  # the Denver pilot config stays available via DEFLOCK_REGION_CONFIG
    providers_config: Path = Path("configs/providers.yaml")
    route_profiles_config: Path = Path("configs/route_profiles.yaml")
    data_quality_config: Path = Path("configs/data_quality.yaml")
    privacy_config: Path = Path("configs/privacy.yaml")

    database_url: str | None = Field(default=None, description="SQLAlchemy URL, e.g. postgresql+psycopg://user:pw@db:5432/deflock")
    valhalla_url: str = "http://valhalla:8002"
    geocoder_url: str | None = Field(default=None, description="Base URL of the approved self-hosted geocoder; None = not configured")
    overpass_url: str = "https://overpass-api.de/api/interpreter"
    user_agent: str = "DeFlockMigration/1.0.0rc1 (local pilot; fixed-region camera sync)"
    snapshot_dir: Path = Path("/var/lib/deflock/snapshots")

    log_level: str = "INFO"
    cors_origins: list[str] = Field(default_factory=list)
    router_connect_timeout_seconds: float = 2.0
    router_read_timeout_seconds: float = 10.0
    geocoder_timeout_seconds: float = 15.0  # a self-hosted Nominatim answers in well under a second once warm, but the first searches after a restart can take several seconds
    plan_deadline_seconds: float = 20.0
    cameras_max_bbox_degrees: float = Field(default=0.6, description="Maximum width/height of a camera viewport query")

    @field_validator("app_env")
    @classmethod
    def _check_env(cls, value: str) -> str:
        if value not in {"development", "test", "production"}:
            raise ValueError("DEFLOCK_APP_ENV must be development, test, or production")
        return value

    @field_validator("log_level")
    @classmethod
    def _check_level(cls, value: str) -> str:
        if value.upper() not in {"DEBUG", "INFO", "WARNING", "ERROR"}:
            raise ValueError("DEFLOCK_LOG_LEVEL must be DEBUG, INFO, WARNING, or ERROR")
        return value.upper()

    def resolve(self, path: Path) -> Path:
        return path if path.is_absolute() else self.project_root / path
