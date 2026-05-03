from __future__ import annotations

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    anthropic_api_key: str = ""
    claude_model: str = "claude-sonnet-4-6"
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
    # When True, the nightly schedule will fetch new data from Fedlex
    # and then promote it. Disabled by default.
    fedlex_refresh_enabled: bool = False
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

    # ----- Agent-backed audit (Task #25) ---------------------------------
    # Shared-secret gate on ``GET /admin/audits/agent-backed``. When set,
    # the endpoint requires ``X-Admin-Token`` to match. When unset, the
    # endpoint is open in non-production environments and 403's in
    # production so a deploy can never accidentally publish an open
    # audit endpoint.
    admin_audit_token: str = ""

    # ----- Managed Agents (Task #26) -------------------------------------
    # When True, every ``_call_claude`` call site (engine.verify and
    # api.chat) routes through ``engine.agent_runner.run_session`` instead
    # of ``messages.create``. The runner opens a managed-agents session,
    # streams events, and returns the same ``(text, AgentProvenance)``
    # tuple the messages.create path returns — but with
    # ``call_kind='sessions.events'`` and the tool/MCP traces populated so
    # the Task #25 audit flips to ``agent_backed=True``.
    #
    # Defaulted ON (Task #37) so production deploys cannot silently fall
    # back to ``messages.create``. Misconfigured deploys (missing IDs,
    # missing MCP URLs) crash on startup via the strict validation in
    # ``api.main.lifespan`` rather than degrading to zero-result scans.
    # Local dev / CI / unit tests set ``USE_MANAGED_AGENTS=0`` to opt
    # out (the test conftest does this for the whole offline suite).
    use_managed_agents: bool = True
    # Persisted IDs from the one-shot bootstrap. The bootstrap script
    # writes them back to the .env on success; the runner refuses to
    # start a session when ``use_managed_agents=True`` and any of these
    # are empty (fail loudly, not silently).
    managed_agent_id: str = ""
    managed_agent_version: int = 0
    managed_environment_id: str = ""
    managed_vault_id: str = ""
    # HTTPS URLs for the three MCP servers the agent registers.
    # Empty values are tolerated only for read-only deployments that
    # explicitly don't need a given server (the bootstrap script will
    # skip the corresponding ``mcp_toolset`` entry).
    mcp_swiss_law_url: str = ""
    mcp_contract_tools_url: str = ""
    mcp_user_context_url: str = ""
    # Single-base override for the co-hosted MCP deployment (Task #31).
    # When set and a per-server URL above is empty, it is auto-derived
    # to ``{mcp_base_url}/mcp/<server>/`` — the path that
    # ``api.main`` mounts each ``FastMCP`` under. Lets a single
    # ``MCP_BASE_URL=https://swiss-legal.example.app`` env var wire all
    # three servers without enumerating each URL.
    mcp_base_url: str = ""
    # Anthropic Managed Agents beta header value. Centralised so a future
    # GA bump only changes one constant.
    managed_agents_beta: str = "managed-agents-2026-04-01"
    # Anthropic API base URL — overridable in tests.
    anthropic_api_base: str = "https://api.anthropic.com"
    # Per-session wall-clock cap. Managed-agents sessions are bounded by
    # the agent's tool budget too, but we add a client-side timeout so
    # one stuck session can't block a /scan request indefinitely.
    managed_session_timeout_s: float = 180.0

    def model_post_init(self, __context: object) -> None:
        # Derive per-server MCP URLs from a single base, when given.
        # Per-server overrides win — a deploy that points one server
        # at a separate host (e.g. user_context running in a different
        # region for data residency) can do so without losing the
        # base-URL convenience for the other two.
        base = self.mcp_base_url.rstrip("/")
        if base:
            if not self.mcp_swiss_law_url:
                self.mcp_swiss_law_url = f"{base}/mcp/swiss-law/"
            if not self.mcp_contract_tools_url:
                self.mcp_contract_tools_url = f"{base}/mcp/contract-tools/"
            if not self.mcp_user_context_url:
                self.mcp_user_context_url = f"{base}/mcp/user-context/"

    def cors_origins_list(self) -> list[str]:
        raw = self.cors_allow_origins or self.frontend_origin
        if not raw.strip():
            return []
        return [o.strip() for o in raw.split(",") if o.strip()]

    def is_production(self) -> bool:
        return self.app_env.lower() in {"production", "prod"}


settings = Settings()
