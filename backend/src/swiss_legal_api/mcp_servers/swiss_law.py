"""``swiss-law-retrieval-mcp`` — read-only retrieval over the Qdrant
corpus that backs ``engine/verify.py``.

Tools:
- ``qdrant_search(query, sr_number, article, canton)`` → list of retrieved
  chunks, including ``eli_uri`` and ``paragraph`` so the agent can follow up
  with ``fetch_fedlex_article``.
- ``fetch_article_by_sr(sr_number, article, canton)`` → exact-match retrieval
  (no fuzzy query string).
- ``list_citations(entitlement_id)`` → the catalog's source citations for one
  entitlement.
- ``fetch_fedlex_article(eli_uri, article=None)`` → fetches official law
  metadata AND, when ``article`` is supplied, the full live article text from
  the Fedlex linked-data filestore.

Live-fetch path (when ``article`` is given):
  1. SPARQL `fedlex.data.admin.ch/sparqlendpoint` → latest dated expression
     URI (e.g. ``.../20260101/de``).
  2. SPARQL → HTML filestore URL for that expression.
  3. GET the HTML file (~2-3 MB for large laws, cached per expression).
  4. Extract the ``<article id="art_NNN">`` block; parse each
     ``<p class="absatz">`` into a numbered paragraph.

Caching: in-process LRU bounded at ``_HTML_CACHE_MAXSIZE`` entries keyed by
``(expression_uri, html_url)``.  Warm-cache latency <50 ms; cold-cache
latency <4 s (one SPARQL + one HTML download).

Why read-only: this server is the agent's authoritative-source gateway.
Permission policy on the agent is ``always_allow`` — there is no write
surface, so silent execution is safe and auditable.
"""

from __future__ import annotations

import html as html_lib
import logging
import re
import xml.etree.ElementTree as ET
from collections import OrderedDict
from datetime import date
from typing import Any

import httpx

from ..catalog import load_catalog
from ..engine.retrieval import retrieve_for_citation
from ..schemas import Citation
from . import McpServerSpec, McpToolSpec, build_fastmcp

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

_FEDLEX_TIMEOUT_S = 15.0
_SPARQL_ENDPOINT = "https://fedlex.data.admin.ch/sparqlendpoint"
_HTML_USER_FORMAT = "https://fedlex.data.admin.ch/vocabulary/user-format/html"
_HTML_CACHE_MAXSIZE = 32

_JOLUX = "http://data.legilux.public.lu/resource/ontology/jolux#"
_RDF = "http://www.w3.org/1999/02/22-rdf-syntax-ns#"
_USER_AGENT = "SwissLegalAPI/1.0 (legal-rights-scan; read-only)"

# Maps 2-letter BCP-47 codes to ISO 639-2/B (used in Fedlex URIs).
_LANG_TO_ISO639_2: dict[str, str] = {
    "de": "DEU",
    "fr": "FRA",
    "it": "ITA",
    "rm": "ROH",
    "en": "ENG",
}

# Patterns for splitting eli_uri into (law_base, language).
# Dated:    …/eli/cc/27/317_321_377/20250101/de
# Undated:  …/eli/cc/27/317_321_377/de
_DATED_URI_RE = re.compile(
    r"^(https://fedlex\.data\.admin\.ch/eli/.+)/(\d{8})/([a-z]{2,3})$"
)
_UNDATED_URI_RE = re.compile(
    r"^(https://fedlex\.data\.admin\.ch/eli/.+)/([a-z]{2,3})$"
)

# ---------------------------------------------------------------------------
# In-process HTML cache
# ---------------------------------------------------------------------------

_html_cache: OrderedDict[tuple[str, str], str] = OrderedDict()


def _cache_get(key: tuple[str, str]) -> str | None:
    if key in _html_cache:
        _html_cache.move_to_end(key)
        return _html_cache[key]
    return None


def _cache_set(key: tuple[str, str], value: str) -> None:
    _html_cache[key] = value
    _html_cache.move_to_end(key)
    while len(_html_cache) > _HTML_CACHE_MAXSIZE:
        _html_cache.popitem(last=False)


# ---------------------------------------------------------------------------
# Article-id normalizer
# ---------------------------------------------------------------------------


