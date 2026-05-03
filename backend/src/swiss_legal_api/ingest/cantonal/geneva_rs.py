"""Geneva (GE) — Recueil systématique genevois (RSG) adapter.

Geneva publishes the RSG with two complementary surfaces:

  * **OData feed** — ``https://ge.ch/legislation/rsg/odata/Acts`` is the
    official machine-readable catalogue. Each ``<entry>`` describes one
    act (compilation ID, title, effective date, repeal status, link to
    the per-act XML view). We prefer this in production because it ships
    structured metadata; the HTML pages are a stable fallback.
  * **lexfind.ch / ge.ch HTML pages** — per-act pages with the
    ``<div class="rsg-article">`` structure we parse below. Used for
    full text extraction once OData has told us which acts are in
    force.

Compilation IDs in RSG use a letter + numeric pattern (e.g.
``"A 2 05"`` for the constitution, ``"E 5 05"`` for the LIPP/income tax
act). We encode the ID as ``A2.05`` (drop spaces, dot before the last
group) so the loosened ``Citation.sr_number`` regex accepts it and the
shape stays human-readable in URLs and payloads.

Parser shape (HTML):

  * ``<div class="rsg-article" data-art="N">`` per article.
  * ``<h3 class="rsg-art-num">Art. N</h3>`` per article header.
  * ``<div class="rsg-alinea" data-al="K">`` per paragraph (alinéa).
  * Optional ``<div class="rsg-abrogated">…</div>`` repeal marker.

Parser shape (OData feed) — Atom XML with ``ge:Act`` entries:

  * ``<entry><id>…/Acts(<id>)</id></entry>``
  * ``<m:properties>`` containing ``<d:CompilationId>``,
    ``<d:Language>``, ``<d:EffectiveDate>``, ``<d:Status>``,
    ``<d:HtmlUrl>``.
"""

from __future__ import annotations

import logging
import re
import xml.etree.ElementTree as ET
from collections.abc import Iterable
from dataclasses import dataclass, replace
from html.parser import HTMLParser
from urllib.parse import urljoin

import httpx

from .base import CantonalArticleRecord

logger = logging.getLogger(__name__)

CANTON = "GE"
COMPILATION_LABEL = "RSG (Recueil systématique genevois)"
_REPEALED_FAR_FUTURE = "9999-12-31"


@dataclass(frozen=True)
class _GEArticleSpec:
    url: str
    compilation_id: str
    language: str = "fr"
    effective_date: str | None = None


def encode_compilation_id(raw: str) -> str:
    """``"A 2 05"`` -> ``"A2.05"``.

    Geneva's published IDs use spaces as separators, but the seed schema
    requires the loosened ``sr_number`` regex (``^[A-Z]*\\d+(\\.\\d+)?$``).
    We drop the spaces and join the trailing pair with a dot — this is
    a pure encoding step, the canton + compilation_id pair is still
    unique. Inverse for display lives in the frontend's citation renderer.
    """
    parts = raw.strip().split()
    if not parts:
        return raw
    if len(parts) == 1:
        return parts[0]
    # Letter prefix(es) merged with the first numeric group, then dot,
    # then the rest joined without separator (typical Geneva IDs are 3
    # tokens: letter + 2 digits).
    head = "".join(parts[:-1])
    tail = parts[-1]
    return f"{head}.{tail}"


