"""``swiss-law-retrieval-mcp`` — read-only retrieval over the Qdrant
corpus that backs ``engine/verify.py``.

Tools:
- ``qdrant_search(query, sr_number, article, canton)`` → list of
  retrieved chunks, now including ``eli_uri`` and ``paragraph`` so the
  agent can follow up with ``fetch_fedlex_article``.
- ``fetch_article_by_sr(sr_number, article, canton)`` → exact-match
  retrieval (no fuzzy query string), used by the agent when it already
  knows the SR + article it needs to read.
- ``list_citations(entitlement_id)`` → the catalog's source citations
  for one entitlement, so the agent can pick which article to fetch.
- ``fetch_fedlex_article(eli_uri)`` → fetches official law metadata
  from the Fedlex linked-data API (title, SR number, language).
  Combines with the Qdrant chunk text to give the agent full
  authoritative context for benefit analysis.

Why read-only: this server is the agent's authoritative-source
gateway. Permission policy on the agent is ``always_allow`` — there is
no write surface, so silent execution is safe and auditable.
"""

from __future__ import annotations

import logging
import re
import xml.etree.ElementTree as ET
from typing import Any

import httpx

from ..catalog import load_catalog
from ..engine.retrieval import retrieve_for_citation
from ..schemas import Citation
from . import McpServerSpec, McpToolSpec, build_fastmcp

logger = logging.getLogger(__name__)

# Timeout for a single Fedlex HTTP request (seconds).
_FEDLEX_TIMEOUT_S = 15.0

# Jolux ontology namespace used in Fedlex RDF responses.
_JOLUX = "http://data.legilux.public.lu/resource/ontology/jolux#"
_RDF = "http://www.w3.org/1999/02/22-rdf-syntax-ns#"