def _normalize_article_id(article: str) -> str:
    """Map an article number string to its Fedlex HTML anchor id.

    Examples::

        "697m"  → "art_697_m"
        "663b"  → "art_663_b"
        "697"   → "art_697"
        "6a"    → "art_6_a"
        "270a"  → "art_270_a"
    """
    normalized = re.sub(r"(\d+)([a-z]+)$", r"\1_\2", article.lower())
    return f"art_{normalized}"


# ---------------------------------------------------------------------------
# URI helpers
# ---------------------------------------------------------------------------


def _extract_law_base_and_lang(eli_uri: str) -> tuple[str, str]:
    """Return ``(law_base_uri, language_code)`` from a language-scoped eli_uri.

    Handles both dated (``…/20250101/de``) and undated (``…/de``) forms.
    Falls back to ``("", "de")`` for unrecognised shapes.
    """
    m = _DATED_URI_RE.match(eli_uri)
    if m:
        return m.group(1), m.group(3)
    m2 = _UNDATED_URI_RE.match(eli_uri)
    if m2:
        return m2.group(1), m2.group(2)
    return "", "de"


# ---------------------------------------------------------------------------
# RDF metadata parser
# ---------------------------------------------------------------------------


def _parse_rdf_metadata(rdf_text: str) -> dict[str, str]:
    """Extract jolux metadata from Fedlex RDF/XML.

    Returns a dict with keys: ``title``, ``title_short``, ``sr_number``,
    ``language``.  Missing fields are empty strings.
    """
    out: dict[str, str] = {
        "title": "",
        "title_short": "",
        "sr_number": "",
        "language": "",
    }
    try:
        root = ET.fromstring(rdf_text)
    except ET.ParseError:
        return out

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
            code = lang_resource.rstrip("/").split("/")[-1].lower()[:2]
            if code in {"de", "fr", "it", "rm", "en"}:
                out["language"] = code

    return out


# ---------------------------------------------------------------------------
# SPARQL helpers
# ---------------------------------------------------------------------------


async def _sparql_get(
    client: httpx.AsyncClient,
    query: str,
) -> dict[str, Any]:
    """Run a SPARQL SELECT query against the Fedlex endpoint.

    Returns the parsed JSON response, or ``{"results": {"bindings": []}}``
    on any error so callers can handle the empty case uniformly.
    """
    try:
        resp = await client.get(
            _SPARQL_ENDPOINT,
            params={"query": query},
            headers={
                "Accept": "application/sparql-results+json",
                "User-Agent": _USER_AGENT,
            },
        )
        resp.raise_for_status()
        return resp.json()
    except Exception as exc:
        logger.warning("fedlex_sparql_error exc=%s", type(exc).__name__)
        return {"results": {"bindings": []}}


async def _find_latest_expression_uri(
    client: httpx.AsyncClient,
    law_base: str,
    lang: str,
) -> tuple[str, str]:
    """Return ``(expression_uri, version_date)`` for the latest **in-force** version.

    "In-force" here means the latest consolidated expression whose date is on
    or before today.  Fedlex regularly publishes future-dated expressions for
    scheduled law changes; using them would produce legal text that is not yet
    legally effective, corrupting the agent's reasoning.

    The upper bound ``{law_base}/{today}/{lang}`` exploits the fact that
    lexicographic ordering of ISO dates (YYYYMMDD) equals chronological order
    when the law base URI prefix is shared — so ``STR(?expr) <= upper_bound``
    is both correct and server-evaluated, keeping the result set minimal.

    Returns ``("", "")`` when no in-force dated expression is found.
    """
    today = date.today().strftime("%Y%m%d")
    upper_bound = f"{law_base}/{today}/{lang}"
    query = f"""
PREFIX jolux: <http://data.legilux.public.lu/resource/ontology/jolux#>
SELECT ?expr WHERE {{
  ?expr a jolux:Expression .
  FILTER(
    STRSTARTS(STR(?expr), "{law_base}/2") &&
    STRENDS(STR(?expr), "/{lang}") &&
    STR(?expr) <= "{upper_bound}"
  )
}}
ORDER BY DESC(STR(?expr))
LIMIT 1
"""
    data = await _sparql_get(client, query)
    bindings = data.get("results", {}).get("bindings", [])
    if not bindings:
        return "", ""
    expr_uri = bindings[0]["expr"]["value"]
    # Extract date segment from .../YYYYMMDD/lang
    date_match = re.search(r"/(\d{8})/[a-z]{2,3}$", expr_uri)
    version_date = date_match.group(1) if date_match else ""
    return expr_uri, version_date


