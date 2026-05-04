from __future__ import annotations

import asyncio
import json as _json
import logging
import sys
import time
from collections.abc import AsyncIterator
from contextlib import AsyncExitStack, asynccontextmanager, suppress
from urllib.parse import urlparse

import httpx
from fastapi import FastAPI, Header, HTTPException, Query, Request
from fastapi import Path as PathParam
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

from .. import scheduler as sweep_scheduler
from .. import storage
from ..audits import agent_backed_summary
from ..catalog import load_catalog
from ..config import settings
from ..engine.retrieval import _client as qdrant_client
from ..engine.scan import run_benefit_scan
from ..mcp_servers import build_fastmcp
from ..mcp_servers import contract_tools as _ct_server
from ..mcp_servers import swiss_law as _sl_server
from ..mcp_servers import user_context as _uc_server
from ..schemas import (
    AgentProvenance,
    Alert,
    BenefitReport,
    ContextProfile,
    UserProfileUpsert,
    UserRecord,
)
from ..seeding.embedder import get_embedder
from .chat import UnknownBenefitError, answer_follow_up

logging.basicConfig(
    level=getattr(logging, settings.log_level.upper(), logging.INFO),
    format=(
        '{"ts":"%(asctime)s","lvl":"%(levelname)s",'
        '"logger":"%(name)s","msg":"%(message)s"}'
    ),
    stream=sys.stdout,
)
logger = logging.getLogger(__name__)


def _probe_primary_collection(
    known_collection_names: set[str] | None = None,
) -> tuple[str, int | None]:
    """Inspect the configured primary scan collection.

    Returns one of:
      - ``("ok", n)``       when the collection exists and has ``n > 0`` points
      - ``("missing", None)`` when the collection is absent on the cluster
      - ``("empty", 0)``    when the collection exists but holds zero points

    Raises whatever the Qdrant SDK raises if the cluster itself is
    unreachable — the caller decides whether that's a 503 or just a log
    line. Kept module-level so both the lifespan and ``/readyz?deep=1``
    share one source of truth for "is the corpus actually here?".

    ``known_collection_names`` lets callers that have *just* called
    ``get_collections()`` themselves (the ``/readyz`` handler does, to
    convert an unreachable cluster into 503) reuse that result and skip
    a second round-trip. When ``None``, this helper makes the call
    itself.
    """
    client = qdrant_client()
    if known_collection_names is None:
        cols_resp = client.get_collections()
        names = {c.name for c in cols_resp.collections}
    else:
        names = known_collection_names
    if settings.qdrant_collection not in names:
        return ("missing", None)
    # exact=True is fine: 36-article corpus on a single shard. The whole
    # point is to detect 0-point clusters, so a fast approximate count
    # would defeat the check.
    n = int(client.count(collection_name=settings.qdrant_collection, exact=True).count)
    if n <= 0:
        return ("empty", 0)
    return ("ok", n)


# ---------------------------------------------------------------------------
# Co-hosted MCP servers (Task #31)
# ---------------------------------------------------------------------------
# The three MCP servers (swiss_law, contract_tools, user_context) are
# mounted under the FastAPI app at stable path prefixes so a single
# Replit deployment exposes all three streamable-HTTP endpoints over
# HTTPS. Each FastMCP instance owns a session_manager that MUST be
# entered as part of the parent app's lifespan — otherwise inbound
# JSON-RPC requests hit a closed task group and 500.
#
# Production wires the agent (managed_agents.bootstrap) by setting
# ``MCP_BASE_URL=https://<deployment-host>``; the per-server URLs are
# auto-derived to point at the mounts below.

_MCP_MOUNTS: tuple[tuple[str, object], ...] = (
    ("/mcp/swiss-law", build_fastmcp(_sl_server.SERVER)),
    ("/mcp/contract-tools", build_fastmcp(_ct_server.SERVER)),
    ("/mcp/user-context", build_fastmcp(_uc_server.SERVER)),
)


