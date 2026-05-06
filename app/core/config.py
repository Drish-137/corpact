from functools import lru_cache
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    # App
    app_env: str = "development"
    log_level: str = "INFO"
    api_secret_key: str = "change-me"

    # Database
    db_host: str = "localhost"
    db_port: int = 5432
    db_name: str = "corpact"
    db_user: str = "corpact"
    db_password: str = "changeme"

    # AWS
    aws_region: str = "us-east-1"
    sqs_queue_url: str = ""
    s3_raw_bucket: str = "corpact-raw-events"
    aws_endpoint_url: str | None = None  # set for localstack in dev

    # Data sources
    alpha_vantage_api_key: str = ""

    @property
    def db_url(self) -> str:
        return (
            f"postgresql+asyncpg://{self.db_user}:{self.db_password}"
            f"@{self.db_host}:{self.db_port}/{self.db_name}"
        )

    @property
    def is_production(self) -> bool:
        return self.app_env == "production"


@lru_cache
def get_settings() -> Settings:
    return Settings()