class _RSGActParser(HTMLParser):
    """Walk a Geneva RSG act page collecting per-paragraph records.

    Two depth counters track structural nesting independently:

      * ``_article_div_depth`` — depth of the open ``rsg-article`` div
        (closes the article when it returns to 0).
      * ``_alinea_div_depth`` — depth of the open ``rsg-alinea`` div
        (flushes the buffered text when it returns to 0). Tracking
        depth per-alinéa rather than per-article means nested ``<div>``
        wrappers inside an alinéa (links, tables, footnote markers)
        no longer flush text early, which would otherwise drop or
        split paragraph content.

    Repeal status is captured at article scope and applied retroactively
    when the article closes, so a ``<div class="rsg-abrogated">`` marker
    that follows the alinéas still flags every paragraph as repealed.
    """

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self._records: list[tuple[str, str, str, bool]] = []
        # Per-article paragraph buffer: emitted on article close so a
        # repeal marker that appears anywhere inside the article still
        # gets applied to every paragraph.
        self._article_buffer: list[tuple[str, str, str]] = []
        self._cur_article: str | None = None
        self._cur_paragraph: str | None = None
        self._buf: list[str] = []
        self._cur_repealed = False
        self._article_div_depth = 0
        self._alinea_div_depth = 0

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag != "div":
            return
        attr = {k: (v or "") for k, v in attrs}
        cls_set = attr.get("class", "").split()
        if "rsg-article" in cls_set:
            # New article opens — close any in-flight one first.
            self._close_article()
            self._cur_article = (attr.get("data-art") or "").strip() or None
            self._cur_repealed = False
            self._article_div_depth = 1
            self._alinea_div_depth = 0
        elif "rsg-alinea" in cls_set and self._cur_article:
            # Alinéa opens. Flush any predecessor first (covers the rare
            # case of two adjacent alinéa divs without a wrapper between).
            self._flush_alinea()
            self._cur_paragraph = (attr.get("data-al") or "1") or "1"
            self._alinea_div_depth = 1
            self._article_div_depth += 1
        elif "rsg-abrogated" in cls_set and self._cur_article:
            self._cur_repealed = True
            self._article_div_depth += 1
        elif self._article_div_depth > 0:
            # Any other nested <div> inside the article — track depth so
            # the article-close logic stays balanced.
            self._article_div_depth += 1
            if self._alinea_div_depth > 0:
                self._alinea_div_depth += 1

    def handle_endtag(self, tag: str) -> None:
        if tag != "div" or self._article_div_depth == 0:
            return
        if self._alinea_div_depth > 0:
            self._alinea_div_depth -= 1
            if self._alinea_div_depth == 0:
                # The actual alinéa wrapper just closed — emit buffered text.
                self._flush_alinea()
        self._article_div_depth -= 1
        if self._article_div_depth == 0:
            self._close_article()

    def handle_data(self, data: str) -> None:
        if self._alinea_div_depth > 0:
            self._buf.append(data)

    def _flush_alinea(self) -> None:
        """Move accumulated text from ``_buf`` into the article buffer."""
        text = " ".join("".join(self._buf).split())
        if self._cur_article and self._cur_paragraph and text:
            self._article_buffer.append((self._cur_article, self._cur_paragraph, text))
        self._buf = []
        self._cur_paragraph = None

    def _close_article(self) -> None:
        """Emit the article's buffered paragraphs with the final repeal flag."""
        # Drain any in-flight alinéa text first (defensive — well-formed
        # RSG always closes alinéa before the article div, but malformed
        # markup shouldn't lose data).
        if self._alinea_div_depth > 0:
            self._flush_alinea()
            self._alinea_div_depth = 0
        for article, paragraph, text in self._article_buffer:
            self._records.append((article, paragraph, text, self._cur_repealed))
        self._article_buffer = []
        self._cur_article = None
        self._cur_paragraph = None
        self._cur_repealed = False
        self._article_div_depth = 0

    def close(self) -> None:
        # HTMLParser.close() is the end-of-stream hook — make sure any
        # article still open at EOF still emits its records.
        super().close()
        if self._cur_article is not None:
            self._close_article()

    @property
    def records(self) -> list[tuple[str, str, str, bool]]:
        return self._records


_ART_NORMALISER = re.compile(r"\s+")


def parse_articles(
    html: str,
    *,
    compilation_id: str,
    language: str,
    source_url: str,
    effective_date: str | None,
) -> list[CantonalArticleRecord]:
    """Parse one Geneva RSG act page into per-paragraph records.

    The compilation ID is expected pre-encoded via
    :func:`encode_compilation_id` (e.g. ``"A2.05"`` for ``"A 2 05"``).
    Repealed articles surface with ``repealed_date=9999-12-31``.
    """
    parser = _RSGActParser()
    parser.feed(html)
    parser.close()
    encoded = encode_compilation_id(compilation_id)
    out: list[CantonalArticleRecord] = []
    for article, paragraph, text, repealed in parser.records:
        out.append(
            CantonalArticleRecord(
                canton=CANTON,
                compilation_id=encoded,
                article=_ART_NORMALISER.sub("", article),
                paragraph=paragraph,
                language=language,
                text=text,
                source_url=source_url,
                effective_date=effective_date,
                repealed_date=_REPEALED_FAR_FUTURE if repealed else None,
            )
        )
    return out


def ingest(
    specs: Iterable[_GEArticleSpec],
    *,
    client: httpx.Client | None = None,
) -> list[CantonalArticleRecord]:
    own_client = client is None
    http = client if client is not None else httpx.Client(timeout=30.0)
    try:
        out: list[CantonalArticleRecord] = []
        for spec in specs:
            resp = http.get(spec.url)
            resp.raise_for_status()
            out.extend(
                parse_articles(
                    resp.text,
                    compilation_id=spec.compilation_id,
                    language=spec.language,
                    source_url=spec.url,
                    effective_date=spec.effective_date,
                )
            )
        return out
    finally:
        if own_client:
            http.close()


# ----- OData catalogue discovery ----------------------------------------

RSG_ODATA_URL = "https://ge.ch/legislation/rsg/odata/Acts"

# Atom/OData namespaces used by the Geneva feed. Captured here so the
# parser is robust to the canton occasionally rev-ing the OData minor
# version (the namespace URIs are part of the OData v2 spec).
_ATOM_NS = "http://www.w3.org/2005/Atom"
_ODATA_M_NS = "http://schemas.microsoft.com/ado/2007/08/dataservices/metadata"
_ODATA_D_NS = "http://schemas.microsoft.com/ado/2007/08/dataservices"

