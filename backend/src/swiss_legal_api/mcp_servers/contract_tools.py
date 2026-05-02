"""``swiss-contract-tools-mcp`` — analyzers for triggers, retrieval-
backed verification, full benefit scans, tort assessment, alert diff
classification, and confidence scoring.

Tool surface (six tools, each a thin wrapper over a canonical Python
callable so Config A and Config B execute the SAME code):

- ``verify_entitlement(entitlement_id, profile, evidence)`` —
  retrieval-backed Claude verification (engine.verify.verify_entitlement)
- ``benefit_scan(profile)`` — full BenefitReport over the catalog
  (engine.scan.run_benefit_scan)
- ``analyze_tort(profile, allegation, sr_number, article)`` — runs the
  same verifier against an ad-hoc tort claim (default: SR 220 Art. 41
  OR — the Swiss tort general clause)
- ``evaluate_trigger(trigger_expr, profile)`` — pure trigger DSL
  evaluator (engine.trigger.evaluate_trigger)
- ``classify_diff(user_id, previous, current, changed_articles)`` —
  alert classifier (engine.sweep.classify_diff)
- ``score_confidence(raw_confidence, translation_only)`` — applies the
  server-side translation-only cap so the agent and the local verifier
  cannot disagree on the final number

Permission policy on the agent: ``always_ask`` for verification /
scan / tort (these trigger Claude calls and Qdrant reads); the pure
helpers (evaluate_trigger, classify_diff, score_confidence) are
``always_allow`` since they're side-effect free.
"""
from __future__ import annotations

from typing import Any

from pydantic import TypeAdapter

from ..catalog import load_catalog
from ..engine.scan import run_benefit_scan as _run_scan
from ..engine.sweep import classify_diff as _classify_diff
from ..engine.trigger import evaluate_trigger as _evaluate_trigger
from ..engine.verify import (
    _TRANSLATION_ONLY_CONFIDENCE_CAP,
)
from ..engine.verify import (
    _verify_local as _verify,
)
from ..schemas import (
    BenefitReport,
    Citation,
    ContextProfile,
    Entitlement,
    EstimatedValue,
    TitleI18n,
    TriggerExpr,
)
from ..schemas.sweep import Alert
from . import McpServerSpec, McpToolSpec

_TRIGGER_ADAPTER: TypeAdapter[TriggerExpr] = TypeAdapter(TriggerExpr)


