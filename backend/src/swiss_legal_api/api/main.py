from __future__ import annotations

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from ..catalog import load_catalog
from ..engine.scan import run_benefit_scan
from ..schemas import BenefitReport, ContextProfile
from .chat import answer_follow_up

app = FastAPI(
    title="Swiss Legal Agent API",
    version="0.1.0",
    description="Proactive Rights Discovery for Swiss residents.",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


class ChatRequest(BaseModel):
    message: str
    benefit_id: str | None = None


class ChatResponse(BaseModel):
    answer: str


@app.get("/health")
async def health() -> dict[str, bool]:
    return {"ok": True}


@app.post("/scan", response_model=BenefitReport)
async def scan(profile: ContextProfile) -> BenefitReport:
    try:
        return await run_benefit_scan(profile, load_catalog())
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@app.post("/chat", response_model=ChatResponse)
async def chat(req: ChatRequest) -> ChatResponse:
    try:
        answer = await answer_follow_up(req.message, req.benefit_id)
        return ChatResponse(answer=answer)
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc
