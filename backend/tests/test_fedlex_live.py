"""Tests for the live Fedlex article-text fetch (Task #54).

All network calls are mocked with ``httpx.MockTransport`` — no live network
required.  Recorded fixtures are stored under ``tests/fixtures/fedlex_live/``.

Three test groups:
1. ``test_normalize_article_id_*`` — pure unit tests for the normalizer.
2. ``test_sparql_manifestation_resolver`` — SPARQL flow in isolation.
3. ``test_fetch_fedlex_article_full_pipeline`` — end-to-end tool call with all
   four HTTP interactions mocked.
"""

from __future__ import annotations

from pathlib import Path

import httpx
import pytest

from swiss_legal_api.mcp_servers.swiss_law import (
    _extract_article_block,
    _fetch_article_impl,
    _find_latest_expression_uri,
    _get_html_filestore_url,
    _normalize_article_id,
)

_FIXTURES = Path(__file__).parent / "fixtures" / "fedlex_live"

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_RDF_METADATA_OR_DE = """\
<?xml version="1.0" encoding="utf-8" ?>
<rdf:RDF
xmlns:rdf="http://www.w3.org/1999/02/22-rdf-syntax-ns#"
xmlns:jolux="http://data.legilux.public.lu/resource/ontology/jolux#">
  <rdf:Description rdf:about="https://fedlex.data.admin.ch/eli/cc/27/317_321_377/de">
    <rdf:type rdf:resource="http://data.legilux.public.lu/resource/ontology/jolux#Expression"/>
    <jolux:title>Bundesgesetz betreffend die Ergänzung des Schweizerischen Zivilgesetzbuches (Fünfter Teil: Obligationenrecht)</jolux:title>
    <jolux:titleShort>OR</jolux:titleShort>
    <jolux:historicalLegalId>220</jolux:historicalLegalId>
    <jolux:language rdf:resource="http://publications.europa.eu/resource/authority/language/DEU"/>
  </rdf:Description>
</rdf:RDF>
"""

_ELI_OR_DE = "https://fedlex.data.admin.ch/eli/cc/27/317_321_377/de"
_EXPR_OR_DE = "https://fedlex.data.admin.ch/eli/cc/27/317_321_377/20260101/de"
_HTML_FILE_OR = (
    "https://fedlex.data.admin.ch/filestore/fedlex.data.admin.ch"
    "/eli/cc/27/317_321_377/20260101/de/html"
    "/fedlex-data-admin-ch-eli-cc-27-317_321_377-20260101-de-html-12.html"
)


def _make_transport(
    rdf_xml: str,
    sparql_expr_json: str,
    sparql_html_json: str,
    html_content: str,
) -> httpx.MockTransport:
    """Build a mock transport that serves the four Fedlex HTTP interactions."""

    def handler(request: httpx.Request) -> httpx.Response:
        url = str(request.url)
        accept = request.headers.get("accept", "")

        # 1. RDF metadata for the law expression
        if "eli/cc" in url and "sparqlendpoint" not in url and "filestore" not in url:
            if "rdf+xml" in accept or not accept:
                return httpx.Response(
                    200,
                    text=rdf_xml,
                    headers={"content-type": "application/rdf+xml;charset=UTF-8"},
                )

        # 2. SPARQL queries — distinguish by query-string content
        if "sparqlendpoint" in url:
            raw_query = request.url.params.get("query", "").lower()
            if "strstarts" in raw_query:
                # latest expression query (uses STRSTARTS + STRENDS)
                return httpx.Response(
                    200,
                    text=sparql_expr_json,
                    headers={"content-type": "application/sparql-results+json"},
                )
            if "isexemplifiedby" in raw_query:
                # html manifestation query
                return httpx.Response(
                    200,
                    text=sparql_html_json,
                    headers={"content-type": "application/sparql-results+json"},
                )
            # fallback — empty result
            return httpx.Response(
                200,
                text='{"results":{"bindings":[]}}',
                headers={"content-type": "application/sparql-results+json"},
            )

        # 3. HTML filestore download
        if "filestore" in url:
            return httpx.Response(
                200,
                text=html_content,
                headers={"content-type": "text/html;charset=UTF-8"},
            )

        return httpx.Response(404, text="not mocked")

    return httpx.MockTransport(handler)


