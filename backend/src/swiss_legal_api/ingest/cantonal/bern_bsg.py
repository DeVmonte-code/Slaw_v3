"""Bern (BE) — Bernische Systematische Gesetzessammlung (BSG) adapter.

Bern publishes BSG under ``https://www.belex.sites.be.ch/`` with a mostly
HTML surface; a small minority of older acts only have PDF
manifestations. The HTML pages are structurally simpler than ZH-Lex:

  * ``<div class="article" data-article="N">`` per article.
  * ``<h3>Art. N</h3>`` (or ``§ N`` for older statutes).
  * ``<p data-paragraph="K">`` per paragraph.
  * Optional ``<p class="status" data-status="aufgehoben">…</p>`` marker
    for repealed articles (we treat any non-empty status of "aufgehoben"
    or "abrogated" as a repeal banner).

PDF fallback: a tiny number of BSG entries (mostly transitional decrees
from the 1980s) only ship a PDF download. Out of scope for this PR — the
adapter logs ``bsg_pdf_only sr=…`` and skips. A follow-up will extend
:func:`ingest` to delegate PDF entries to pypdf (already a project dep
via the curriculum chunker).
"""
from __future__ import annotations

import logging
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
    own_client = client is None
    http = client if client is not None else httpx.Client(timeout=30.0)
    try:
        out: list[CantonalArticleRecord] = []
        for spec in specs:
            resp = http.get(spec.url)
            resp.raise_for_status()
            content_type = resp.headers.get("content-type", "").lower()
            if "pdf" in content_type:
                # PDF fallback path is documented as out-of-scope for this
                # PR; surface clearly so operators see which BSG entries
                # need the follow-up work.
                logger.warning(
                    "bsg_pdf_only compilation=%s url=%s — skipping",
                    spec.compilation_id,
                    spec.url,
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


ArticleSpec = _BEArticleSpec
