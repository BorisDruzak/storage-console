from pydantic import Field, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file='.env', extra='ignore')

    database_url: str = 'postgresql+psycopg://storage_console@postgres/storage_console'
    app_env: str = 'development'
    sentry_dsn: str = ''
    app_release: str = '0.1.0'
    worker_interval_seconds: int = Field(default=5, ge=1)
    worker_stale_seconds: int = Field(default=30, ge=2)

    @model_validator(mode='after')
    def validate_worker_window(self) -> 'Settings':
        if self.worker_interval_seconds >= self.worker_stale_seconds:
            raise ValueError('Worker interval must be shorter than the freshness window')
        return self