def _safe_url_host(url: str) -> str:
    """Strip everything except scheme + host[:port] from an MCP URL.

    MCP endpoint URLs may carry credentials (``user:pass@``), signed
    query parameters, or internal-only paths that have no business
    appearing in startup logs or the public ``/readyz`` body. We only
    need enough to tell two MCPs apart in an outage report — the
    scheme and host fulfil that without leaking topology or secrets.
    Returns ``"<unset>"`` for an empty URL and ``"<malformed>"`` if the
    parse blows up so the caller can still render *something* useful.
    """
    if not url:
        return "<unset>"
    try:
        parts = urlparse(url)
    except (ValueError, TypeError):
        return "<malformed>"
    host = parts.hostname or ""
    if not host:
        return "<malformed>"
    scheme = parts.scheme or "https"
    if parts.port:
        return f"{scheme}://{host}:{parts.port}"
    return f"{scheme}://{host}"


def _redact_id(value: str) -> str:
    """Render a managed-agents identifier for logs without leaking it.

    Vault/agent/environment IDs are not secrets the way an API key is,
    but they're still per-tenant identifiers that have no business in a
    plaintext log line. Show the first 4 + last 2 characters so an
    operator can correlate against the bootstrap output without
    exposing the full value.
    """
    if not value:
        return "<unset>"
    if len(value) <= 8:
        return f"{value[:2]}…{value[-2:]}"
    return f"{value[:4]}…{value[-2:]}"


def _validate_managed_agents_config() -> None:
    """Hard startup gate (Task #37) — fail loudly when managed agents
    are enabled but the bootstrap-time IDs / MCP URLs are missing.

    Called from the FastAPI lifespan BEFORE the app starts serving so
    a misconfigured deploy crashes on boot rather than silently
    serving zero-result scans. Set ``USE_MANAGED_AGENTS=0`` to opt out
    for local dev / CI / unit tests where there is no real agent.
    """
    if not settings.use_managed_agents:
        logger.warning(
            "agent_runner_unconfigured - use_managed_agents is false, "
            "agent IDs are missing or explicitly disabled. "
            "Falling back to one-shot messages.create."
        )
        return
    required = {
        "MANAGED_AGENT_ID": settings.managed_agent_id,
        "MANAGED_AGENT_VERSION": (
            str(settings.managed_agent_version)
            if settings.managed_agent_version > 0
            else ""
        ),
        "MANAGED_ENVIRONMENT_ID": settings.managed_environment_id,
        "MANAGED_VAULT_ID": settings.managed_vault_id,
        "MCP_SWISS_LAW_URL": settings.mcp_swiss_law_url,
        "MCP_CONTRACT_TOOLS_URL": settings.mcp_contract_tools_url,
        "MCP_USER_CONTEXT_URL": settings.mcp_user_context_url,
    }
    missing = [name for name, value in required.items() if not value]
    if missing:
        raise RuntimeError(
            "USE_MANAGED_AGENTS=true but required configuration is missing: "
            f"{', '.join(missing)}. Run "
            "`python -m swiss_legal_api.managed_agents.bootstrap` to "
            "provision the agent and populate the IDs, set MCP_BASE_URL "
            "(or each MCP_*_URL) to the deployment host, OR set "
            "USE_MANAGED_AGENTS=0 to opt out (local dev / CI only — "
            "production must run the agent driver)."
        )
    logger.info(
        "agent_runner_ready agent_id=%s version=%d environment_id=%s "
        "vault=%s mcp_swiss_law=%s mcp_contract_tools=%s "
        "mcp_user_context=%s",
        _redact_id(settings.managed_agent_id),
        settings.managed_agent_version,
        _redact_id(settings.managed_environment_id),
        _redact_id(settings.managed_vault_id),
        _safe_url_host(settings.mcp_swiss_law_url),
        _safe_url_host(settings.mcp_contract_tools_url),
        _safe_url_host(settings.mcp_user_context_url),
    )


_MCP_HEALTH_TIMEOUT_S = 4.0


