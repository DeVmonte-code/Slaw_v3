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
    # Cosine-similarity floor for retrieved Qdrant chunks. Anything below is
    # dropped before reaching the verifier, which then short-circuits to
    # supports=false without spending a Claude call.
    score_threshold: float = 0.55

    log_level: str = "INFO"
    cors_allow_origins: str = ""
    frontend_origin: str = ""
    app_env: str = "development"

    def cors_origins_list(self) -> list[str]:
        raw = self.cors_allow_origins or self.frontend_origin
        if not raw.strip():
            return []
        return [o.strip() for o in raw.split(",") if o.strip()]

    def is_production(self) -> bool:
        return self.app_env.lower() in {"production", "prod"}


settings = Settings()
