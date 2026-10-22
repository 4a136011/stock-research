"""環境變數設定。密鑰一律使用 SecretStr，避免被 repr / 日誌洩漏。"""

from functools import lru_cache
from typing import Literal

from pydantic import SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore", env_ignore_empty=True)

    app_env: Literal["development", "test", "production"] = "development"
    log_level: str = "INFO"
    cors_origins: str = "http://localhost:3000"

    database_url: SecretStr | None = None
    supabase_url: str | None = None
    supabase_service_role_key: SecretStr | None = None

    llm_provider: str = "mock"
    llm_model: str | None = None
    llm_api_key: SecretStr | None = None
    llm_max_tokens: int = 2000
    llm_daily_call_limit: int = 50

    @property
    def cors_origin_list(self) -> list[str]:
        return [o.strip() for o in self.cors_origins.split(",") if o.strip()]


@lru_cache
def get_settings() -> Settings:
    return Settings()
