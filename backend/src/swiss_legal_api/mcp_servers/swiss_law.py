"""``swiss-law-retrieval-mcp`` — read-only retrieval over the Qdrant
corpus that backs ``engine/verify.py``.

Tools:
- ``qdrant_search(query, sr_number, article, canton)`` → list of
  retrieved chunks. Thin wrapper over
  :func:`swiss_legal_api.engine.retrieval.retrieve_for_citation` so the
  agent and the local verifier hit the SAME similarity / canton /
  effective-date guardrails. The single-source-of-truth test asserts
  the registry's ``impl`` IS ``retrieve_for_citation`` itself.
- ``fetch_article_by_sr(sr_number, article, canton)`` → exact-match
  retrieval (no fuzzy query string), used by the agent when it already
  knows the SR + article it needs to read.
- ``list_citations(entitlement_id)`` → the catalog's source citations
  for one entitlement, so the agent can pick which article to fetch.

Why read-only: this server is the agent's authoritative-source
gateway. Permission policy on the agent is ``always_allow`` — there is
no write surface, so silent execution is safe and auditable.
"""

from __future__ import annotations

from typing import Any

from ..catalog import load_catalog
from ..engine.retrieval import retrieve_for_citation
from ..schemas import Citation
from . import McpServerSpec, McpToolSpec, build_fastmcp


def qdrant_search(
    query: str,
    sr_number: str,
    article: str,
    canton: str = "CH",
) -> list[dict[str, Any]]:
    """Run the canonical retrieval pipeline for an SR + article + canton.

    Returns the same chunk shape ``engine.verify`` already builds when
    it talks to Claude directly — keeping the wire-format identical
    means the agent's prompt can re-use the existing reasoning rubric
    without translation.
    """
    # Citation requires language + quote fields, but the retriever only
    # uses sr_number and article — fill the rest with neutral defaults
    # so the validator passes without affecting the Qdrant query shape.
    cit = Citation(
        sr_number=sr_number,
        article=article,
        language="de",
        quote_under_15_words="(retrieval-only stub)",
    )
    chunks = retrieve_for_citation(cit, query, canton)
    return [
        {
            "text": c.text,
            "language": c.language,
            "score": round(c.score, 3),
            "effective_date": c.effective_date.isoformat() if c.effective_date else None,
        }
        for c in chunks
    ]


def fetch_article_by_sr(sr_number: str, article: str, canton: str = "CH") -> list[dict[str, Any]]:
    """Exact-match retrieval — same callable, empty query string."""
    return qdrant_search("", sr_number, article, canton)


def list_citations(entitlement_id: str) -> list[dict[str, str]]:
    """Return the catalog's source citations for one entitlement."""
    cat = {e.id: e for e in load_catalog()}
    ent = cat.get(entitlement_id)
    if ent is None:
        return []
    return [{"sr_number": c.sr_number, "article": c.article} for c in ent.source_citations]


SERVER = McpServerSpec(
    name="swiss-law-retrieval-mcp",
    tools=(
        McpToolSpec(
            name="qdrant_search",
            description="Similarity-bounded retrieval over the Qdrant law corpus.",
            impl=qdrant_search,
        ),
        McpToolSpec(
            name="fetch_article_by_sr",
            description="Exact-match fetch of one SR article (canton-scoped).",
            impl=fetch_article_by_sr,
        ),
        McpToolSpec(
            name="list_citations",
            description="Catalog source citations for one entitlement id.",
            impl=list_citations,
        ),
    ),
)


def serve() -> None:  # pragma: no cover — production deployment shim
    """Run as a standalone MCP server over HTTPS streamable-HTTP.

    Production deploys this file either standalone (one process per
    server) or co-hosted under the FastAPI app at
    ``${MCP_BASE_URL}/mcp/swiss-law/`` — both paths build the same
    ``FastMCP`` via :func:`mcp_servers.build_fastmcp`.
    """
    build_fastmcp(SERVER, mount_path="/mcp").run(transport="streamable-http")


if __name__ == "__main__":  # pragma: no cover
    serve()