async def _probe_one_mcp(client: httpx.AsyncClient, url: str) -> dict[str, object]:
    """Single MCP-server reachability probe.

    Streamable-HTTP MCP endpoints reject a bare GET with 405/406 (the
    JSON-RPC handshake requires POST). We treat any answer below 500
    as "the server is alive on the network" — a 4xx confirms the
    process is up and routing requests; a connection / timeout error
    or a 5xx is an outage. ``elapsed_ms`` is the wall-clock from
    request to first byte so operators can spot slow but live MCPs.

    The returned dict carries only the redacted ``host`` (scheme +
    hostname[:port]) — never the raw URL — because ``/readyz`` is
    publicly reachable and the URL may contain credentialed userinfo,
    signed query params, or internal-topology paths.
    """
    started = time.perf_counter()
    host = _safe_url_host(url)
    try:
        resp = await client.get(url, timeout=_MCP_HEALTH_TIMEOUT_S)
    except httpx.TimeoutException:
        return {
            "host": host,
            "status": "timeout",
            "elapsed_ms": int((time.perf_counter() - started) * 1000),
        }
    except httpx.HTTPError as exc:
        return {
            "host": host,
            "status": "unreachable",
            "error": type(exc).__name__,
            "elapsed_ms": int((time.perf_counter() - started) * 1000),
        }
    elapsed_ms = int((time.perf_counter() - started) * 1000)
    code = resp.status_code
    if code >= 500:
        return {
            "host": host,
            "status": "server_error",
            "http_status": code,
            "elapsed_ms": elapsed_ms,
        }
    return {
        "host": host,
        "status": "reachable",
        "http_status": code,
        "elapsed_ms": elapsed_ms,
    }


async def _probe_mcp_servers() -> dict[str, dict[str, object]]:
    """Concurrently probe all three MCP servers, return per-server status.

    Output values are safe to expose on /readyz: only the redacted
    host, status enum, optional HTTP code, and elapsed_ms — never the
    raw URL.
    """
    targets: list[tuple[str, str]] = [
        ("swiss_law", settings.mcp_swiss_law_url),
        ("contract_tools", settings.mcp_contract_tools_url),
        ("user_context", settings.mcp_user_context_url),
    ]
    out: dict[str, dict[str, object]] = {}
    async with httpx.AsyncClient(timeout=_MCP_HEALTH_TIMEOUT_S) as client:
        coros = [
            _probe_one_mcp(client, url) if url else _no_url()
            for _name, url in targets
        ]
        results = await asyncio.gather(*coros, return_exceptions=False)
    for (name, _url), result in zip(targets, results, strict=True):
        out[name] = result
    return out


async def _no_url() -> dict[str, object]:
    return {"host": "<unset>", "status": "unconfigured"}


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    # Strict managed-agents config gate (Task #37). Runs FIRST so a
    # misconfigured deploy crashes before we waste time spinning up MCP
    # session managers and the embedder.
    _validate_managed_agents_config()
    async with AsyncExitStack() as mcp_stack:
        for prefix, fmcp in _MCP_MOUNTS:
            try:
                # streamable_http_app() was already called at module level
                # (app.mount() below) which lazily created fmcp._session_manager
                # (session manager A) and wired it into the StreamableHTTPASGIApp
                # ASGI endpoint.  We must run() THAT same manager — NOT create a
                # new one — otherwise A is never started and every request throws
                # "Task group is not initialized".
                await mcp_stack.enter_async_context(
                    fmcp.session_manager.run()  # type: ignore
                )
                logger.info(
                    "mcp_server_started name=%s mount=%s",
                    getattr(fmcp, "name", "unknown"),
                    prefix,
                )
            except Exception:
                logger.exception(
                    "mcp_server_start_failed %s %s",
                    getattr(fmcp, "name", "unknown"),
                    prefix,
                )
                raise
        async with _app_lifespan_body():
            yield