_RSG_REPEAL_STATUSES = {"abrogated", "abrogé", "repealed"}


def _odata_prop(props: ET.Element, name: str) -> str:
    """Read one ``<d:Name>`` text node from an OData ``<m:properties>``."""
    el = props.find(f"./{{{_ODATA_D_NS}}}{name}")
    return (el.text or "").strip() if el is not None else ""


def parse_odata_feed(xml_text: str) -> list[_GEArticleSpec]:
    """Pure parser: an OData Atom feed -> list of in-force-act specs.

    Skips entries with status in :data:`_RSG_REPEAL_STATUSES` so the
    discovered spec list stays scoped to currently in-force law.
    Compilation IDs from the feed are ALREADY in encoded form
    (``A2.05``) per Geneva's OData contract — we keep them unchanged.
    """
    root = ET.fromstring(xml_text)
    entries = root.findall(f".//{{{_ATOM_NS}}}entry")
    out: list[_GEArticleSpec] = []
    for entry in entries:
        props = entry.find(f"./{{{_ATOM_NS}}}content/{{{_ODATA_M_NS}}}properties")
        if props is None:
            continue
        if _odata_prop(props, "Status").lower() in _RSG_REPEAL_STATUSES:
            continue
        compilation_id = _odata_prop(props, "CompilationId")
        html_url = _odata_prop(props, "HtmlUrl")
        if not compilation_id or not html_url:
            continue
        out.append(
            _GEArticleSpec(
                url=html_url,
                compilation_id=compilation_id,
                language=_odata_prop(props, "Language") or "fr",
                effective_date=_odata_prop(props, "EffectiveDate") or None,
            )
        )
    return out


# HTML catalogue fallback — used when the OData feed is unreachable.
# The Geneva chancellery also publishes the RSG index as an HTML page on
# ge.ch with one ``<a class="rsgentry" data-rsg=… data-status=…
# data-effective=… data-language=… href=…>`` per act, mirroring the
# ZH/BE index conventions. We never silently drop discovery — we try
# OData first, fall back to HTML, and only fall back to the inline
# starter spec list (in __main__) if both surfaces are unreachable.
RSG_HTML_INDEX_URL = "https://www.ge.ch/legislation/rsg/"


class _RSGHtmlIndexParser(HTMLParser):
    """Walk the ge.ch HTML RSG catalogue and collect in-force entries."""

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.entries: list[_GEArticleSpec] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag != "a":
            return
        attr = {k: (v or "") for k, v in attrs}
        if "rsgentry" not in attr.get("class", "").split():
            return
        if attr.get("data-status", "in_force") != "in_force":
            return
        rsg = attr.get("data-rsg", "").strip()
        href = attr.get("href", "").strip()
        if not rsg or not href:
            return
        self.entries.append(
            _GEArticleSpec(
                url=href,
                compilation_id=rsg,
                language=attr.get("data-language", "fr") or "fr",
                effective_date=attr.get("data-effective") or None,
            )
        )


def parse_html_index(html: str, *, base_url: str = RSG_HTML_INDEX_URL) -> list[_GEArticleSpec]:
    """Pure parser: ge.ch HTML RSG index -> list of in-force-act specs.

    Relative ``href`` values are resolved against ``base_url`` so the
    fallback path is just as resilient as the OData primary.
    """
    p = _RSGHtmlIndexParser()
    p.feed(html)
    p.close()
    return [replace(spec, url=urljoin(base_url, spec.url)) for spec in p.entries]


def discover_specs(
    *,
    odata_url: str = RSG_ODATA_URL,
    html_index_url: str = RSG_HTML_INDEX_URL,
    client: httpx.Client | None = None,
) -> list[_GEArticleSpec]:
    """Fetch the RSG catalogue, OData first, HTML index as fallback.

    Per the canton-adapter contract: OData is the official
    machine-readable surface, HTML index is the resilient backup. We
    surface the OData failure via :mod:`logging` so operators see when
    the canton is shedding traffic to the HTML page; the function only
    raises if BOTH surfaces fail (in which case ``__main__`` falls back
    to the inline starter spec list).
    """
    own_client = client is None
    http = client if client is not None else httpx.Client(timeout=30.0)
    try:
        try:
            resp = http.get(odata_url, headers={"Accept": "application/atom+xml"})
            resp.raise_for_status()
            return parse_odata_feed(resp.text)
        except (httpx.HTTPError, ET.ParseError) as exc:
            logger.warning(
                "rsg_odata_unavailable url=%s err=%s — falling back to HTML index",
                odata_url,
                exc,
            )
        resp = http.get(html_index_url)
        resp.raise_for_status()
        return parse_html_index(resp.text, base_url=str(resp.url))
    finally:
        if own_client:
            http.close()


ArticleSpec = _GEArticleSpec
