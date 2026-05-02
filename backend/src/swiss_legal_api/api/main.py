from __future__ import annotations

import logging
import sys
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from ..catalog import load_catalog
from ..config import settings
from ..engine.retrieval import _client as qdrant_client
from ..engine.scan import run_benefit_scan
from ..schemas import BenefitReport, ContextProfile
from ..seeding.embedder import get_embedder
from .chat import answer_follow_up

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


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
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
    yield


app = FastAPI(
    title="Swiss Legal Agent API",
    version="0.1.0",
    description="Proactive Rights Discovery for Swiss residents.",
    lifespan=lifespan,
)


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


class ChatResponse(BaseModel):
    answer: str


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
async def scan(profile: ContextProfile) -> BenefitReport:
    try:
        return await run_benefit_scan(profile, load_catalog())
    except Exception as exc:
        logger.exception("scan failed: %s", type(exc).__name__)
        raise HTTPException(status_code=500, detail="Internal error") from exc


@app.post("/chat", response_model=ChatResponse)
async def chat(req: ChatRequest) -> ChatResponse:
    try:
        answer = await answer_follow_up(req.message, req.benefit_id)
        return ChatResponse(answer=answer)
    except Exception as exc:
        logger.exception("chat failed: %s", type(exc).__name__)
        raise HTTPException(status_code=500, detail="Internal error") from exc
