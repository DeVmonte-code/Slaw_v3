from __future__ import annotations

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    anthropic_api_key: str = ""
    claude_model: str = "claude-opus-4-7"
    qdrant_url: str = ""
    qdrant_api_key: str = ""
    qdrant_collection: str = "swiss_law"
    embedding_model: str = "intfloat/multilingual-e5-small"
    scan_concurrency: int = 3


settings = Settings()
