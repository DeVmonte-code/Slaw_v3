"""Geneva (GE) — Recueil systématique genevois (RSG) adapter.

Geneva publishes the RSG under ``https://www.lexfind.ch/`` and via an
OData feed at ``https://ge.ch/legislation/rsg/`` (the OData feed is the
official machine-readable surface but the HTML face is more stable in
practice — they share the same upstream content).

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
"""
from __future__ import annotations

import re
from collections.abc import Iterable
from dataclasses import dataclass
from html.parser import HTMLParser

import httpx

from .base import CantonalArticleRecord

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
            self._article_buffer.append(
                (self._cur_article, self._cur_paragraph, text)
            )
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


ArticleSpec = _GEArticleSpec
