from __future__ import annotations

import asyncio
import hashlib
import json
import math
from datetime import datetime
from typing import Any

from ..config import settings
from ..schemas import Benefit, BenefitReport, ContextProfile, Entitlement, EvidenceItem
from .trigger import evaluate_trigger
from .verify import VerifyResult, verify_entitlement


async def _verify_one(
    e: Entitlement,
    profile: ContextProfile,
    evidence: list[dict[str, Any]],
    sem: asyncio.Semaphore,
) -> tuple[Entitlement, list[dict[str, Any]], VerifyResult | None]:
    async with sem:
        try:
            v = await verify_entitlement(e, profile, evidence)
            return e, evidence, v
        except Exception:
            return e, evidence, None


async def run_benefit_scan(
    profile: ContextProfile, catalog: list[Entitlement]
) -> BenefitReport:
    triggered: list[tuple[Entitlement, list[dict[str, Any]]]] = []
    for e in catalog:
        r = evaluate_trigger(e.trigger, profile)
        if r.matched:
            triggered.append((e, r.evidence))

    sem = asyncio.Semaphore(settings.scan_concurrency)
    results = await asyncio.gather(
        *[_verify_one(e, profile, ev, sem) for e, ev in triggered]
    )

    benefits: list[Benefit] = []
    suppressed = 0
    for e, evidence, v in results:
        if v is None or not v.supports or v.confidence < e.confidence_floor:
            suppressed += 1
            continue
        title: str = str(getattr(e.title, profile.language, None) or e.title.en)
        benefits.append(
            Benefit(
                entitlement_id=e.id,
                title=title,
                category=e.category,
                estimated_value_chf=e.estimated_value_chf,
                confidence=v.confidence,
                citations=[v.best_citation, *e.source_citations[1:]],
                evidence=[EvidenceItem(**ev) for ev in evidence],
                required_action=e.required_action,
                action_template_id=e.action_template_id,
                time_limit_days=e.time_limit_days,
                llm_reasoning=v.reasoning,
            )
        )

    benefits.sort(
        key=lambda b: b.confidence * math.log1p(b.estimated_value_chf.max),
        reverse=True,
    )

    profile_hash = hashlib.sha256(
        json.dumps(profile.model_dump(mode="json"), sort_keys=True).encode()
    ).hexdigest()[:16]

    return BenefitReport(
        generated_at=datetime.utcnow().isoformat() + "Z",
        profile_hash=profile_hash,
        benefits=benefits,
        suppressed_count=suppressed,
    )
