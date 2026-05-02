"""Bern (BE) — Bernische Systematische Gesetzessammlung (BSG) adapter.

Bern publishes BSG under ``https://www.belex.sites.be.ch/`` with two
surfaces:

  * The catalogue index at ``/data/index/de`` listing every in-force
    act with its BSG number, title, MIME type (``text/html`` vs
    ``application/pdf``), and a link to the act page. We parse this
    and emit one :class:`ArticleSpec` per in-force entry.
  * Per-act pages: HTML for the modern majority, PDF for a small tail
    of older transitional decrees (mostly from the 1980s) that were
    never re-typeset.

HTML parser shape:

  * ``<div class="article" data-article="N">`` per article.
  * ``<h3>Art. N</h3>`` (or ``§ N`` for older statutes).
  * ``<p data-paragraph="K">`` per paragraph.
  * Optional ``<p class="status" data-status="aufgehoben">…</p>`` marker
    for repealed articles (we treat any non-empty status of "aufgehoben"
    or "abrogated" as a repeal banner).

PDF fallback shape: BSG PDFs follow a stable lectern format —
``Art. N`` heading lines, then optional ``1`` / ``2`` / ``3`` arabic
paragraph numerals at the start of each Absatz. We extract the page
text via :mod:`pypdf` (already a project dependency for the curriculum
chunker), then split into article+paragraph rows with
:func:`parse_pdf_text`. Repeal-banner detection mirrors the HTML path
("aufgehoben" / "abrogated" markers anywhere in the article body flag
every paragraph as repealed).
"""
from __future__ import annotations

import io
import logging
import re
from collections.abc import Iterable
from dataclasses import dataclass
from html.parser import HTMLParser

import httpx

from .base import CantonalArticleRecord

logger = logging.getLogger(__name__)

CANTON = "BE"
COMPILATION_LABEL = "BSG (Bernische Systematische Gesetzessammlung)"
_REPEALED_FAR_FUTURE = "9999-12-31"
_REPEAL_MARKERS = {"aufgehoben", "abrogated", "abrogé"}


@dataclass(frozen=True)
class _BEArticleSpec:
    url: str
    compilation_id: str
    language: str = "de"
    effective_date: str | None = None
    # Set by ``discover_specs`` when the catalogue index marks the act
    # as PDF-only. Lets ``ingest`` short-circuit content-type sniffing
    # for entries that don't even bother sending the right header.
    is_pdf: bool = False


class _BSGActParser(HTMLParser):
    """Walk a BSG act page collecting per-paragraph records.

    Differences from the ZH parser: the article wrapper is ``<div>`` not
    ``<section>``, paragraph data attribute is ``data-paragraph`` not
    ``data-abs``, and the repeal banner is conveyed via a status attr on
    a sibling ``<p>`` (because BSG ships the original article body
    alongside the repeal notice).

    Repeal status is captured at article scope and applied retroactively
    on article close: BSG sometimes emits the status marker AFTER the
    paragraphs (especially in older Belex pages), so emitting eagerly
    would leak un-flagged paragraphs through the repeal guardrail.
    """

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self._records: list[tuple[str, str, str, bool]] = []
        # Per-article buffer — drained on article close so the repeal
        # flag can be applied no matter where in the article the
        # ``<p class="status">`` marker appears.
        self._article_buffer: list[tuple[str, str, str]] = []
        self._cur_article: str | None = None
        self._cur_paragraph: str | None = None
        self._buf: list[str] = []
        self._in_para = False
        self._article_repealed = False

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        attr = {k: (v or "") for k, v in attrs}
        cls = attr.get("class", "")
        if tag == "div" and "article" in cls.split():
            # New article opens — drain the previous one first.
            self._close_article()
            self._cur_article = (attr.get("data-article") or "").strip() or None
            self._cur_paragraph = None
            self._article_repealed = False
        elif tag == "p":
            cls_set = cls.split()
            if "status" in cls_set:
                status = (attr.get("data-status") or "").strip().lower()
                if status in _REPEAL_MARKERS:
                    self._article_repealed = True
            elif self._cur_article and "data-paragraph" in attr:
                self._flush_paragraph()
                self._cur_paragraph = attr.get("data-paragraph", "1") or "1"
                self._in_para = True

    def handle_endtag(self, tag: str) -> None:
        # Both <p> and <div> close the in-flight paragraph buffer; we
        # don't reset article context on </div> because BSG nests divs
        # frequently (figures, footnotes), so the next article-class
        # <div> opens a new context via _close_article instead.
        if tag in ("p", "div") and self._in_para:
            self._flush_paragraph()

    def handle_data(self, data: str) -> None:
        if self._in_para:
            self._buf.append(data)

    def _flush_paragraph(self) -> None:
        """Move the in-flight paragraph from ``_buf`` to the article buffer."""
        if not self._in_para:
            return
        text = " ".join("".join(self._buf).split())
        if self._cur_article and self._cur_paragraph and text:
            self._article_buffer.append(
                (self._cur_article, self._cur_paragraph, text)
            )
        self._buf = []
        self._in_para = False

    def _close_article(self) -> None:
        """Emit buffered paragraphs with the final article-scope repeal flag."""
        self._flush_paragraph()
        for article, paragraph, text in self._article_buffer:
            self._records.append((article, paragraph, text, self._article_repealed))
        self._article_buffer = []
        self._cur_article = None
        self._cur_paragraph = None
        self._article_repealed = False

    def close(self) -> None:
        # End-of-stream hook — drain whatever article is still open.
        super().close()
        if self._cur_article is not None:
            self._close_article()

    @property
    def records(self) -> list[tuple[str, str, str, bool]]:
        return self._records