@asynccontextmanager
async def _app_lifespan_body() -> AsyncIterator[None]:
    try:
        get_embedder()
        logger.info("embedder warmed: %s", settings.embedding_model)
    except Exception as exc:
        logger.exception("embedder warm-up failed: %s", type(exc).__name__)
    try:
        status, n = _probe_primary_collection()
        if status == "ok":
            logger.info(
                "qdrant reachable at %s; collection '%s' has %d points",
                settings.qdrant_url or "<unset>",
                settings.qdrant_collection,
                n,
            )
        elif status == "missing":
            # ERROR (not warning) so the failure is impossible to miss in
            # workflow logs — without the corpus every /scan returns 0
            # benefits silently.
            logger.error(
                "qdrant collection '%s' is MISSING on cluster %s — "
                "/scan will return 0 benefits until you run "
                "`python -m swiss_legal_api.seeding.seed_qdrant`.",
                settings.qdrant_collection,
                settings.qdrant_url or "<unset>",
            )
        else:  # "empty"
            logger.error(
                "qdrant collection '%s' on cluster %s is EMPTY (0 points) — "
                "/scan will return 0 benefits until you run "
                "`python -m swiss_legal_api.seeding.seed_qdrant`.",
                settings.qdrant_collection,
                settings.qdrant_url or "<unset>",
            )
    except Exception as exc:
        logger.warning(
            "qdrant unreachable at startup (%s); /readyz will reflect this",
            type(exc).__name__,
        )
    # Start the nightly benefit-sweep scheduler. No-op when
    # ``settings.sweep_enabled`` is false (the default), so dev runs
    # don't spawn a background thread silently.
    try:
        sweep_scheduler.start()
    except Exception as exc:
        logger.exception("sweep_scheduler_start_failed err=%s", type(exc).__name__)
    yield
    try:
        sweep_scheduler.stop()
    except Exception as exc:
        logger.exception("sweep_scheduler_stop_failed err=%s", type(exc).__name__)


app = FastAPI(
    title="Swiss Legal Agent API",
    version="0.1.0",
    description="Proactive Rights Discovery for Swiss residents.",
    lifespan=lifespan,
)

# Mount each FastMCP's streamable-HTTP ASGI app at its stable prefix.
# The MCP endpoint is reachable at ``<prefix>/`` (FastMCP's
# ``streamable_http_path`` defaults to "/" via ``build_fastmcp``).
for _prefix, _fmcp in _MCP_MOUNTS:
    app.mount(_prefix, _fmcp.streamable_http_app())  # type: ignore

# ---------------------------------------------------------------------------
# MCP path-normalizer middleware
# ---------------------------------------------------------------------------
# The Replit reverse-proxy strips trailing slashes from inbound URLs and
# returns a 308 redirect when Starlette's Mount does the opposite 307.
# This creates a redirect loop that Anthropic's managed-agents runtime
# cannot escape during MCP initialise.
#
# Solution: intercept requests whose path EXACTLY matches a mount prefix
# (i.e. ``/mcp/swiss-law`` with no trailing slash) and append the slash
# BEFORE Starlette's routing sees the request.  The FastMCP sub-app
# then handles the request directly (HTTP 200) with no redirect at all.
_MCP_PREFIXES: frozenset[str] = frozenset(p for p, _ in _MCP_MOUNTS)


@app.middleware("http")
async def _mcp_slash_normalizer(request: Request, call_next):  # type: ignore[type-arg]
    if request.scope.get("path") in _MCP_PREFIXES:
        # Patch both ``path`` and ``raw_path`` so sub-app routing is correct.
        request.scope["path"] = request.scope["path"] + "/"
        raw = request.scope.get("raw_path", b"")
        if raw and not raw.endswith(b"/"):
            request.scope["raw_path"] = raw + b"/"
    return await call_next(request)


_origins = settings.cors_origins_list()
if _origins:
    app.add_middleware(
        CORSMiddleware,
        allow_origins=_origins,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    logger.info("CORS locked to origins: %s", _origins)
elif settings.is_production():
    raise RuntimeError(
        "CORS misconfiguration: APP_ENV=production but neither FRONTEND_ORIGIN "
        "nor CORS_ALLOW_ORIGINS is set. Refusing to start with allow_origins=['*']."
    )
else:
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_methods=["*"],
        allow_headers=["*"],
    )
    logger.warning(
        "CORS allow_origins=['*'] — DEV ONLY (APP_ENV=%s). "
        "Set FRONTEND_ORIGIN or CORS_ALLOW_ORIGINS before deploying.",
        settings.app_env,
    )


