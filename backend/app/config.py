from functools import lru_cache

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    app_name: str = "SuperAgent Sentinel API"
    app_env: str = "development"
    debug: bool = False

    database_url: str = (
        "postgresql+asyncpg://superagent:superagent@127.0.0.1:5432/superagent"
    )
    redis_url: str = "redis://127.0.0.1:6379/0"
    analysis_queue: str = "superagent:analysis:queue"
    job_ttl_seconds: int = Field(default=86400, ge=300, le=604800)

    cors_origins: str = (
        "http://localhost:5173,"
        "http://127.0.0.1:5173,"
        "http://localhost:8080"
    )
    analysis_stage_delay_ms: int = Field(default=140, ge=0, le=3000)

    openai_enabled: bool = False
    openai_api_key: str | None = None
    openai_model: str | None = None

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    @property
    def cors_origin_list(self) -> list[str]:
        return [
            value.strip()
            for value in self.cors_origins.split(",")
            if value.strip()
        ]


@lru_cache
def get_settings() -> Settings:
    return Settings()
