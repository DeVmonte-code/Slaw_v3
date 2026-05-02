from __future__ import annotations

import logging
import sys
from contextlib import asynccontextmanager
from typing import AsyncIterator

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


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    try:
        get_embedder()
        logger.info("embedder warmed: %s", settings.embedding_model)
    except Exception as exc:
        logger.exception("embedder warm-up failed: %s", type(exc).__name__)
    try:
        qdrant_client().get_collections()
        logger.info("qdrant reachable at %s", settings.qdrant_url or "<unset>")
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
async def readyz() -> dict[str, object]:
    try:
        qdrant_client().get_collections()
    except Exception as exc:
        logger.warning("readyz: qdrant ping failed (%s)", type(exc).__name__)
        raise HTTPException(
            status_code=503, detail={"ok": False, "qdrant": "unreachable"}
        ) from exc
    return {"ok": True, "qdrant": "reachable"}


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