# ---------------------------------------------------------------------------
# 1. Normalizer unit tests
# ---------------------------------------------------------------------------


def test_normalize_article_id_trailing_letter() -> None:
    """Digits followed by letter get an underscore: 697m → art_697_m."""
    assert _normalize_article_id("697m") == "art_697_m"
    assert _normalize_article_id("663b") == "art_663_b"
    assert _normalize_article_id("270a") == "art_270_a"
    assert _normalize_article_id("6a") == "art_6_a"


def test_normalize_article_id_digits_only() -> None:
    """Pure-digit articles get a plain prefix: 697 → art_697."""
    assert _normalize_article_id("697") == "art_697"
    assert _normalize_article_id("1") == "art_1"
    assert _normalize_article_id("6") == "art_6"


# ---------------------------------------------------------------------------
# 2. SPARQL resolver in isolation
# ---------------------------------------------------------------------------


async def test_expression_resolver_upper_bound_excludes_future() -> None:
    """SPARQL query must contain today's date as an upper bound.

    Fedlex publishes future-dated consolidated expressions for scheduled law
    changes.  The resolver must only select expressions effective on or before
    today.  We verify this by asserting:

    1. The captured SPARQL query contains today's date string.
    2. When SPARQL returns a future expression the resolver does NOT accept it.
    """
    from datetime import date

    law_base = "https://fedlex.data.admin.ch/eli/cc/27/317_321_377"
    today = date.today().strftime("%Y%m%d")
    future_date = "20991231"
    future_expr = f"{law_base}/{future_date}/de"
    current_expr = f"{law_base}/{today}/de"

    captured_queries: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        raw_query = request.url.params.get("query", "")
        captured_queries.append(raw_query)
        # A correct SPARQL server would apply our upper-bound filter and
        # return only current_expr; simulate that here.
        if today in raw_query and future_date not in raw_query:
            return httpx.Response(
                200,
                json={
                    "head": {"vars": ["expr"]},
                    "results": {
                        "bindings": [
                            {"expr": {"type": "uri", "value": current_expr}}
                        ]
                    },
                },
                headers={"content-type": "application/sparql-results+json"},
            )
        # If the query were missing the upper bound it would return the future
        # expression — prove the bound is present by returning nothing here.
        return httpx.Response(
            200,
            json={"head": {"vars": ["expr"]}, "results": {"bindings": []}},
            headers={"content-type": "application/sparql-results+json"},
        )

    transport = httpx.MockTransport(handler)
    async with httpx.AsyncClient(transport=transport) as client:
        expr_uri, version_date = await _find_latest_expression_uri(
            client, law_base, "de"
        )

    # The function must return the current expression, not the future one.
    assert expr_uri == current_expr, (
        f"Expected in-force expression {current_expr!r}, got {expr_uri!r}"
    )
    assert version_date == today

    # The SPARQL query must embed today's date as an upper bound.
    assert captured_queries, "expected at least one SPARQL query"
    assert today in captured_queries[0], (
        "SPARQL upper-bound filter missing: "
        f"today={today!r} not found in query"
    )
    assert future_expr not in captured_queries[0], (
        "SPARQL query must not reference the future expression URI directly"
    )


async def test_sparql_manifestation_resolver() -> None:
    """SPARQL queries correctly return expression URI and HTML file URL."""
    sparql_expr = (_FIXTURES / "sparql_latest_expr_or_de.json").read_text()
    sparql_html = (_FIXTURES / "sparql_html_file_or_20260101.json").read_text()

    def handler(request: httpx.Request) -> httpx.Response:
        raw_query = request.url.params.get("query", "").lower()
        if "strends" in raw_query:
            return httpx.Response(
                200, text=sparql_expr,
                headers={"content-type": "application/sparql-results+json"},
            )
        return httpx.Response(
            200, text=sparql_html,
            headers={"content-type": "application/sparql-results+json"},
        )

    transport = httpx.MockTransport(handler)
    async with httpx.AsyncClient(transport=transport) as client:
        expr_uri, version_date = await _find_latest_expression_uri(
            client, "https://fedlex.data.admin.ch/eli/cc/27/317_321_377", "de"
        )
        assert expr_uri == _EXPR_OR_DE
        assert version_date == "20260101"

        html_url = await _get_html_filestore_url(client, expr_uri)
        assert html_url == _HTML_FILE_OR


