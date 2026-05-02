"""``swiss-contract-tools-mcp`` — verification + scan analyzers.

Tools:
- ``verify_entitlement_tool(entitlement_id, profile, evidence)``
- ``run_benefit_scan_tool(profile)`` → full scan over the catalog

These wrap the SAME Python callables that
``swiss_legal_api/engine/verify.py`` and
``swiss_legal_api/engine/scan.py`` already expose to the in-process
verifier. The SSOT test enforces identity, so a refactor of either
analyzer automatically updates both Config A (direct SDK) and Config
B (managed-agents) paths.

Permission policy on the agent: ``always_ask`` for these tools — they
trigger Claude calls and Qdrant writes (via the underlying scan
pipeline) so the operator decides whether the agent may invoke them
unsupervised.
"""
from __future__ import annotations

from typing import Any

from ..catalog import load_catalog
from ..engine.scan import run_benefit_scan as _run_scan
from ..engine.verify import verify_entitlement as _verify
from ..schemas import ContextProfile
from . import McpServerSpec, McpToolSpec


async def verify_entitlement_tool(
    entitlement_id: str,
    profile: dict[str, Any],
    triggered_evidence: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    """MCP-shaped wrapper around :func:`engine.verify.verify_entitlement`.

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


async def run_benefit_scan_tool(profile: dict[str, Any]) -> dict[str, Any]:
    """MCP-shaped wrapper around :func:`engine.scan.run_benefit_scan`."""
    ctx = ContextProfile.model_validate(profile)
    report = await _run_scan(ctx, load_catalog())
    return report.model_dump(mode="json")


SERVER = McpServerSpec(
    name="swiss-contract-tools-mcp",
    tools=(
        McpToolSpec(
            name="verify_entitlement",
            description="Verify one entitlement against retrieved law for a profile.",
            impl=verify_entitlement_tool,
        ),
        McpToolSpec(
            name="run_benefit_scan",
            description="Run a full BenefitReport scan for the given profile.",
            impl=run_benefit_scan_tool,
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