class ChatRequest(BaseModel):
    message: str
    benefit_id: str | None = None
    # Caller-supplied identifier so the managed-agents launch metadata
    # (Task #26) carries a stable user_id end-to-end. Falls back to
    # ``anonymous`` when omitted — preserves backward compatibility for
    # the unauthenticated /chat surface while still letting clients
    # that DO know who is asking thread the value through.
    user_id: str = "anonymous"


class ChatResponse(BaseModel):
    answer: str
    # Provenance of the Claude call that produced this answer — the
    # /chat call site doesn't persist anything, so the response
    # envelope is the only audit trail the caller (and the frontend
    # "Unverified by agent" badge) gets. Always present for new
    # responses; defaulted to None only so legacy clients deserialising
    # an older snapshot don't break.
    agent_provenance: AgentProvenance | None = None


@app.get("/health")
async def health() -> dict[str, bool]:
    return {"ok": True}


@app.get("/readyz")
async def readyz(
    include: str | None = None, deep: bool = False
) -> dict[str, object]:
    """Liveness + Qdrant reachability probe.

    Default behaviour (no flags) is unchanged: confirms Qdrant is
    reachable. The primary scan collection's *existence* is implied by
    the cluster being up — but absence (or an empty collection) is a
    silent killer for ``/scan`` (0 benefits, HTTP 200), so:

    With ``?deep=1`` the probe additionally verifies that
    ``settings.qdrant_collection`` exists **and** holds ``> 0`` points.
    Returns 503 with a precise reason (``collection_missing`` /
    ``collection_empty``) so operators pointing the backend at a fresh
    or wrong cluster fail fast instead of debugging a "scan returns
    nothing" mystery.

    With ``?include=curriculum`` the probe additionally verifies the
    advisory ``settings.curriculum_collection`` is present. Use this in
    deployments that have seeded doctrinal PDFs and want a hard signal if
    the second collection ever drops out from under them.

    The two flags compose: ``?deep=1&include=curriculum`` runs both.
    """
    try:
        cols_resp = qdrant_client().get_collections()
    except Exception as exc:
        logger.warning("readyz: qdrant ping failed (%s)", type(exc).__name__)
        raise HTTPException(
            status_code=503, detail={"ok": False, "qdrant": "unreachable"}
        ) from exc

    collection_names = {c.name for c in cols_resp.collections}
    body: dict[str, object] = {"ok": True, "qdrant": "reachable"}

    if deep:
        # Reuse the get_collections() result we already have above so the
        # deep path is one extra round-trip (count) instead of two.
        try:
            status, n = _probe_primary_collection(collection_names)
        except Exception as exc:
            logger.warning(
                "readyz: deep probe failed (%s)", type(exc).__name__
            )
            raise HTTPException(
                status_code=503,
                detail={"ok": False, "qdrant": "unreachable"},
            ) from exc
        if status == "missing":
            logger.warning(
                "readyz: primary collection '%s' missing on cluster",
                settings.qdrant_collection,
            )
            raise HTTPException(
                status_code=503,
                detail={
                    "ok": False,
                    "qdrant": "reachable",
                    "collection": "missing",
                    "expected_collection": settings.qdrant_collection,
                },
            )
        if status == "empty":
            logger.warning(
                "readyz: primary collection '%s' has 0 points",
                settings.qdrant_collection,
            )
            raise HTTPException(
                status_code=503,
                detail={
                    "ok": False,
                    "qdrant": "reachable",
                    "collection": "empty",
                    "expected_collection": settings.qdrant_collection,
                    "points": 0,
                },
            )
        body["collection"] = "reachable"
        body["points"] = n

    # Managed-agents MCP probe (Task #37). When the agent driver is the
    # primary scan path, an unreachable MCP server is just as fatal as
    # an unreachable Qdrant — surface it on /readyz so deploys catch it
    # before users do. Probed when ?include=mcp is set OR whenever the
    # driver is enabled (so the default health check is self-contained
    # in production).
    if include == "mcp" or settings.use_managed_agents:
        mcp_results = await _probe_mcp_servers()
        body["mcp"] = mcp_results
        broken = {
            name: r
            for name, r in mcp_results.items()
            if r.get("status") not in ("reachable", "unconfigured")
        }
        if broken:
            logger.warning(
                "readyz: MCP probe found unreachable servers: %s",
                sorted(broken.keys()),
            )
            raise HTTPException(
                status_code=503,
                detail={
                    "ok": False,
                    "qdrant": "reachable",
                    "mcp": mcp_results,
                },
            )

    if include == "curriculum":
        if settings.curriculum_collection not in collection_names:
            logger.warning(
                "readyz: curriculum collection '%s' not found",
                settings.curriculum_collection,
            )
            raise HTTPException(
                status_code=503,
                detail={
                    "ok": False,
                    "qdrant": "reachable",
                    "curriculum": "missing",
                    "expected_collection": settings.curriculum_collection,
                },
            )
        body["curriculum"] = "reachable"

    return body