async def _get_html_filestore_url(
    client: httpx.AsyncClient,
    expression_uri: str,
) -> str:
    """Return the single HTML filestore URL for a dated expression.

    Returns ``""`` when SPARQL finds no HTML manifestation.
    """
    query = f"""
PREFIX jolux: <http://data.legilux.public.lu/resource/ontology/jolux#>
SELECT ?file WHERE {{
  <{expression_uri}> jolux:isEmbodiedBy ?manif .
  ?manif jolux:userFormat <{_HTML_USER_FORMAT}> ;
         jolux:isExemplifiedBy ?file .
}}
LIMIT 1
"""
    data = await _sparql_get(client, query)
    bindings = data.get("results", {}).get("bindings", [])
    if not bindings:
        return ""
    return bindings[0].get("file", {}).get("value", "")


# ---------------------------------------------------------------------------
# HTML article extractor
# ---------------------------------------------------------------------------


def _extract_article_block(
    html_text: str,
    article_id: str,
) -> tuple[str, list[dict[str, str]]]:
    """Extract plain text and per-paragraph breakdown from a Fedlex HTML file.

    The Fedlex Casemates renderer wraps each article in::

        <article id="art_697_m"> ... </article>

    with paragraphs inside ``<p class="absatz">`` elements, each leading with
    ``<sup>N</sup>`` giving the paragraph number.

    Returns ``(article_text, paragraphs)`` where:

    - ``article_text`` — plain text of all paragraphs joined by spaces.
    - ``paragraphs`` — ``[{"num": "1", "text": "..."}, …]``.

    Both are empty when the article id is not found in ``html_text``.
    Uses stdlib only (no external HTML-parser dependency).
    """
    # Locate the opening tag.
    art_re = re.compile(
        rf'<article\b[^>]*\bid="{re.escape(article_id)}"[^>]*>', re.I
    )
    m = art_re.search(html_text)
    if not m:
        return "", []

    # Walk forward to find the balancing </article>, respecting nested articles.
    pos = m.end()
    depth = 1
    while pos < len(html_text) and depth > 0:
        nxt_open = html_text.find("<article", pos)
        nxt_close = html_text.find("</article>", pos)
        if nxt_close == -1:
            break
        if nxt_open != -1 and nxt_open < nxt_close:
            depth += 1
            pos = nxt_open + 8
        else:
            depth -= 1
            pos = nxt_close + 10

    article_html = html_text[m.start() : pos]

    # Extract paragraph elements.
    para_re = re.compile(
        r'<p\b[^>]*class="absatz[^"]*"[^>]*>(.*?)</p>', re.S | re.I
    )
    paragraphs: list[dict[str, str]] = []
    all_texts: list[str] = []
    for pm in para_re.finditer(article_html):
        inner = pm.group(1)
        # Paragraph number from leading <sup>N</sup>.
        sup = re.match(r"\s*<sup[^>]*>(\w+)</sup>", inner)
        num = sup.group(1) if sup else str(len(paragraphs) + 1)
        # Strip HTML tags, decode entities, normalise whitespace.
        clean = re.sub(r"<[^>]+>", "", inner)
        clean = html_lib.unescape(clean).replace("\xa0", " ")
        clean = re.sub(r"\s+", " ", clean).strip()
        # Remove leading paragraph-number digit(s) that appear after tag-strip.
        clean = re.sub(r"^[\d]+[a-z]?\s+", "", clean)
        if clean:
            paragraphs.append({"num": num, "text": clean})
            all_texts.append(clean)

    return " ".join(all_texts), paragraphs


# ---------------------------------------------------------------------------
# Core implementation (injectable client for testability)
# ---------------------------------------------------------------------------


