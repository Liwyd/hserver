from functools import lru_cache

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # Database
    database_username: str = Field(alias="DATABASE_USERNAME")
    database_password: str = Field(alias="DATABASE_PASSWORD")
    database_name: str = Field(alias="DATABASE_NAME")
    database_host: str = Field(default="localhost", alias="DATABASE_HOST")
    database_port: int = Field(default=5432, alias="DATABASE_PORT")

    # PostgreSQL Container
    postgres_db: str = Field(alias="POSTGRES_DB")
    postgres_user: str = Field(alias="POSTGRES_USER")
    postgres_password: str = Field(alias="POSTGRES_PASSWORD")
    pgport: int = Field(default=5432, alias="PGPORT")

    # Telegram Bot
    telegram_api_token: str = Field(alias="TELEGRAM_API_TOKEN")
    telegram_admins_id: str = Field(alias="TELEGRAM_ADMINS_ID")

    # Encryption
    encryption_key: str = Field(alias="ENCRYPTION_KEY")

    # Traffic Monitor
    traffic_monitor_enabled: bool = Field(default=False, alias="TRAFFIC_MONITOR_ENABLED")
    traffic_monitor_alert_percent: int = Field(default=80, alias="TRAFFIC_MONITOR_ALERT_PERCENT")
    traffic_monitor_interval_minutes: int = Field(default=15, alias="TRAFFIC_MONITOR_INTERVAL_MINUTES")

    # Rate Limiting
    hetzner_max_requests_per_second: float = Field(default=1.0, alias="HETZNER_MAX_REQUESTS_PER_SECOND")
    hetzner_rate_limit_buffer: int = Field(default=5, alias="HETZNER_RATE_LIMIT_BUFFER")

    @property
    def admin_ids(self) -> list[int]:
        return [int(x.strip()) for x in self.telegram_admins_id.split(",") if x.strip()]

    @property
    def database_url(self) -> str:
        return (
            f"postgresql+asyncpg://{self.database_username}:{self.database_password}"
            f"@{self.database_host}:{self.database_port}/{self.database_name}"
        )

    @property
    def postgres_container_url(self) -> str:
        return (
            f"postgresql+asyncpg://{self.postgres_user}:{self.postgres_password}"
            f"@{self.database_host}:{self.pgport}/{self.postgres_db}"
        )


@lru_cache
def get_settings() -> Settings:
    return Settings()
