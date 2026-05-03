"""Agent-backed audit queries (Task #25).

Computes the same aggregate the ``GET /admin/audits/agent-backed``
endpoint serves, by walking every persisted ``BenefitReport`` in
storage and counting the ``Benefit.agent_provenance`` records.

Supports filtering by ``since`` (ISO timestamp window) and
``entitlement_id`` (single-id drill-down) so an auditor can answer
not just "what fraction of all shipped analyses were agent-backed?"
but also "was THIS specific entitlement verified by an agent in the
last 24h?". When ``include_records=True`` the response carries the
full per-verification provenance payload, not just aggregates.

Kept dependency-free of FastAPI so the CLI (``python -m
swiss_legal_api.audits agent_backed``) can run from cron without
booting the HTTP app.
"""

from __future__ import annotations

import logging
from collections import Counter
from collections.abc import Iterator
from datetime import UTC, datetime
from typing import Any

from .. import storage
from ..schemas import AgentProvenance, BenefitReport

logger = logging.getLogger(__name__)


def _iter_records(
    *,
    since: str | None = None,
    entitlement_id: str | None = None,
    job_id: str | None = None,
) -> Iterator[dict[str, Any]]:
    """Yield one record per persisted Benefit matching the filters.

    Each record carries the full provenance payload plus the keys an
    auditor needs to answer "this specific verification" questions:
    ``entitlement_id``, ``generated_at`` (the report timestamp), and
    ``confidence``. Filtering is applied here (not in SQL) because the
    sqlite store keeps the report as JSON — a dedicated index is not
    yet justified at the current scale.

    ``since`` is parsed as an ISO-8601 instant (``datetime`` semantics,
    not lexicographic string comparison) so callers can pass any
    well-formed variant — ``2026-04-01T00:00:00Z``,
    ``2026-04-01T00:00:00+00:00``, with or without microseconds — and
    boundary semantics stay correct. Reports whose ``generated_at`` is
    strictly before the parsed ``since`` are skipped.
    """
    since_dt = _parse_iso_utc(since) if since is not None else None
    for report in storage.iter_all_scans():
        if since_dt is not None:
            report_dt = _parse_iso_utc(report.generated_at)
            if report_dt is None or report_dt < since_dt:
                continue
        # ``job_id`` is the persisted scan-run identifier — each
        # ``BenefitReport`` row is keyed by ``(user_id, generated_at)``,
        # so the report's ``generated_at`` IS the job_id auditors use
        # to drill down to a single scan run.
        if job_id is not None and report.generated_at != job_id:
            continue
        for b in report.benefits:
            if entitlement_id is not None and b.entitlement_id != entitlement_id:
                continue
            yield {
                "entitlement_id": b.entitlement_id,
                "generated_at": report.generated_at,
                "confidence": b.confidence,
                "agent_provenance": (
                    b.agent_provenance.model_dump() if b.agent_provenance is not None else None
                ),
            }


def _parse_iso_utc(value: str) -> datetime | None:
    """Parse an ISO-8601 timestamp, normalising to a UTC-aware datetime.

    Returns ``None`` for malformed input so the caller can decide
    whether to skip the row (lenient) or surface the error. We
    normalise naive datetimes to UTC because every persisted
    ``generated_at`` is written in UTC.
    """
    s = value.replace("Z", "+00:00") if value.endswith("Z") else value
    try:
        dt = datetime.fromisoformat(s)
    except ValueError:
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=UTC)
    return dt


def _aggregate(records: list[dict[str, Any]]) -> dict[str, Any]:
    """Compute the headline counts + breakdowns from a record list."""
    total = len(records)
    agent_backed = 0
    unverified = 0
    unknown = 0
    by_call_kind: Counter[str] = Counter()
    by_model: Counter[str] = Counter()
    for r in records:
        prov = r["agent_provenance"]
        if prov is None:
            unknown += 1
            by_call_kind["unknown"] += 1
            by_model["unknown"] += 1
            continue
        if prov["agent_backed"]:
            agent_backed += 1
        else:
            unverified += 1
        by_call_kind[prov["call_kind"]] += 1
        by_model[prov["model"]] += 1
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


def agent_backed_summary(
    *,
    since: str | None = None,
    entitlement_id: str | None = None,
    job_id: str | None = None,
    include_records: bool = False,
) -> dict[str, Any]:
    """Aggregate counts + per-call-kind / per-model breakdowns.

    The shape is stable across the CLI, the admin endpoint, and the
    findings report so they cannot drift.

    Parameters mirror the admin endpoint:

    * ``since`` — ISO-8601 timestamp; only reports generated at or
      after this instant are counted.
    * ``entitlement_id`` — restrict to a single entitlement (the
      "drill-down for one verification" mode).
    * ``job_id`` — restrict to a single scan run. Each persisted
      ``BenefitReport`` is keyed by ``(user_id, generated_at)``, so
      ``job_id`` is the report's ``generated_at`` ISO timestamp.
    * ``include_records`` — when True, the response carries the full
      per-verification provenance list under ``records``. Costs O(N)
      bytes; off by default so the headline call stays cheap.
    """
    records = list(_iter_records(since=since, entitlement_id=entitlement_id, job_id=job_id))
    out = _aggregate(records)
    out["filter"] = {
        "since": since,
        "entitlement_id": entitlement_id,
        "job_id": job_id,
    }
    if include_records:
        out["records"] = records
    return out


# Convenience helper kept for tests / external callers that just want
# the AgentProvenance objects (or None for legacy rows).
def _collect_provenances() -> list[AgentProvenance | None]:
    """Walk every persisted scan and return the per-Benefit provenances."""
    out: list[AgentProvenance | None] = []
    for report in storage.iter_all_scans():
        for b in report.benefits:
            out.append(b.agent_provenance)
    return out


__all__ = ["BenefitReport", "_collect_provenances", "agent_backed_summary"]