async def _fetch_article_impl(
    client: httpx.AsyncClient,
    eli_uri: str,
    article: str | None,
) -> dict[str, Any]:
    """Full implementation of the MCP tool.  Accepts a pre-built client
    so tests can inject a mock transport without touching the public API.
    """
    law_base, lang = _extract_law_base_and_lang(eli_uri)

    # --- Step 1: fetch law-level RDF metadata (title, SR, language) ---
    meta: dict[str, str] = {"title": "", "title_short": "", "sr_number": "", "language": lang}
    try:
        rdf_resp = await client.get(
            eli_uri,
            headers={"Accept": "application/rdf+xml", "User-Agent": _USER_AGENT},
        )
        rdf_resp.raise_for_status()
        meta = _parse_rdf_metadata(rdf_resp.text)
        if not meta["language"]:
            meta["language"] = lang
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
            "language": lang,
            "version_date": "",
            "article": article,
            "article_id": _normalize_article_id(article) if article else None,
            "article_text": "",
            "paragraphs": [],
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
            "language": lang,
            "version_date": "",
            "article": article,
            "article_id": _normalize_article_id(article) if article else None,
            "article_text": "",
            "paragraphs": [],
            "source_url": eli_uri,
            "error": type(exc).__name__,
        }

    # --- Metadata-only path (no article requested) ---
    if not article:
        logger.info(
            "fedlex_rdf_ok eli_uri=%s sr=%s title_short=%s lang=%s",
            eli_uri, meta["sr_number"], meta["title_short"], meta["language"],
        )
        return {
            "eli_uri": eli_uri,
            "title": meta["title"],
            "title_short": meta["title_short"],
            "sr_number": meta["sr_number"],
            "language": meta["language"],
            "version_date": "",
            "article": None,
            "article_id": None,
            "article_text": "",
            "paragraphs": [],
            "source_url": eli_uri,
            "error": None,
        }

    # --- Step 2: discover latest expression + HTML filestore URL ---
    article_id = _normalize_article_id(article)
    expression_uri = ""
    version_date = ""
    html_url = ""
    article_text = ""
    paragraphs: list[dict[str, str]] = []
    fetch_error: str | None = None

    if not law_base:
        fetch_error = "unrecognised_eli_uri_format"
    else:
        expression_uri, version_date = await _find_latest_expression_uri(
            client, law_base, meta["language"] or lang
        )
        if not expression_uri:
            logger.warning(
                "fedlex_no_dated_expression eli_uri=%s lang=%s",
                eli_uri, lang,
            )
            fetch_error = "no_dated_expression_found"
        else:
            html_url = await _get_html_filestore_url(client, expression_uri)
            if not html_url:
                logger.warning(
                    "fedlex_no_html_manifestation expression=%s", expression_uri
                )
                fetch_error = "no_html_manifestation_found"

    # --- Step 3: fetch HTML (with in-process cache) ---
    if html_url and not fetch_error:
        cache_key = (expression_uri, html_url)
        cached = _cache_get(cache_key)
        if cached is not None:
            html_text = cached
            logger.debug(
                "fedlex_html_cache_hit expression=%s article_id=%s",
                expression_uri, article_id,
            )
        else:
            try:
                html_resp = await client.get(
                    html_url,
                    headers={"User-Agent": _USER_AGENT, "Accept": "text/html"},
                )
                html_resp.raise_for_status()
                html_text = html_resp.text
                _cache_set(cache_key, html_text)
                logger.info(
                    "fedlex_html_fetched expression=%s url=%s len=%d",
                    expression_uri, html_url, len(html_text),
                )
            except Exception as exc:
                logger.warning(
                    "fedlex_html_fetch_error expression=%s exc=%s",
                    expression_uri, type(exc).__name__,
                )
                fetch_error = f"html_fetch_{type(exc).__name__}"
                html_text = ""

        if html_text:
            # --- Step 4: extract article block ---
            article_text, paragraphs = _extract_article_block(html_text, article_id)
            if not article_text:
                logger.warning(
                    "fedlex_article_not_found expression=%s article_id=%s",
                    expression_uri, article_id,
                )
                fetch_error = f"article_id_{article_id}_not_found_in_html"

    logger.info(
        "fedlex_ok eli_uri=%s sr=%s article=%s paras=%d error=%s",
        eli_uri, meta["sr_number"], article, len(paragraphs), fetch_error,
    )
    return {
        "eli_uri": eli_uri,
        "title": meta["title"],
        "title_short": meta["title_short"],
        "sr_number": meta["sr_number"],
        "language": meta["language"],
        "version_date": version_date,
        "article": article,
        "article_id": article_id,
        "article_text": article_text,
        "paragraphs": paragraphs,
        "source_url": html_url or eli_uri,
        "error": fetch_error,
    }


