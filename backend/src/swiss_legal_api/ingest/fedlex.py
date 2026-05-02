"""Fedlex SPARQL + Akoma Ntoso ingestion pipeline.

Fetches Swiss federal-law articles from data.fedlex.admin.ch and emits a
deterministic snapshot file (``seed/law_articles.fedlex.json``) that the
Qdrant seeder consumes via UUID5 stable IDs.

Pipeline per SR number:

1. SPARQL: resolve SR -> act URI + ``dateEntryInForce`` +
   ``dateNoLongerInForce`` + per-language realisation URIs via
   ``jolux:historicalLegalId``.
2. For each requested language present on the act, download the consolidated
   Akoma Ntoso XML from the Fedlex filestore at the well-known URL pattern::

      https://fedlex.data.admin.ch/filestore/fedlex.data.admin.ch/
        eli/cc/<path>/<YYYYMMDD>/<lang>/xml/
        fedlex-data-admin-ch-eli-cc-<path-with-dashes>-<YYYYMMDD>-<lang>-xml-<N>.xml

   ``N`` is a per-revision suffix; we probe ``MAX_N_PROBE..1`` and take the
   highest value that returns a real ``application/xml`` body. Fedlex serves
   its single-page-app HTML shell for non-existent ``N`` values, so a 200
   alone is not sufficient.
3. Parse ``<article eId="art_X">`` -> ``<paragraph eId="art_X/para_Y">`` ->
   ``<content><p>...</p></content>``. Articles without ``<paragraph>``
   children emit one record with ``paragraph="1"``.

CLI::

   python -m swiss_legal_api.ingest.fedlex \\
       --sr 220,642.11,141.0,142.20,837.0,831.40
"""
from __future__ import annotations

import argparse
import json
import logging
import re
import sys
import xml.etree.ElementTree as ET
from collections.abc import Iterable
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import httpx

logger = logging.getLogger(__name__)

SPARQL_ENDPOINT = "https://fedlex.data.admin.ch/sparqlendpoint"
FILESTORE_BASE = "https://fedlex.data.admin.ch/filestore/fedlex.data.admin.ch"
ACT_URI_PREFIX = "https://fedlex.data.admin.ch/eli/cc/"

JOLUX = "http://data.legilux.public.lu/resource/ontology/jolux#"
LANG_URI = {
    "de": "http://publications.europa.eu/resource/authority/language/DEU",
    "fr": "http://publications.europa.eu/resource/authority/language/FRA",
    "it": "http://publications.europa.eu/resource/authority/language/ITA",
    "en": "http://publications.europa.eu/resource/authority/language/ENG",
}
LANG_FROM_URI = {v: k for k, v in LANG_URI.items()}

AKN_NS = "{http://docs.oasis-open.org/legaldocml/ns/akn/3.0}"
# Fedlex serves SPA HTML for N >= ~50; 10 covers all currently published
# revisions of the SRs we care about and bounds the worst-case probe cost.
MAX_N_PROBE = 10


class FedlexError(Exception):
    """Base exception for the Fedlex ingestion pipeline."""


class FedlexNotFoundError(FedlexError):
    """Raised when an act / language / manifestation cannot be located."""


class FedlexParseError(FedlexError):
    """Raised when SPARQL / AN-XML cannot be parsed as expected."""


@dataclass(frozen=True)
class ActMetadata:
    """Per-SR metadata resolved from the Fedlex SPARQL graph."""

    sr_number: str
    act_uri: str  # https://fedlex.data.admin.ch/eli/cc/<path>
    eli_path: str  # <path>, e.g. "27/317_321_377"
    effective_date: str | None  # YYYY-MM-DD or None
    repealed_date: str | None  # YYYY-MM-DD or None
    realisations: dict[str, str] = field(default_factory=dict)  # lang -> realisation URI


