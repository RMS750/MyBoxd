from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path


def _load_env() -> None:
    for path in (Path.cwd() / ".env", Path.cwd().parent / ".env"):
        if not path.exists():
            continue
        for raw in path.read_text(encoding="utf-8").splitlines():
            line = raw.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, value = line.split("=", 1)
            os.environ.setdefault(key.strip(), value.strip().strip('"').strip("'"))


def _bool(name: str, default: bool = False) -> bool:
    value = os.getenv(name)
    if value is None:
        return default
    return value.strip().casefold() in {"1", "true", "yes", "on"}


def _database_url(value: str) -> str:
    # Render/older providers may still hand out postgres:// URLs. SQLAlchemy 2 +
    # psycopg 3 works reliably with the explicit driver form below.
    if value.startswith("postgres://"):
        value = "postgresql+psycopg://" + value[len("postgres://") :]
    elif value.startswith("postgresql://") and "+" not in value.split("://", 1)[0]:
        value = "postgresql+psycopg://" + value[len("postgresql://") :]
    return value


def _origins() -> tuple[str, ...]:
    raw = os.getenv("FRONTEND_URL", os.getenv("FRONTEND_ORIGIN", "http://localhost:5173"))
    values = [x.strip().rstrip("/") for x in raw.split(",") if x.strip()]
    for local in ("http://localhost:5173", "http://127.0.0.1:5173"):
        if local not in values and os.getenv("ENVIRONMENT", "development") != "production":
            values.append(local)
    return tuple(values)


_load_env()


@dataclass(frozen=True)
class Settings:
    app_name: str = "MyBoxd"
    environment: str = os.getenv("ENVIRONMENT", "development").casefold()
    database_url: str = _database_url(os.getenv("DATABASE_URL", "sqlite:///./myboxd.db"))
    frontend_origins: tuple[str, ...] = _origins()
    tmdb_api_key: str = os.getenv("TMDB_API_KEY", "")
    tmdb_enrich_limit: int = int(os.getenv("TMDB_ENRICH_LIMIT", "120"))
    candidate_enrich_limit: int = int(os.getenv("CANDIDATE_ENRICH_LIMIT", "96"))
    max_upload_mb: int = int(os.getenv("MAX_UPLOAD_MB", "25"))
    session_days: int = int(os.getenv("SESSION_DAYS", "30"))
    cookie_name: str = os.getenv("SESSION_COOKIE_NAME", "myboxd_session")
    auto_create_schema: bool = _bool("AUTO_CREATE_SCHEMA", os.getenv("ENVIRONMENT", "development").casefold() != "production")

    @property
    def production(self) -> bool:
        return self.environment == "production"

    @property
    def cookie_secure(self) -> bool:
        return self.production

    @property
    def cookie_samesite(self) -> str:
        # The public deployment serves frontend + API from one origin, so Lax is
        # sufficient and avoids reliance on third-party cookie behavior.
        return "lax"


settings = Settings()