def parse_articles(
    html: str,
    *,
    compilation_id: str,
    language: str,
    source_url: str,
    effective_date: str | None,
) -> list[CantonalArticleRecord]:
    """Parse one BSG act page into per-paragraph records.

    The compilation ID is the BSG number (e.g. ``"661.11"`` for the
    Mietverfahrensverordnung). Articles flagged ``aufgehoben`` surface
    with ``repealed_date=9999-12-31`` (same convention as ZH-Lex).
    """
    parser = _BSGActParser()
    parser.feed(html)
    parser.close()
    out: list[CantonalArticleRecord] = []
    for article, paragraph, text, repealed in parser.records:
        out.append(
            CantonalArticleRecord(
                canton=CANTON,
                compilation_id=compilation_id,
                article=article,
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
    specs: Iterable[_BEArticleSpec],
    *,
    client: httpx.Client | None = None,
) -> list[CantonalArticleRecord]:
    """Drive HTML / PDF parsers over the supplied specs.

    Content-type sniffing routes each response: ``application/pdf`` (or a
    spec marked ``is_pdf=True`` from the index) goes through
    :func:`parse_pdf_articles`, everything else through HTML.
    """
    own_client = client is None
    http = client if client is not None else httpx.Client(timeout=30.0)
    try:
        out: list[CantonalArticleRecord] = []
        for spec in specs:
            resp = http.get(spec.url)
            resp.raise_for_status()
            content_type = resp.headers.get("content-type", "").lower()
            if spec.is_pdf or "pdf" in content_type:
                try:
                    out.extend(
                        parse_pdf_articles(
                            resp.content,
                            compilation_id=spec.compilation_id,
                            language=spec.language,
                            source_url=spec.url,
                            effective_date=spec.effective_date,
                        )
                    )
                except Exception:
                    # Never let one malformed PDF abort the whole run —
                    # log + skip is better than partial corpus loss.
                    logger.exception(
                        "bsg_pdf_parse_failed compilation=%s url=%s",
                        spec.compilation_id, spec.url,
                    )
                continue
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


# ----- PDF fallback -----------------------------------------------------

# An "Art. N" header — accepts both numeric-only ("Art. 11") and
# letter-suffix ("Art. 11a") article numbers. The whole-line anchor is
# enforced by the splitter, not the regex itself.
_PDF_ART_HEADER = re.compile(r"^\s*(?:Art\.|§)\s+(\d+[a-z]?)\b\s*$")
# Paragraph numeral as it appears at the start of an Absatz. BSG PDFs
# use either ASCII digits ("1") or superscript form ("¹") depending on
# the typesetter; both render to "1" / "2" / … when pypdf extracts.
_PDF_PARA_NUM = re.compile(r"^\s*(\d+)\s+(.*)$")


def parse_pdf_text(
    text: str,
    *,
    compilation_id: str,
    language: str,
    source_url: str,
    effective_date: str | None,
) -> list[CantonalArticleRecord]:
    """Split already-extracted PDF text into per-paragraph records.

    Algorithm:
      1) Walk lines top-to-bottom.
      2) ``Art. N`` (or ``§ N``) on its own line opens a new article.
      3) Lines starting with an arabic paragraph numeral start a new
         Absatz; subsequent lines without a numeral concatenate into the
         current Absatz until either the next numeral or the next
         article header.
      4) "aufgehoben" / "abrogated" anywhere inside an article flags
         every paragraph in that article as repealed (article-scope,
         applied at article close — same convention as the HTML parser).

    Pure function — :func:`parse_pdf_articles` is the wrapper that calls
    :mod:`pypdf` first.
    """
    records: list[tuple[str, str, str, bool]] = []
    cur_article: str | None = None
    cur_paragraph: str | None = None
    article_buffer: list[tuple[str, str, str]] = []
    para_lines: list[str] = []
    article_repealed = False

    def flush_paragraph() -> None:
        nonlocal cur_paragraph, para_lines
        if cur_article and cur_paragraph and para_lines:
            joined = " ".join(" ".join(para_lines).split())
            if joined:
                article_buffer.append((cur_article, cur_paragraph, joined))
        para_lines = []
        cur_paragraph = None

    def close_article() -> None:
        nonlocal cur_article, article_repealed, article_buffer
        flush_paragraph()
        for art, para, body in article_buffer:
            records.append((art, para, body, article_repealed))
        article_buffer = []
        cur_article = None
        article_repealed = False

    for raw in text.splitlines():
        line = raw.strip()
        if not line:
            continue
        m_art = _PDF_ART_HEADER.match(line)
        if m_art:
            close_article()
            cur_article = m_art.group(1)
            continue
        if not cur_article:
            continue
        if "aufgehoben" in line.lower() or "abrogated" in line.lower():
            article_repealed = True
        m_para = _PDF_PARA_NUM.match(line)
        if m_para:
            flush_paragraph()
            cur_paragraph = m_para.group(1)
            para_lines = [m_para.group(2)]
        elif cur_paragraph is None:
            # Implicit single-paragraph article (no numeral): synthesise §1.
            cur_paragraph = "1"
            para_lines = [line]
        else:
            para_lines.append(line)

    close_article()

    out: list[CantonalArticleRecord] = []
    for article, paragraph, body, repealed in records:
        out.append(
            CantonalArticleRecord(
                canton=CANTON,
                compilation_id=compilation_id,
                article=article,
                paragraph=paragraph,
                language=language,
                text=body,
                source_url=source_url,
                effective_date=effective_date,
                repealed_date=_REPEALED_FAR_FUTURE if repealed else None,
            )
        )
    return out


def extract_pdf_text(pdf_bytes: bytes) -> str:
    """Concatenate page text from a BSG PDF using :mod:`pypdf`.

    Kept as a thin separate function so :func:`parse_pdf_text` is
    testable without a binary fixture (the heavy lifting is the
    line-level splitter, not pypdf itself).
    """
    # Local import keeps cantonal package import-time cheap when nobody
    # is exercising the PDF path.
    from pypdf import PdfReader

    reader = PdfReader(io.BytesIO(pdf_bytes))
    pages: list[str] = []
    for page in reader.pages:
        pages.append(page.extract_text() or "")
    return "\n".join(pages)


def parse_pdf_articles(
    pdf_bytes: bytes,
    *,
    compilation_id: str,
    language: str,
    source_url: str,
    effective_date: str | None,
) -> list[CantonalArticleRecord]:
    """End-to-end: BSG PDF bytes -> per-paragraph records."""
    return parse_pdf_text(
        extract_pdf_text(pdf_bytes),
        compilation_id=compilation_id,
        language=language,
        source_url=source_url,
        effective_date=effective_date,
    )


# ----- Catalogue index discovery -----------------------------------------

BSG_INDEX_URL = "https://www.belex.sites.be.ch/data/index/de"


class _BSGIndexParser(HTMLParser):
    """Walk the BSG catalogue index and collect in-force act entries.

    Each row is an ``<a class="bsgentry" data-bsg=… data-status=…
    data-format="html|pdf" data-language="de|fr" data-effective=…
    href=…>``. Repealed entries are skipped.
    """

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.entries: list[_BEArticleSpec] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag != "a":
            return
        attr = {k: (v or "") for k, v in attrs}
        if "bsgentry" not in attr.get("class", "").split():
            return
        if attr.get("data-status", "in_force") != "in_force":
            return
        bsg = attr.get("data-bsg", "").strip()
        href = attr.get("href", "").strip()
        if not bsg or not href:
            return
        fmt = (attr.get("data-format") or "html").lower().strip()
        self.entries.append(
            _BEArticleSpec(
                url=href,
                compilation_id=bsg,
                language=attr.get("data-language", "de") or "de",
                effective_date=attr.get("data-effective") or None,
                is_pdf=(fmt == "pdf"),
            )
        )


def parse_index(html: str) -> list[_BEArticleSpec]:
    """Pure parser: BSG index HTML -> list of in-force-act specs."""
    p = _BSGIndexParser()
    p.feed(html)
    p.close()
    return p.entries


def discover_specs(
    *,
    index_url: str = BSG_INDEX_URL,
    client: httpx.Client | None = None,
) -> list[_BEArticleSpec]:
    """Fetch the BSG catalogue and return specs for every in-force act."""
    own_client = client is None
    http = client if client is not None else httpx.Client(timeout=30.0)
    try:
        resp = http.get(index_url)
        resp.raise_for_status()
        return parse_index(resp.text)
    finally:
        if own_client:
            http.close()


ArticleSpec = _BEArticleSpec