@dataclass(frozen=True)
class ArticleRecord:
    """One Qdrant-bound row: a single (article, paragraph, language) chunk."""

    eli_uri: str  # realisation URI, undated (e.g. .../eli/cc/27/317_321_377/de)
    sr_number: str
    article: str
    paragraph: str
    language: str
    text: str
    effective_date: str | None
    repealed_date: str | None
    canton: str = "CH"

    def as_payload(self) -> dict[str, Any]:
        return {
            "eli_uri": self.eli_uri,
            "sr_number": self.sr_number,
            "article": self.article,
            "paragraph": self.paragraph,
            "language": self.language,
            "text": self.text,
            "canton": self.canton,
            "effective_date": self.effective_date,
            "repealed_date": self.repealed_date,
        }


class FedlexClient:
    """Thin httpx wrapper around the Fedlex SPARQL endpoint and filestore."""

    def __init__(
        self,
        client: httpx.Client | None = None,
        sparql_endpoint: str = SPARQL_ENDPOINT,
        filestore_base: str = FILESTORE_BASE,
    ) -> None:
        self._owns_client = client is None
        self._client = client if client is not None else httpx.Client(timeout=60.0)
        self._sparql_endpoint = sparql_endpoint
        self._filestore_base = filestore_base

    def __enter__(self) -> FedlexClient:
        return self

    def __exit__(self, *exc: object) -> None:
        self.close()

    def close(self) -> None:
        if self._owns_client:
            self._client.close()

    def fetch_act_metadata(self, sr_number: str) -> ActMetadata:
        """Resolve SR -> act URI, dates, and per-language realisations."""
        query = (
            f"PREFIX jolux: <{JOLUX}>\n"
            "SELECT DISTINCT ?act ?eif ?nolonger ?lang ?expr WHERE {\n"
            f'  ?expr jolux:historicalLegalId "{sr_number}" .\n'
            "  ?expr jolux:language ?lang .\n"
            "  ?act jolux:isRealizedBy ?expr .\n"
            "  OPTIONAL { ?act jolux:dateEntryInForce ?eif }\n"
            "  OPTIONAL { ?act jolux:dateNoLongerInForce ?nolonger }\n"
            "}\n"
        )
        rows = self._sparql(query)
        if not rows:
            raise FedlexNotFoundError(f"No act found for SR {sr_number}")
        act_uri: str | None = None
        eif: str | None = None
        nolonger: str | None = None
        realisations: dict[str, str] = {}
        for row in rows:
            act_uri = row["act"]["value"]
            if "eif" in row and eif is None:
                eif = row["eif"]["value"]
            if "nolonger" in row and nolonger is None:
                nolonger = row["nolonger"]["value"]
            lang = LANG_FROM_URI.get(row["lang"]["value"])
            if lang:
                realisations[lang] = row["expr"]["value"]
        assert act_uri is not None
        if not act_uri.startswith(ACT_URI_PREFIX):
            raise FedlexParseError(f"Unexpected act URI shape: {act_uri}")
        return ActMetadata(
            sr_number=sr_number,
            act_uri=act_uri,
            eli_path=act_uri[len(ACT_URI_PREFIX):],
            effective_date=eif,
            repealed_date=nolonger,
            realisations=realisations,
        )

    def fetch_consolidated_xml(
        self,
        eli_path: str,
        snapshot_date: str,
        language: str,
    ) -> str:
        """Download AN-XML for an (eli_path, YYYYMMDD, lang) triple.

        Probes ``N=MAX_N_PROBE..1`` and returns the highest revision whose
        body is real Akoma Ntoso XML. Raises :class:`FedlexNotFoundError` when
        no manifestation is found.
        """
        path_dashes = eli_path.replace("/", "-")
        for n in range(MAX_N_PROBE, 0, -1):
            url = (
                f"{self._filestore_base}/eli/cc/{eli_path}/{snapshot_date}/"
                f"{language}/xml/fedlex-data-admin-ch-eli-cc-{path_dashes}-"
                f"{snapshot_date}-{language}-xml-{n}.xml"
            )
            resp = self._client.get(url)
            if resp.status_code != 200:
                continue
            content_type = resp.headers.get("content-type", "").lower()
            if not (
                content_type.startswith("application/xml")
                or content_type.startswith("text/xml")
            ):
                continue
            text = resp.text
            head = text.lstrip()[:500]
            if not head.startswith("<?xml") and "akomaNtoso" not in head:
                continue
            return text
        raise FedlexNotFoundError(
            f"No XML manifestation found for {eli_path} {snapshot_date} {language} "
            f"(probed N=1..{MAX_N_PROBE})"
        )

    def _sparql(self, query: str) -> list[dict[str, Any]]:
        resp = self._client.post(
            self._sparql_endpoint,
            data={"query": query},
            headers={"Accept": "application/sparql-results+json"},
        )
        resp.raise_for_status()
        body = resp.json()
        bindings = body.get("results", {}).get("bindings", [])
        return list(bindings)