async def verify_entitlement_tool(
    entitlement_id: str,
    profile: dict[str, Any],
    triggered_evidence: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    """MCP wrapper around :func:`engine.verify.verify_entitlement`.

    Profile is accepted as a dict so the JSON-RPC payload stays simple;
    we hand it to ``ContextProfile`` so the same validation that gates
    the HTTP API also gates the MCP path.
    """
    cat = {e.id: e for e in load_catalog()}
    ent = cat[entitlement_id]
    ctx = ContextProfile.model_validate(profile)
    result = await _verify(ent, ctx, triggered_evidence or [])
    return {
        "entitlement_id": entitlement_id,
        "supports": result.supports,
        "confidence": result.confidence,
        "reasoning": result.reasoning,
        "best_citation": result.best_citation.model_dump(mode="json"),
    }


async def benefit_scan_tool(profile: dict[str, Any]) -> dict[str, Any]:
    """MCP wrapper around :func:`engine.scan.run_benefit_scan`."""
    ctx = ContextProfile.model_validate(profile)
    report = await _run_scan(ctx, load_catalog())
    return report.model_dump(mode="json")


async def analyze_tort_tool(
    profile: dict[str, Any],
    allegation: str,
    sr_number: str = "220",
    article: str = "41",
) -> dict[str, Any]:
    """Assess a tort claim under the SR 220 Art. 41 general clause.

    Builds an ephemeral :class:`Entitlement` (so the agent and the
    in-process pipeline use the SAME verifier — no parallel analyzer)
    and runs the canonical retrieval + Claude path against it. The
    ``allegation`` string is folded into the title so retrieval has
    semantic context for the user's specific claim.
    """
    ctx = ContextProfile.model_validate(profile)
    title = f"Tort claim assessment: {allegation[:120]}"
    ad_hoc = Entitlement(
        id=f"ad_hoc_tort_SR{sr_number}_Art{article}",
        title=TitleI18n(en=title, de=title, fr=title, it=title),
        # Use the closest existing category — the catalog's Literal
        # union doesn't yet have "civil_law", and ad-hoc tort
        # assessment is the consumer's day-in-court remedy.
        category="consumer_protection",
        jurisdiction="federal",
        trigger=_TRIGGER_ADAPTER.validate_python({"all": []}),
        source_citations=[
            Citation(
                sr_number=sr_number,
                article=article,
                language="de",
                quote_under_15_words="(ad-hoc tort assessment)",
            )
        ],
        estimated_value_chf=EstimatedValue(min=0, max=0),
        required_action="consultation_with_lawyer",
    )
    result = await _verify(ad_hoc, ctx, [{"field": "allegation", "value": allegation}])
    return {
        "supports": result.supports,
        "confidence": result.confidence,
        "reasoning": result.reasoning,
        "best_citation": result.best_citation.model_dump(mode="json"),
    }


def evaluate_trigger_tool(
    trigger_expr: dict[str, Any], profile: dict[str, Any]
) -> dict[str, Any]:
    """MCP wrapper around :func:`engine.trigger.evaluate_trigger`."""
    ctx = ContextProfile.model_validate(profile)
    expr: TriggerExpr = _TRIGGER_ADAPTER.validate_python(trigger_expr)
    r = _evaluate_trigger(expr, ctx)
    return {"matched": r.matched, "evidence": r.evidence}


def classify_diff_tool(
    user_id: str,
    previous: dict[str, Any] | None,
    current: dict[str, Any],
    changed_articles: list[dict[str, Any]] | None = None,
) -> list[dict[str, Any]]:
    """MCP wrapper around :func:`engine.sweep.classify_diff`."""
    prev_report = (
        BenefitReport.model_validate(previous) if previous is not None else None
    )
    curr_report = BenefitReport.model_validate(current)
    changes: dict[tuple[str, str], str | None] = {}
    for entry in changed_articles or []:
        sr = str(entry["sr_number"])
        art = str(entry["article"])
        changes[(sr, art)] = entry.get("amendment_date")
    alerts: list[Alert] = _classify_diff(
        user_id=user_id,
        previous=prev_report,
        current=curr_report,
        changed_articles=changes,
    )
    return [a.model_dump(mode="json") for a in alerts]


def score_confidence_tool(
    raw_confidence: float, translation_only: bool = False
) -> dict[str, Any]:
    """Apply the server-side translation-only confidence cap.

    Returns ``{"confidence": float, "capped": bool}`` so the agent can
    surface to the user when its raw assessment was reduced. Single
    source of truth for the cap value lives in
    :mod:`engine.verify` (``_TRANSLATION_ONLY_CONFIDENCE_CAP``).
    """
    raw = max(0.0, min(1.0, float(raw_confidence)))
    if translation_only and raw > _TRANSLATION_ONLY_CONFIDENCE_CAP:
        return {"confidence": _TRANSLATION_ONLY_CONFIDENCE_CAP, "capped": True}
    return {"confidence": raw, "capped": False}


# Re-export the canonical implementations under stable names so the
# SSOT test can assert ``contract_tools._verify is verify_entitlement``
# (identity, not equality). A future refactor that copies a callable
# will fail this assertion and surface in CI.
__all__ = [
    "SERVER",
    "_classify_diff",
    "_evaluate_trigger",
    "_run_scan",
    "_verify",
    "analyze_tort_tool",
    "benefit_scan_tool",
    "classify_diff_tool",
    "evaluate_trigger_tool",
    "score_confidence_tool",
    "verify_entitlement_tool",
]


SERVER = McpServerSpec(
    name="swiss-contract-tools-mcp",
    tools=(
        McpToolSpec(
            name="verify_entitlement",
            description="Verify one entitlement against retrieved law for a profile.",
            impl=verify_entitlement_tool,
        ),
        McpToolSpec(
            name="benefit_scan",
            description="Run a full BenefitReport scan for the given profile.",
            impl=benefit_scan_tool,
        ),
        McpToolSpec(
            name="analyze_tort",
            description="Assess a tort claim under SR 220 Art. 41 (general clause).",
            impl=analyze_tort_tool,
        ),
        McpToolSpec(
            name="evaluate_trigger",
            description="Pure-function trigger DSL evaluator over a profile.",
            impl=evaluate_trigger_tool,
        ),
        McpToolSpec(
            name="classify_diff",
            description="Emit NEW/UPDATED/GONE alerts diffing two BenefitReports.",
            impl=classify_diff_tool,
        ),
        McpToolSpec(
            name="score_confidence",
            description="Apply the translation-only confidence cap (server-enforced).",
            impl=score_confidence_tool,
        ),
    ),
)


def serve() -> None:  # pragma: no cover
    from mcp.server.fastmcp import FastMCP  # type: ignore[import-not-found]

    app = FastMCP(SERVER.name)
    for tool in SERVER.tools:
        app.tool(name=tool.name, description=tool.description)(tool.impl)
    app.run(transport="streamable-http")


if __name__ == "__main__":  # pragma: no cover
    serve()