@app.post("/scan", response_model=BenefitReport)
async def scan(
    profile: ContextProfile,
    x_user_id: str | None = Header(default=None, alias="X-User-Id"),
) -> BenefitReport:
    # Propagate the caller's user_id (Task #26 metadata contract) into
    # every managed-agents session run as part of this scan. Header is
    # optional — anonymous /scan still works for the public landing-
    # page surface; the per-user sweep path passes a real id.
    user_id = x_user_id or "anonymous"
    try:
        report = await run_benefit_scan(
            profile, load_catalog(), user_id=user_id
        )
        # Persist so the agent-backed audit endpoint (/admin/audits/agent-backed)
        # can aggregate provenance over ad-hoc /scan calls in addition to the
        # nightly sweep. The sweep engine also calls insert_scan; using the same
        # function keeps the audit data path consistent.
        try:
            storage.insert_scan(user_id, report)
        except Exception as persist_exc:
            logger.warning("scan_persist_failed user_id=%s exc=%s", user_id, type(persist_exc).__name__)
        return report
    except Exception as exc:
        logger.exception("scan failed: %s", type(exc).__name__)
        raise HTTPException(status_code=500, detail="Internal error") from exc


# ---------------------------------------------------------------------------
# /scan/stream — Server-Sent Events progress channel (Task #34)
# ---------------------------------------------------------------------------
# A second surface over the same ``run_benefit_scan`` engine that pushes
# real progress events as the scan proceeds, so the /results UI can show
# the *actual* phase (trigger → verify → report), the real number of
# entitlements being verified, and per-benefit completions instead of a
# client-side timer-driven phase ticker.
#
# Wire format: standard SSE (``text/event-stream``). Each event has an
# ``event:`` line carrying the event type and a ``data:`` line carrying
# a single-line JSON payload. Event types emitted:
#
#   - ``phase``     — {"name": "trigger"|"verify"|"report", "message": str}
#   - ``triggered`` — {"count": int, "pending_corpus_backfill": int}
#   - ``verifying`` — per-entitlement start
#   - ``verified``  — per-entitlement finish (carries running counts)
#   - ``complete``  — {"report": BenefitReport}  (terminal, success)
#   - ``error``     — {"message": str}            (terminal, failure)
#
# The plain ``POST /scan`` endpoint is unchanged and remains the
# fallback the frontend uses when SSE isn't available (proxies that
# buffer text/event-stream, hostile networks, etc.).