def _localname(tag: str) -> str:
    return tag.rsplit("}", 1)[-1]


def _gather_text(elem: ET.Element) -> str:
    """Concatenate all text under ``elem``, stripping any direct ``<num>`` child.

    AN-XML ``<paragraph>`` contains ``<num>`` (paragraph number, e.g. "1") and
    ``<content>`` (the body). We keep only the body text and collapse runs of
    whitespace so downstream embeddings see clean prose.
    """
    parts: list[str] = []
    for child in elem:
        if _localname(child.tag) == "num":
            continue
        parts.append("".join(child.itertext()))
    text = " ".join(parts)
    return re.sub(r"\s+", " ", text).strip()


def _normalise_article(eid: str) -> str:
    """``art_18`` -> ``"18"``, ``art_6_a`` -> ``"6a"``, ``art_257e`` -> ``"257e"``."""
    if not eid.startswith("art_"):
        raise FedlexParseError(f"unexpected article eId: {eid!r}")
    return eid[4:].replace("_", "")


def _normalise_paragraph(eid: str) -> str:
    """``art_X/para_3`` -> ``"3"``, ``art_X/para_3_a`` -> ``"3a"``."""
    _, _, tail = eid.partition("/")
    if not tail.startswith("para_"):
        raise FedlexParseError(f"unexpected paragraph eId: {eid!r}")
    return tail[5:].replace("_", "")


def parse_articles(
    xml_text: str,
    *,
    eli_uri: str,
    sr_number: str,
    language: str,
    effective_date: str | None,
    repealed_date: str | None,
) -> list[ArticleRecord]:
    """Parse Akoma Ntoso XML into per-paragraph :class:`ArticleRecord` rows.

    Each ``<article eId="art_X">`` becomes one record per
    ``<paragraph eId="art_X/para_Y">``. Articles without ``<paragraph>``
    children (single-paragraph) emit one record with ``paragraph="1"`` whose
    text is the entire article body.

    Empty text bodies are skipped — Fedlex sometimes ships header-only
    articles (placeholder shells around amended provisions).
    """
    root = ET.fromstring(xml_text)
    out: list[ArticleRecord] = []
    article_tag = f"{AKN_NS}article"
    paragraph_tag = f"{AKN_NS}paragraph"
    for art in root.iter(article_tag):
        eid = art.attrib.get("eId")
        if not eid:
            continue
        # Skip articles nested under another structural element. Real-world
        # Fedlex AN-XML labels transitional / final provisions as
        # "disp_u2/art_1", "disp_u3/art_5", etc. — they're not main-body
        # articles and our entitlement catalog never cites them, so emitting
        # them would just bloat the corpus with collisions on (sr_number,
        # article) tuples already taken by main-body rows.
        if "/" in eid or not eid.startswith("art_"):
            continue
        article_no = _normalise_article(eid)
        prefix = f"{eid}/para_"
        # Filter to direct paragraphs of *this* article so nested articles
        # (rare but possible in transitional provisions) don't bleed across.
        paragraphs = [
            p for p in art.iter(paragraph_tag)
            if p.attrib.get("eId", "").startswith(prefix)
        ]
        if paragraphs:
            for para in paragraphs:
                pid = para.attrib["eId"]
                text = _gather_text(para)
                if not text:
                    continue
                out.append(
                    ArticleRecord(
                        eli_uri=eli_uri,
                        sr_number=sr_number,
                        article=article_no,
                        paragraph=_normalise_paragraph(pid),
                        language=language,
                        text=text,
                        effective_date=effective_date,
                        repealed_date=repealed_date,
                    )
                )
        else:
            text = _gather_text(art)
            if text:
                out.append(
                    ArticleRecord(
                        eli_uri=eli_uri,
                        sr_number=sr_number,
                        article=article_no,
                        paragraph="1",
                        language=language,
                        text=text,
                        effective_date=effective_date,
                        repealed_date=repealed_date,
                    )
                )
    return out


