from functools import lru_cache

from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    database_url: str = "postgresql+asyncpg://nurses:nurses@localhost:5432/nurses"
    redis_url: str = "redis://localhost:6379/0"
    bot_token: str = ""
    admin_telegram_ids: str = ""  # comma-separated
    init_data_max_age_seconds: int = 86400
    admin_session_ttl_seconds: int = 7 * 86400  # browser admin login lifetime
    cors_origins: str = ""  # comma-separated frontend origins

    s3_endpoint: str = ""
    s3_bucket: str = "nurses"
    s3_access_key: str = ""
    s3_secret_key: str = ""

    stt_provider: str = "stub"
    llm_provider: str = "stub"
    tts_provider: str = "stub"

    @field_validator("database_url")
    @classmethod
    def _asyncpg_scheme(cls, v: str) -> str:
        # Railway/Heroku-style URLs use postgres:// or postgresql://; SQLAlchemy async needs asyncpg.
        for prefix in ("postgres://", "postgresql://"):
            if v.startswith(prefix):
                return "postgresql+asyncpg://" + v[len(prefix):]
        return v

    @property
    def cors_origin_list(self) -> list[str]:
        return [x.strip() for x in self.cors_origins.split(",") if x.strip()]

    @property
    def admin_ids(self) -> set[int]:
        return {int(x) for x in self.admin_telegram_ids.split(",") if x.strip()}


@lru_cache
def get_settings() -> Settings:
    return Settings()
