import os
from functools import lru_cache


def _normalize_database_url(url: str) -> str:
    """Railway/Render provide postgres:// or postgresql://; SQLAlchemy needs +psycopg."""
    if url.startswith("postgres://"):
        return "postgresql+psycopg://" + url[len("postgres://") :]
    if url.startswith("postgresql://"):
        return "postgresql+psycopg://" + url[len("postgresql://") :]
    return url


class Settings:
    """Env-driven settings. DATA_SOURCE_MODE=mock (default) uses bundled fixtures;
    DATA_SOURCE_MODE=live makes real HTTP calls where a connector supports it."""

    database_url: str = _normalize_database_url(
        os.getenv(
            "DATABASE_URL", "postgresql+psycopg://investdash:investdash@db:5432/investdash"
        )
    )
    data_source_mode: str = os.getenv("DATA_SOURCE_MODE", "mock")  # mock | live
    fred_api_key: str | None = os.getenv("FRED_API_KEY")
    sec_user_agent: str = os.getenv("SEC_USER_AGENT", "InvestDash research contact@example.com")
    cors_origins: list[str] = os.getenv("CORS_ORIGINS", "http://localhost:3000").split(",")
    algorithm_version: str = "v1"

    jwt_secret_key: str = os.getenv("JWT_SECRET_KEY", "dev-insecure-change-me")
    jwt_algorithm: str = "HS256"
    access_token_expire_minutes: int = int(os.getenv("ACCESS_TOKEN_EXPIRE_MINUTES", str(60 * 24 * 7)))
    initial_admin_username: str = os.getenv("INITIAL_ADMIN_USERNAME", "admin")
    initial_admin_password: str = os.getenv("INITIAL_ADMIN_PASSWORD", "")


@lru_cache
def get_settings() -> Settings:
    return Settings()