def _split_numeric(s: str) -> tuple[int, str]:
    """Numeric prefix + letter suffix, so ``"9" < "9a" < "10"``."""
    m = re.match(r"^(\d+)(.*)$", s)
    if not m:
        return (0, s)
    return (int(m.group(1)), m.group(2))


def _sort_records(records: Iterable[ArticleRecord]) -> list[ArticleRecord]:
    def key(r: ArticleRecord) -> tuple[Any, ...]:
        return (
            r.sr_number,
            _split_numeric(r.article),
            _split_numeric(r.paragraph),
            r.language,
        )
    return sorted(records, key=key)


def _candidate_snapshot_dates(
    requested: str, effective_date: str | None
) -> list[str]:
    """Generate ``YYYYMMDD`` candidates from the requested date back to the
    act's entry-into-force year.

    Fedlex publishes a 1 January consolidation per year per act, but not
    every act gets a fresh consolidation every year — so when the requested
    date has no manifestation we walk backwards one year at a time. We stop
    at the act's ``dateEntryInForce`` (or 10 years before the requested year
    if unknown) so we don't probe forever.
    """
    try:
        req_year = int(requested[:4])
    except ValueError:  # pragma: no cover - defensive
        return [requested]
    if effective_date and len(effective_date) >= 4 and effective_date[:4].isdigit():
        floor_year = int(effective_date[:4])
    else:
        floor_year = req_year - 10
    # Defensive clamp: if the act's entry-into-force is *after* the requested
    # snapshot date (caller passed a stale year, or an act was rebuilt under a
    # new SR), still probe at least the requested date itself rather than
    # returning an empty candidate list (which would later crash ``ingest()``
    # when it indexed ``candidates[0]``).
    if floor_year > req_year:
        floor_year = req_year
    suffix = requested[4:] or "0101"
    seen: set[str] = set()
    out: list[str] = []
    for year in range(req_year, floor_year - 1, -1):
        candidate = f"{year:04d}{suffix}"
        if candidate not in seen:
            seen.add(candidate)
            out.append(candidate)
    return out


def ingest(
    sr_numbers: Iterable[str],
    *,
    languages: Iterable[str] = ("de", "fr", "it", "en"),
    snapshot_date: str | None = None,
    client: FedlexClient | None = None,
) -> list[ArticleRecord]:
    """Run the full pipeline for one or more SR numbers.

    ``snapshot_date`` is the ``YYYYMMDD`` Fedlex applicability date; when
    omitted it defaults to the current calendar year's January 1st (Fedlex
    publishes a 1 Jan consolidation per year). When that exact date has no
    manifestation we fall back year by year down to the act's entry-into-
    force year (some acts only get a fresh consolidation every few years).

    Returns the records sorted by ``(sr_number, article, paragraph,
    language)`` for deterministic snapshot output. Languages absent from a
    given act are silently skipped.
    """
    if snapshot_date is None:
        snapshot_date = f"{datetime.now(UTC).year}0101"
    fedlex = client or FedlexClient()
    out: list[ArticleRecord] = []
    try:
        for sr in sr_numbers:
            meta = fedlex.fetch_act_metadata(sr)
            candidates = _candidate_snapshot_dates(snapshot_date, meta.effective_date)
            for lang in languages:
                if lang not in meta.realisations:
                    logger.info("fedlex_lang_missing sr=%s lang=%s", sr, lang)
                    continue
                xml: str | None = None
                used_date: str | None = None
                for candidate_date in candidates:
                    try:
                        xml = fedlex.fetch_consolidated_xml(
                            meta.eli_path, candidate_date, lang
                        )
                        used_date = candidate_date
                        break
                    except FedlexNotFoundError:
                        continue
                if xml is None or used_date is None:
                    logger.warning(
                        "fedlex_xml_missing sr=%s lang=%s probed=%s..%s",
                        sr, lang, candidates[0], candidates[-1],
                    )
                    continue
                if used_date != snapshot_date:
                    logger.info(
                        "fedlex_xml_fallback sr=%s lang=%s requested=%s using=%s",
                        sr, lang, snapshot_date, used_date,
                    )
                out.extend(
                    parse_articles(
                        xml,
                        eli_uri=meta.realisations[lang],
                        sr_number=sr,
                        language=lang,
                        effective_date=meta.effective_date,
                        repealed_date=meta.repealed_date,
                    )
                )
    finally:
        if client is None:
            fedlex.close()
    return _sort_records(out)


