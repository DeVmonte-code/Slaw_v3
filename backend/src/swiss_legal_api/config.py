from __future__ import annotations

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    anthropic_api_key: str = ""
    claude_model: str = "claude-opus-4-7"
    qdrant_url: str = ""
    qdrant_api_key: str = ""
    qdrant_collection: str = "swiss_law"
    # Second Qdrant collection holding doctrinal context (CO 1-183 + Luis's
    # specialized PDFs). Treated as advisory-only at retrieval time — never
    # cited as primary authority. Configurable so that staging clusters can
    # use a parallel collection name without colliding with production.
    curriculum_collection: str = "co_curriculum"
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

    # ----- Scheduled benefit sweep (Task #22) -----------------------------
    # Single-process APScheduler started in the FastAPI lifespan when
    # ``sweep_enabled`` is true. Off by default so test/dev runs don't
    # spawn a background thread silently.
    sweep_enabled: bool = False
    # Cron HOUR for the nightly sweep, in the server's local timezone.
    # Decoupled from minute=0 so two clusters in the same region can
    # stagger by a few minutes without colliding on Fedlex / Anthropic.
    sweep_cron_hour: int = 3
    sweep_cron_minute: int = 17
    # Per-user retention. ``run_benefit_scan`` snapshots are not free
    # (each carries a full BenefitReport JSON) so we cap history per
    # user — diff only ever compares to the latest, older rows are
    # historical telemetry.
    sweep_retention_per_user: int = 30
    # SQLite path for the persistent layer. Override to ``:memory:``
    # in tests; production uses a file under ``backend/data/``.
    sweep_db_path: str = "data/sweep.db"
    # Path to the *previous* Fedlex snapshot. The sweep diffs the
    # current ``seed/law_articles.fedlex.json`` against this file to
    # build the changed-eli_uri set. After a successful sweep the
    # current snapshot is copied into this slot so the next run picks
    # up only deltas. Configurable so tests can use a tmpdir.
    fedlex_previous_snapshot_path: str = "data/law_articles.fedlex.previous.json"

    def cors_origins_list(self) -> list[str]:
        raw = self.cors_allow_origins or self.frontend_origin
        if not raw.strip():
            return []
        return [o.strip() for o in raw.split(",") if o.strip()]

    def is_production(self) -> bool:
        return self.app_env.lower() in {"production", "prod"}


settings = Settings()