# ---------------------------------------------------------------------------
# Public MCP tools
# ---------------------------------------------------------------------------


def qdrant_search(
    query: str,
    sr_number: str,
    article: str,
    canton: str = "CH",
) -> list[dict[str, Any]]:
    """Run the canonical retrieval pipeline for an SR + article + canton.

    Returns the same chunk shape ``engine.verify`` already builds when it
    talks to Claude directly — keeping the wire-format identical means the
    agent's prompt can re-use the existing reasoning rubric without
    translation.

    Each chunk carries ``eli_uri`` and ``paragraph`` (when present in the
    Qdrant payload) so the agent can call ``fetch_fedlex_article`` with the
    ``article`` argument to read the authoritative article text.
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


async def fetch_fedlex_article(
    eli_uri: str,
    article: str | None = None,
) -> dict[str, Any]:
    """Fetch official Swiss law metadata and, optionally, the full article text.

    **Metadata-only** (``article`` omitted or ``None``): returns the law title,
    abbreviation, SR number, and language from the Fedlex RDF/XML endpoint —
    identical to the previous behaviour.

    **Full article text** (``article`` supplied, e.g. ``"697m"``): additionally
    runs two SPARQL queries against ``fedlex.data.admin.ch/sparqlendpoint`` to
    discover the latest in-force consolidated HTML, downloads that file once
    (cached per ``(expression_uri, html_url)``), and extracts the named
    article block by its HTML anchor id (``"art_697_m"``).

    Response shape::

        {
            "eli_uri":      "<input URI>",
            "title":        "<full official law title>",
            "title_short":  "<abbreviation, e.g. OR, ZGB>",
            "sr_number":    "<SR number, e.g. 220>",
            "language":     "<de|fr|it|rm|en>",
            "version_date": "<YYYYMMDD of latest in-force version, or ''>",
            "article":      "<article argument, or null>",
            "article_id":   "<HTML anchor, e.g. art_697_m, or null>",
            "article_text": "<plain text of all paragraphs concatenated>",
            "paragraphs":   [{"num": "1", "text": "..."}, ...],
            "source_url":   "<HTML filestore URL actually fetched>",
            "error":        "<error code string, or null>"
        }

    The agent should compare ``article_text`` with the Qdrant chunk text from
    ``qdrant_search``.  If they differ materially, prefer the Fedlex text and
    note the discrepancy in ``reasoning``.

    Performance budget: warm-cache <50 ms; cold-cache <4 s (one SPARQL to
    find the latest expression, one SPARQL to find the HTML file, one HTML
    download of 2-3 MB for large laws).

    Fedlex API notes:
    - ``fedlex.data.admin.ch/sparqlendpoint`` (not ``/sparql``) supports GET
      with ``?query=`` and returns ``application/sparql-results+json``.
    - The Fedlex portal (www.fedlex.admin.ch) is a JavaScript SPA and returns
      only a noscript stub to plain HTTP clients — this tool uses the
      linked-data API exclusively.
    - Article-level linked-data URIs (``/art.697m``) return 404; article text
      is extracted from the consolidated law HTML.
    """
    async with httpx.AsyncClient(
        follow_redirects=True,
        timeout=_FEDLEX_TIMEOUT_S,
    ) as client:
        return await _fetch_article_impl(client, eli_uri, article)


SERVER = McpServerSpec(
    name="swiss-law-retrieval-mcp",
    tools=(
        McpToolSpec(
            name="qdrant_search",
            description=(
                "Similarity-bounded retrieval over the Qdrant law corpus. "
                "Returns chunks with text, score, language, effective_date, "
                "eli_uri and paragraph. Pass eli_uri + the article argument "
                "to fetch_fedlex_article to get the official live article text."
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
                "Fetch official Swiss law metadata and live article text from "
                "the Fedlex linked-data API. "
                "Pass eli_uri from a qdrant_search chunk and article from the "
                "seed_citation (e.g. '697m', '663b', '7') to receive the full "
                "authoritative article_text and per-paragraph breakdown as "
                "published today on www.fedlex.admin.ch. "
                "Call this for every unique eli_uri returned by qdrant_search "
                "and compare article_text with the Qdrant chunk — if they "
                "differ materially, prefer the Fedlex text and note it in "
                "reasoning."
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