def write_snapshot(records: Iterable[ArticleRecord], path: Path) -> int:
    """Serialise sorted records to JSON, returning the row count."""
    sorted_records = _sort_records(records)
    payload = [r.as_payload() for r in sorted_records]
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    return len(payload)


def _split_csv(raw: str) -> list[str]:
    return [s.strip() for s in raw.split(",") if s.strip()]


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="python -m swiss_legal_api.ingest.fedlex",
        description="Ingest Swiss federal-law articles from Fedlex.",
    )
    parser.add_argument(
        "--sr",
        required=True,
        help="Comma-separated SR numbers (e.g. 220,642.11,141.0)",
    )
    parser.add_argument(
        "--snapshot-date",
        default=None,
        help="Fedlex consolidation date YYYYMMDD (default: current year, 0101)",
    )
    parser.add_argument(
        "--languages",
        default="de,fr,it,en",
        help="Comma-separated language codes (default: de,fr,it,en)",
    )
    parser.add_argument(
        "--out",
        default=None,
        help="Output path (default: backend/seed/law_articles.fedlex.json)",
    )
    args = parser.parse_args(argv)

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s %(message)s",
    )

    sr_numbers = _split_csv(args.sr)
    languages = tuple(_split_csv(args.languages))

    out_path = (
        Path(args.out)
        if args.out
        else Path(__file__).resolve().parents[3] / "seed" / "law_articles.fedlex.json"
    )

    records = ingest(
        sr_numbers,
        languages=languages,
        snapshot_date=args.snapshot_date,
    )
    n = write_snapshot(records, out_path)

    # Per-SR/language summary so the operator can see at a glance which acts
    # actually contributed and which were silently empty (e.g. SR 141.0 with
    # no AN-XML manifestation in Fedlex). Articles are deduped per SR.
    by_sr: dict[str, set[str]] = {}
    by_lang: dict[str, int] = {}
    by_sr_lang: dict[tuple[str, str], int] = {}
    for r in records:
        by_sr.setdefault(r.sr_number, set()).add(r.article)
        by_lang[r.language] = by_lang.get(r.language, 0) + 1
        key = (r.sr_number, r.language)
        by_sr_lang[key] = by_sr_lang.get(key, 0) + 1
    print(
        f"Ingested {n} articles across {len(by_sr)} SRs, "
        f"{len(by_lang)} languages -> {out_path}"
    )
    for sr in sr_numbers:
        articles = by_sr.get(sr, set())
        if not articles:
            print(f"  SR {sr}: 0 records (no XML manifestation found)")
            continue
        lang_breakdown = ", ".join(
            f"{lang}={by_sr_lang.get((sr, lang), 0)}"
            for lang in languages
            if by_sr_lang.get((sr, lang), 0)
        )
        print(
            f"  SR {sr}: {len(articles)} distinct articles ({lang_breakdown})"
        )
    return 0


if __name__ == "__main__":
    sys.exit(main())
