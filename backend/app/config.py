from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    database_url: str = "postgresql+asyncpg://nurses:nurses@localhost:5432/nurses"
    redis_url: str = "redis://localhost:6379/0"
    bot_token: str = ""
    admin_telegram_ids: str = ""  # comma-separated
    init_data_max_age_seconds: int = 86400

    s3_endpoint: str = ""
    s3_bucket: str = "nurses"
    s3_access_key: str = ""
    s3_secret_key: str = ""

    stt_provider: str = "stub"
    llm_provider: str = "stub"
    tts_provider: str = "stub"

    @property
    def admin_ids(self) -> set[int]:
        return {int(x) for x in self.admin_telegram_ids.split(",") if x.strip()}


@lru_cache
def get_settings() -> Settings:
    return Settings()
