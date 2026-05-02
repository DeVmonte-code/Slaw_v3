"""Agent-backed audit queries (Task #25).

This module computes the same aggregate the
``GET /admin/audits/agent-backed`` endpoint serves, by walking every
persisted ``BenefitReport`` in storage and counting the
``Benefit.agent_provenance`` records.

Kept dependency-free of FastAPI so the CLI (``python -m
swiss_legal_api.audits agent_backed``) can run from cron without
booting the HTTP app.
"""
from __future__ import annotations

import logging
from collections import Counter
from typing import Any

from .. import storage
from ..schemas import AgentProvenance

logger = logging.getLogger(__name__)


def _collect_provenances() -> list[AgentProvenance | None]:
    """Walk every persisted scan and return the per-Benefit provenances.

    Iterates ``storage.iter_all_scans()`` — every historical scan, not
    just ``latest_scan`` per user — so a user who ran 12 scans
    contributes 12 reports' worth of benefits to the aggregate. This
    is the primary audit contract: if we silently dropped older
    reports the headline ``agent_backed_pct`` would be biased by
    user activity rather than reflecting what we actually shipped.

    A ``None`` entry means the Benefit was persisted before Task #25
    landed (the field defaulted to None on legacy rows). Those rows
    are counted under ``unknown`` in :func:`agent_backed_summary` so
    a clean rollout shows ``unknown=0`` after the next sweep.
    """
    out: list[AgentProvenance | None] = []
    for report in storage.iter_all_scans():
        for b in report.benefits:
            out.append(b.agent_provenance)
    return out


def agent_backed_summary() -> dict[str, Any]:
    """Aggregate counts + per-call-kind / per-model breakdowns.

    Shape is stable so the audit CLI, the admin endpoint, and the
    findings report can all consume the same dict without coupling
    to internal helpers.
    """
    provs = _collect_provenances()
    total = len(provs)
    agent_backed = sum(1 for p in provs if p is not None and p.agent_backed)
    unverified = sum(1 for p in provs if p is not None and not p.agent_backed)
    unknown = sum(1 for p in provs if p is None)
    by_call_kind: Counter[str] = Counter()
    by_model: Counter[str] = Counter()
    for p in provs:
        if p is None:
            by_call_kind["unknown"] += 1
            by_model["unknown"] += 1
        else:
            by_call_kind[p.call_kind] += 1
            by_model[p.model] += 1
    pct = (agent_backed / total) if total else 0.0
    return {
        "total_benefits": total,
        "agent_backed": agent_backed,
        "unverified_by_agent": unverified,
        "unknown_provenance": unknown,
        "agent_backed_pct": round(pct, 4),
        "by_call_kind": dict(by_call_kind),
        "by_model": dict(by_model),
    }