# Language suffix pattern at the end of eli_uri (e.g. "/de", "/fr", "/it", "/rm")
_LANG_SUFFIX_RE = re.compile(r"/(de|fr|it|rm|en)$", re.IGNORECASE)


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

    Each chunk now also carries ``eli_uri`` and ``paragraph`` (when
    present in the Qdrant payload) so the agent can call
    ``fetch_fedlex_article`` to read the official law metadata and
    confirm the legal context of the retrieved text.
    """
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
            "eli_uri": c.eli_uri,
            "paragraph": c.paragraph,
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


def _parse_rdf_metadata(rdf_text: str) -> dict[str, str]:
    """Extract jolux metadata from Fedlex RDF/XML.

    Returns a dict with keys: ``title``, ``title_short``, ``sr_number``,
    ``language``.  Missing fields are empty strings.
    """
    out: dict[str, str] = {"title": "", "title_short": "", "sr_number": "", "language": ""}
    try:
        root = ET.fromstring(rdf_text)
    except ET.ParseError:
        return out

    ns = {
        "jolux": _JOLUX,
        "rdf": _RDF,
        "rdfs": "http://www.w3.org/2000/01/rdf-schema#",
    }
    # Iterate all Description elements in the RDF graph.
    for desc in root.iter(f"{{{_RDF}}}Description"):
        title_el = desc.find(f"{{{_JOLUX}}}title")
        if title_el is not None and title_el.text:
            out["title"] = title_el.text.strip()
        short_el = desc.find(f"{{{_JOLUX}}}titleShort")
        if short_el is not None and short_el.text:
            out["title_short"] = short_el.text.strip()
        sr_el = desc.find(f"{{{_JOLUX}}}historicalLegalId")
        if sr_el is not None and sr_el.text:
            out["sr_number"] = sr_el.text.strip()
        lang_el = desc.find(f"{{{_JOLUX}}}language")
        if lang_el is not None:
            lang_resource = lang_el.get(f"{{{_RDF}}}resource", "")
            # e.g. ".../language/DEU" → "de"
            code = lang_resource.rstrip("/").split("/")[-1].lower()[:2]
            if code in {"de", "fr", "it", "rm", "en"}:
                out["language"] = code

    return out


async def fetch_fedlex_article(eli_uri: str) -> dict[str, Any]:
    """Fetch official Swiss law metadata from the Fedlex linked-data API.

    Uses the Fedlex RDF/XML endpoint (the only machine-readable API that
    works without JavaScript rendering).  Returns the official law title,
    abbreviation, and SR number for the given ``eli_uri``.

    The agent should use the returned metadata together with the article
    text from ``qdrant_search`` to:
    1. Confirm which official law the Qdrant chunk belongs to.
    2. Reference the authoritative law name and SR number in reasoning.
    3. Determine what benefits apply based on the legal context.

    Returns::

        {
            "eli_uri":    "<original URI>",
            "title":      "<official full law title in the URI's language>",
            "title_short": "<abbreviation, e.g. OR, ZGB, SchKG>",
            "sr_number":  "<systematic register number, e.g. 220>",
            "language":   "<de|fr|it|rm|en>",
            "source_url": "<fetched RDF URL>",
            "error":      "<message if fetch failed, else null>"
        }

    Note: Fedlex article-level URIs (e.g. /de/art.697m) are not
    exposed by the Fedlex API; use ``qdrant_search`` for the article
    text and this tool for the law-level context.
    """
    try:
        async with httpx.AsyncClient(
            follow_redirects=True,
            timeout=_FEDLEX_TIMEOUT_S,
        ) as client:
            resp = await client.get(
                eli_uri,
                headers={
                    "Accept": "application/rdf+xml",
                    "User-Agent": "SwissLegalAPI/1.0 (legal-rights-scan; read-only)",
                },
            )
            resp.raise_for_status()
            rdf_text = resp.text
    except httpx.HTTPStatusError as exc:
        logger.warning(
            "fedlex_rdf_http_error eli_uri=%s status=%s",
            eli_uri,
            exc.response.status_code,
        )
        return {
            "eli_uri": eli_uri,
            "title": "",
            "title_short": "",
            "sr_number": "",
            "language": "",
            "source_url": eli_uri,
            "error": f"HTTP {exc.response.status_code}",
        }
    except Exception as exc:
        logger.warning("fedlex_rdf_error eli_uri=%s exc=%s", eli_uri, type(exc).__name__)
        return {
            "eli_uri": eli_uri,
            "title": "",
            "title_short": "",
            "sr_number": "",
            "language": "",
            "source_url": eli_uri,
            "error": type(exc).__name__,
        }

    meta = _parse_rdf_metadata(rdf_text)
    logger.info(
        "fedlex_rdf_ok eli_uri=%s sr=%s title_short=%s lang=%s",
        eli_uri,
        meta["sr_number"],
        meta["title_short"],
        meta["language"],
    )
    return {
        "eli_uri": eli_uri,
        "title": meta["title"],
        "title_short": meta["title_short"],
        "sr_number": meta["sr_number"],
        "language": meta["language"],
        "source_url": eli_uri,
        "error": None,
    }


SERVER = McpServerSpec(
    name="swiss-law-retrieval-mcp",
    tools=(
        McpToolSpec(
            name="qdrant_search",
            description=(
                "Similarity-bounded retrieval over the Qdrant law corpus. "
                "Returns chunks with text, score, language, effective_date, "
                "eli_uri and paragraph. Use eli_uri with fetch_fedlex_article "
                "to get the official law title and SR number from Fedlex."
            ),
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
        McpToolSpec(
            name="fetch_fedlex_article",
            description=(
                "Fetch official Swiss law metadata (title, abbreviation, SR number) "
                "from the Fedlex linked-data API for a given eli_uri. "
                "Call this for every unique eli_uri returned by qdrant_search "
                "to confirm the authoritative legal context before deciding "
                "what benefits apply to the user profile."
            ),
            impl=fetch_fedlex_article,
        ),
    ),
)


def serve() -> None:  # pragma: no cover — production deployment shim
    """Run as a standalone MCP server over HTTPS streamable-HTTP."""
    build_fastmcp(SERVER, mount_path="/mcp").run(transport="streamable-http")


if __name__ == "__main__":  # pragma: no cover
    serve()
