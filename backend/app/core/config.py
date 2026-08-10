from functools import lru_cache

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    app_name: str = "CyberLab API"
    environment: str = "development"
    api_secret_key: str = "change-me-in-production"
    # Disabled by default: CyberLab binds to 127.0.0.1 only out of the box, so
    # there's no untrusted network path to the API. Set AUTH_ENABLED=true
    # (and a real API_SECRET_KEY) before exposing it beyond localhost — see
    # docs/security.md.
    auth_enabled: bool = False

    postgres_host: str = "cyberlab-postgres"
    postgres_port: int = 5432
    postgres_db: str = "cyberlab"
    postgres_user: str = "cyberlab"
    postgres_password: str = "cyberlab"

    redis_url: str = "redis://cyberlab-redis:6379/0"

    ollama_url: str = "http://host.docker.internal:11434"
    ollama_model: str = "qwen2.5-coder:3b"

    cors_origins_raw: str = Field(default="http://localhost:3300", validation_alias="CORS_ORIGINS")

    kali_agent_url: str = "http://cyberlab-kali:9000"
    kali_agent_token: str = "change-me-in-production"

    labmanager_url: str = "http://cyberlab-labmanager:9100"
    labmanager_token: str = "change-me-in-production"

    @property
    def cors_origins(self) -> list[str]:
        return [origin.strip() for origin in self.cors_origins_raw.split(",") if origin.strip()]

    @property
    def database_url(self) -> str:
        return (
            f"postgresql+asyncpg://{self.postgres_user}:{self.postgres_password}"
            f"@{self.postgres_host}:{self.postgres_port}/{self.postgres_db}"
        )

    @property
    def sync_database_url(self) -> str:
        return (
            f"postgresql+psycopg2://{self.postgres_user}:{self.postgres_password}"
            f"@{self.postgres_host}:{self.postgres_port}/{self.postgres_db}"
        )


@lru_cache
def get_settings() -> Settings:
    return Settings()
