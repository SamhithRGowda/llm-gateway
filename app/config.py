"""Application settings, loaded from environment variables / .env.

Only the settings needed through Phase 1 (DB connectivity) are actively used
right now. The remaining fields exist so the same .env file stays valid across
later phases without needing to be rewritten.
"""
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    # Database (Phase 1)
    database_url: str = "postgresql+asyncpg://gateway:gateway@db:5432/gateway"

    # Redis (provisioned in Phase 0, unused by app code until Phase 5)
    redis_url: str = "redis://redis:6379/0"

    # Provider keys (unused until Phase 2)
    openai_api_key: str = ""
    groq_api_key: str = ""

    # Reliability / rate-limit knobs (unused until later phases)
    default_rate_limit_per_min: int = 60
    circuit_breaker_failure_threshold: int = 5
    circuit_breaker_cooldown_seconds: int = 30
    retry_max_attempts: int = 3

    log_level: str = "INFO"


settings = Settings()