@app.post("/scan/stream")
async def scan_stream(
    profile: ContextProfile,
    x_user_id: str | None = Header(default=None, alias="X-User-Id"),
) -> StreamingResponse:
    queue: asyncio.Queue[dict[str, object] | None] = asyncio.Queue()

    async def _on_progress(event: dict[str, object]) -> None:
        await queue.put(event)

    async def _runner() -> None:
        try:
            report = await run_benefit_scan(
                profile,
                load_catalog(),
                user_id=x_user_id or "anonymous",
                progress_cb=_on_progress,
            )
            await queue.put(
                {"type": "complete", "report": report.model_dump(mode="json")}
            )
        except Exception as exc:  # pragma: no cover - defensive
            logger.exception("scan_stream failed: %s", type(exc).__name__)
            await queue.put({"type": "error", "message": "Internal error"})
        finally:
            await queue.put(None)  # sentinel: close the stream

    async def _event_source() -> AsyncIterator[bytes]:
        task = asyncio.create_task(_runner())
        try:
            while True:
                ev = await queue.get()
                if ev is None:
                    break
                ev_type = str(ev.get("type", "message"))
                # SSE framing: an event is an optional ``event:`` line plus
                # one ``data:`` line followed by a blank line. We use a
                # single-line JSON payload so clients can ``JSON.parse``
                # without buffering across data lines.
                payload = _json.dumps(ev, separators=(",", ":"), default=str)
                yield (
                    f"event: {ev_type}\n"
                    f"data: {payload}\n\n"
                ).encode()
        finally:
            if not task.done():
                task.cancel()
                with suppress(asyncio.CancelledError, Exception):
                    await task

    return StreamingResponse(
        _event_source(),
        media_type="text/event-stream",
        headers={
            # Prevent intermediary buffering — without these the events
            # arrive in one big chunk at the end, defeating the point.
            "Cache-Control": "no-cache, no-transform",
            "X-Accel-Buffering": "no",
            "Connection": "keep-alive",
        },
    )


@app.post("/chat", response_model=ChatResponse)
async def chat(req: ChatRequest) -> ChatResponse:
    try:
        answer, provenance = await answer_follow_up(
            req.message, req.benefit_id, user_id=req.user_id
        )
        return ChatResponse(answer=answer, agent_provenance=provenance)
    except UnknownBenefitError as exc:
        # Explicit 4xx for stale/typoed benefit_id — keeps the
        # MCP-grounding gate intact while giving the operator a
        # actionable error instead of an opaque 500.
        raise HTTPException(
            status_code=404, detail=f"unknown benefit_id: {exc}"
        ) from exc
    except Exception as exc:
        logger.exception("chat failed: %s", type(exc).__name__)
        raise HTTPException(status_code=500, detail="Internal error") from exc


# ============================================================================
# Scheduled sweep — stateful endpoints (Task #22)
# ============================================================================
# These endpoints are the user-facing surface for the nightly benefit sweep:
# the wizard's "notify me" toggle posts the profile here, the results page
# fetches the latest sweep result, and the inbox lists alerts.
#
# Auth is intentionally out of scope (per task brief): ``user_id`` is a
# client-generated UUID stored in localStorage. The frontend treats it as
# opaque; the backend only validates length so the SQLite primary key
# stays well-formed.

# Reasonable upper bound — long enough for any UUID v4/v5 representation
# (36 chars), short enough that a malicious client can't bloat the DB.
_USER_ID_PATH = PathParam(..., min_length=1, max_length=128)


class AlertList(BaseModel):
    """List wrapper so the openapi-typescript client gets a named type."""
    alerts: list[Alert]


@app.post("/users/{user_id}/profile", response_model=UserRecord)
def upsert_profile(
    body: UserProfileUpsert,
    user_id: str = _USER_ID_PATH,
) -> UserRecord:
    """Create or update a stored user profile.

    Idempotent: re-posting the same profile only bumps ``last_seen_at``.
    Setting ``notify_enabled=False`` opts the user out of the nightly
    sweep without dropping their stored history (so a re-opt-in keeps
    diffing from the last known state).
    """
    try:
        return storage.upsert_user(user_id, body.profile, body.notify_enabled)
    except Exception as exc:
        logger.exception(
            "upsert_profile failed user_id=%s err=%s",
            user_id, type(exc).__name__,
        )
        raise HTTPException(status_code=500, detail="Internal error") from exc


@app.get("/users/{user_id}/profile", response_model=UserRecord)
def get_profile(user_id: str = _USER_ID_PATH) -> UserRecord:
    rec = storage.get_user(user_id)
    if rec is None:
        raise HTTPException(status_code=404, detail="user not found")
    return rec


@app.get("/users/{user_id}/scans/latest", response_model=BenefitReport)
def get_latest_scan(user_id: str = _USER_ID_PATH) -> BenefitReport:
    """Return the most-recent persisted sweep report for this user.

    404 when the user exists but has no sweep yet (e.g. profile was
    posted seconds ago and the nightly job hasn't fired). The frontend
    treats this as "loading — sweep pending" rather than an error.
    """
    if storage.get_user(user_id) is None:
        raise HTTPException(status_code=404, detail="user not found")
    report = storage.latest_scan(user_id)
    if report is None:
        raise HTTPException(status_code=404, detail="no scan yet")
    return report


