"""Zurich (ZH) — Loseblattsammlung (LS) adapter.

ZH publishes its Systematic Compilation as HTML under
``https://www.zhlex.zh.ch/`` with two surfaces:

  * The catalogue index at ``/Inhalt.html?Open`` listing every in-force
    act with its LS number, title, and a link to the act page.
  * Per-act pages (``/Erlass.html?Open&Ordnr=NNN.NN``) containing the
    full structured text.

Index parser shape (``<a class="lsentry" data-ordnr="412.31"
data-status="in_force" data-effective="2005-08-22" href="…">``). Acts
flagged with ``data-status="repealed"`` are excluded from
``discover_specs`` so the corpus only contains live law.

Per-act parser shape:

  * ``<article class="enactment">`` wraps the whole act.
  * ``<section class="art" id="art-N">`` per article.
  * ``<h3 class="art-title">§ N</h3>`` per article header.
  * ``<p class="abs" data-abs="K">`` per paragraph (Absatz).
  * Optional ``<p class="repealed">…</p>`` marker — we surface it as
    ``repealed_date="9999-12-31"`` when the article body is replaced
    by a repeal notice (Zurich publishes repealed shells with a banner
    rather than removing the page).

We intentionally do NOT touch live URLs in the test suite — both
parsers are pure-string-in / records-out so the offline tests use
literal HTML fixtures and ``ingest()``/``discover_specs`` are exercised
against ``respx``-stubbed endpoints in the live runbook only.
"""
from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass
from html.parser import HTMLParser

import httpx

from .base import CantonalArticleRecord

CANTON = "ZH"
COMPILATION_LABEL = "ZH-Lex (Loseblattsammlung)"
# Marker date that the retrieval guardrail (`repealed_date <= today`) will
# exclude. We use the far-future RFC3339 minus one day so a cantonal
# repeal-banner article never accidentally surfaces in scans even if a
# future code path forgets to filter on `repealed_date`.
_REPEALED_FAR_FUTURE = "9999-12-31"


@dataclass(frozen=True)
class _ZHArticleSpec:
    """One unit of work for the live ingestor: a URL + its compilation key."""

    url: str
    compilation_id: str
    language: str = "de"
    effective_date: str | None = None


class _ZHActParser(HTMLParser):
    """State machine that walks a single ZH-Lex act page.

    Tracks (current_article, current_paragraph, in_abs, in_repealed)
    so the same parser instance can collect every paragraph in one pass.
    """

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self._records: list[tuple[str, str, str, bool]] = []
        # (article, paragraph, text, was_repealed)
        self._cur_article: str | None = None
        self._cur_paragraph: str | None = None
        self._buf: list[str] = []
        self._in_abs = False
        self._cur_repealed = False

    # ---- Token handlers ---------------------------------------------------

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        attr = {k: (v or "") for k, v in attrs}
        cls = attr.get("class", "")
        if tag == "section" and "art" in cls.split():
            # New article opens. Persist any in-flight paragraph first.
            self._flush()
            self._cur_article = self._extract_article_no(attr.get("id", ""))
            self._cur_paragraph = None
            self._cur_repealed = False
        elif tag == "p":
            cls_set = cls.split()
            if "abs" in cls_set and self._cur_article:
                # New paragraph opens. Flush previous Absatz before starting.
                self._flush()
                self._cur_paragraph = attr.get("data-abs", "1") or "1"
                self._in_abs = True
            elif "repealed" in cls_set and self._cur_article:
                # Repeal banner: emit a single placeholder record so the
                # downstream guardrail can suppress the article uniformly.
                self._flush()
                self._cur_paragraph = "1"
                self._in_abs = True
                self._cur_repealed = True

    def handle_endtag(self, tag: str) -> None:
        if tag == "p" and self._in_abs:
            self._flush()
        elif tag == "section":
            self._flush()
            self._cur_article = None

    def handle_data(self, data: str) -> None:
        if self._in_abs:
            self._buf.append(data)

    # ---- Helpers ----------------------------------------------------------

    def _extract_article_no(self, raw_id: str) -> str | None:
        """``"art-27"`` -> ``"27"``. Defensive: returns None on garbage."""
        if not raw_id.startswith("art-"):
            return None
        return raw_id[len("art-"):].strip() or None

    def _flush(self) -> None:
        if not self._in_abs:
            return
        text = " ".join("".join(self._buf).split())
        if self._cur_article and self._cur_paragraph and text:
            self._records.append(
                (
                    self._cur_article,
                    self._cur_paragraph,
                    text,
                    self._cur_repealed,
                )
            )
        self._buf = []
        self._in_abs = False

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
    """Parse one ZH-Lex act page into per-paragraph records.

    The compilation ID is the LS number (e.g. ``"412.31"`` for the
    Volksschulgesetz). Repeal-banner paragraphs surface with
    ``repealed_date=9999-12-31`` so the retrieval guardrail's
    ``repealed_date > today`` filter excludes them automatically — the
    record is kept rather than dropped so contributors can see in the
    snapshot diff that the article is still tracked but inactive.
    """
    parser = _ZHActParser()
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
    specs: Iterable[_ZHArticleSpec],
    *,
    client: httpx.Client | None = None,
) -> list[CantonalArticleRecord]:
    """Drive :func:`parse_articles` over a list of live act URLs.

    Specs come from :func:`discover_specs` (the default in production)
    or from a curated inline list (used as a fallback so smoke ingests
    work even if the canton's index is briefly unreachable).
    """
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


# ----- Catalogue index discovery -----------------------------------------

ZHLEX_INDEX_URL = "https://www.zhlex.zh.ch/Inhalt.html?Open"
_ACT_URL_TEMPLATE = "https://www.zhlex.zh.ch/Erlass.html?Open&Ordnr={ordnr}"


class _ZHIndexParser(HTMLParser):
    """Walk the ZH-Lex catalogue index and collect in-force act entries.

    The published index uses ``<a class="lsentry" data-ordnr=…
    data-status=… data-effective=… data-language=… href=…>`` per row.
    We skip ``data-status="repealed"`` so the discovered spec list
    contains only currently in-force acts.
    """

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.entries: list[_ZHArticleSpec] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag != "a":
            return
        attr = {k: (v or "") for k, v in attrs}
        if "lsentry" not in attr.get("class", "").split():
            return
        if attr.get("data-status", "in_force") != "in_force":
            return
        ordnr = attr.get("data-ordnr", "").strip()
        if not ordnr:
            return
        href = attr.get("href") or _ACT_URL_TEMPLATE.format(ordnr=ordnr)
        self.entries.append(
            _ZHArticleSpec(
                url=href,
                compilation_id=ordnr,
                language=attr.get("data-language", "de") or "de",
                effective_date=attr.get("data-effective") or None,
            )
        )


def parse_index(html: str) -> list[_ZHArticleSpec]:
    """Pure parser: index HTML -> list of in-force-act specs."""
    p = _ZHIndexParser()
    p.feed(html)
    p.close()
    return p.entries


def discover_specs(
    *,
    index_url: str = ZHLEX_INDEX_URL,
    client: httpx.Client | None = None,
) -> list[_ZHArticleSpec]:
    """Fetch the ZH-Lex catalogue and return one spec per in-force act."""
    own_client = client is None
    http = client if client is not None else httpx.Client(timeout=30.0)
    try:
        resp = http.get(index_url)
        resp.raise_for_status()
        return parse_index(resp.text)
    finally:
        if own_client:
            http.close()


# Public re-export for the CLI — kept module-level so adapters are
# duck-typed via :class:`base.CantonalAdapter`.
ArticleSpec = _ZHArticleSpec