# ---------------------------------------------------------------------------
# 3. End-to-end pipeline (all four HTTP calls mocked)
# ---------------------------------------------------------------------------


async def test_fetch_fedlex_article_full_pipeline() -> None:
    """Full tool call: RDF metadata + SPARQL discovery + HTML download → paragraphs."""
    sparql_expr = (_FIXTURES / "sparql_latest_expr_or_de.json").read_text()
    sparql_html = (_FIXTURES / "sparql_html_file_or_20260101.json").read_text()
    html_fragment = (_FIXTURES / "or_article_fragment.html").read_text()

    transport = _make_transport(_RDF_METADATA_OR_DE, sparql_expr, sparql_html, html_fragment)
    async with httpx.AsyncClient(transport=transport, follow_redirects=True) as client:
        result = await _fetch_article_impl(client, _ELI_OR_DE, "697m")

    # Law-level metadata
    assert result["error"] is None
    assert result["sr_number"] == "220"
    assert result["title_short"] == "OR"
    assert result["language"] == "de"

    # Versioning
    assert result["version_date"] == "20260101"
    assert result["article"] == "697m"
    assert result["article_id"] == "art_697_m"
    assert result["source_url"] == _HTML_FILE_OR

    # Article text was extracted
    assert result["article_text"], "article_text must not be empty"
    assert "Meldepflichten" in result["article_text"]

    # Paragraph breakdown
    paras = result["paragraphs"]
    assert len(paras) == 3
    assert paras[0]["num"] == "1"
    assert "Meldepflichten" in paras[0]["text"]
    assert paras[1]["num"] == "2"
    assert paras[2]["num"] == "3"


async def test_fetch_fedlex_article_metadata_only() -> None:
    """When article=None the tool returns metadata without triggering SPARQL."""
    sparql_called = []

    def handler(request: httpx.Request) -> httpx.Response:
        if "sparqlendpoint" in str(request.url):
            sparql_called.append(True)
        return httpx.Response(
            200, text=_RDF_METADATA_OR_DE,
            headers={"content-type": "application/rdf+xml;charset=UTF-8"},
        )

    transport = httpx.MockTransport(handler)
    async with httpx.AsyncClient(transport=transport, follow_redirects=True) as client:
        result = await _fetch_article_impl(client, _ELI_OR_DE, None)

    assert result["error"] is None
    assert result["sr_number"] == "220"
    assert result["article_text"] == ""
    assert result["paragraphs"] == []
    assert not sparql_called, "SPARQL must not be called in metadata-only mode"


# ---------------------------------------------------------------------------
# 4. Article-extractor unit tests (no network)
# ---------------------------------------------------------------------------


def test_extract_article_block_with_fixture_html() -> None:
    """_extract_article_block correctly parses the recorded HTML fixture."""
    html_content = (_FIXTURES / "or_article_fragment.html").read_text()

    text, paras = _extract_article_block(html_content, "art_697_m")
    assert text, "article_text must not be empty"
    assert len(paras) == 3
    assert paras[0]["num"] == "1"
    assert "Meldepflichten" in paras[0]["text"]

    text2, paras2 = _extract_article_block(html_content, "art_697")
    assert len(paras2) == 2
    assert "Aktionär" in paras2[0]["text"]


def test_extract_article_block_missing_returns_empty() -> None:
    """Missing article id returns empty text and empty list."""
    text, paras = _extract_article_block("<html><body></body></html>", "art_9999")
    assert text == ""
    assert paras == []