@app.get("/users/{user_id}/alerts", response_model=AlertList)
def get_alerts(
    user_id: str = _USER_ID_PATH,
    unread_only: bool = False,
    limit: int = 100,
) -> AlertList:
    if storage.get_user(user_id) is None:
        raise HTTPException(status_code=404, detail="user not found")
    return AlertList(
        alerts=storage.list_alerts(
            user_id, unread_only=unread_only, limit=max(1, min(limit, 500)),
        )
    )


@app.post("/users/{user_id}/alerts/{alert_id}/read", status_code=204)
def mark_alert_read(
    user_id: str = _USER_ID_PATH,
    alert_id: str = PathParam(..., min_length=1, max_length=128),
) -> None:
    """Mark one alert as read. Idempotent: 204 whether the alert was
    unread, already read, or doesn't exist for this user. We expose
    ``alerts_exists`` checking via :func:`storage.alert_exists` so the
    handler can still return 404 when the alert truly isn't visible
    to this user — that's the case the frontend wants to surface, not
    "already read"."""
    if not storage.alert_exists(user_id, alert_id):
        raise HTTPException(status_code=404, detail="alert not found")
    storage.mark_alert_read(user_id, alert_id)


# ============================================================================
# Admin audits (Task #25)
# ============================================================================
# The agent-backed audit walks persisted Benefit.agent_provenance and
# answers "what fraction of our shipped analyses were produced by a
# managed agent (sessions.events with ≥1 tool use) vs a plain
# messages.create call?". The endpoint is the HTTP face of the same
# query the CLI runs (``python -m swiss_legal_api.audits agent_backed``).


def _check_admin_token(token: str | None) -> None:
    """Gate /admin/* endpoints behind a shared secret.

    Behaviour matrix:
    * ``settings.admin_audit_token`` set → require exact match.
    * Token unset + production → 403 (refuse to publish an open audit
      endpoint by accident).
    * Token unset + non-production → allow (dev / CI convenience).
    """
    expected = settings.admin_audit_token
    if expected:
        if not token or token != expected:
            raise HTTPException(status_code=403, detail="forbidden")
        return
    if settings.is_production():
        raise HTTPException(
            status_code=403,
            detail=(
                "admin endpoint disabled: ADMIN_AUDIT_TOKEN not set in "
                "production"
            ),
        )


@app.get("/admin/audits/agent-backed")
def admin_audit_agent_backed(
    x_admin_token: str | None = Header(default=None),
    since: str | None = Query(
        default=None,
        description=(
            "ISO-8601 timestamp; only reports generated at or after "
            "this instant are counted."
        ),
    ),
    entitlement_id: str | None = Query(
        default=None,
        description=(
            "Restrict to a single entitlement — the drill-down mode "
            "auditors use to answer 'was THIS verification "
            "agent-backed?'."
        ),
    ),
    job_id: str | None = Query(
        default=None,
        description=(
            "Restrict to a single scan run. job_id is the report's "
            "generated_at ISO timestamp (each persisted BenefitReport "
            "is keyed by (user_id, generated_at))."
        ),
    ),
    details: bool = Query(
        default=False,
        description=(
            "Include the full per-verification provenance list under "
            "``records``. Off by default so the headline call stays "
            "cheap."
        ),
    ),
) -> dict[str, object]:
    """Aggregate provenance over every persisted scan in the database.

    Counts every ``Benefit.agent_provenance`` across every persisted
    ``BenefitReport``, not just the latest report per user. Filters
    (``since``, ``entitlement_id``, ``job_id``) and the ``details``
    drill-down mode mirror the CLI's flags (``--since``,
    ``--entitlement-id``, ``--job-id``, ``--details``) so the HTTP
    and cron interfaces cannot drift.
    """
    _check_admin_token(x_admin_token)
    return agent_backed_summary(
        since=since,
        entitlement_id=entitlement_id,
        job_id=job_id,
        include_records=details,
    )
