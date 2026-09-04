from functools import lru_cache
from pathlib import Path

from dotenv import load_dotenv
from pydantic_settings import BaseSettings, SettingsConfigDict


PROJECT_ROOT = Path(__file__).resolve().parents[1]
load_dotenv(PROJECT_ROOT / ".env")


class Settings(BaseSettings):
    app_name: str = "Ekmind AI Content Studio"
    app_env: str = "development"
    database_url: str = "sqlite:///./storage/ekmind.db"
    openai_api_key: str | None = None
    openai_model: str = "gpt-4.1-mini"
    langsmith_api_key: str | None = None
    langsmith_project: str = "ekmind-ai-content-studio"
    langsmith_tracing: bool = False
    langsmith_workspace_id: str | None = None
    langsmith_endpoint: str = "https://api.smith.langchain.com"
    langsmith_dataset: str = "ekmind-approved-content"
    search_provider: str | None = None
    search_api_key: str | None = None
    avatar_provider: str = "mock"
    voice_provider: str = "mock"
    heygen_api_key: str | None = None
    heygen_avatar_id: str | None = None
    heygen_voice_id: str | None = None
    heygen_api_base: str = "https://api.heygen.com"
    youtube_client_id: str | None = None
    youtube_client_secret: str | None = None
    youtube_refresh_token: str | None = None
    max_revisions: int = 2
    quality_threshold: float = 8.0
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    @property
    def demo_mode(self) -> bool:
        return not bool(self.openai_api_key)

    @property
    def project_root(self) -> Path:
        return PROJECT_ROOT

    @property
    def youtube_configured(self) -> bool:
        return all((self.youtube_client_id, self.youtube_client_secret, self.youtube_refresh_token))


@lru_cache
def get_settings() -> Settings:
    return Settings()
