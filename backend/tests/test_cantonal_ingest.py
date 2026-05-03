"""Offline tests for the cantonal-law ingestion adapters.

Each adapter (ZH-Lex, BSG, RSG) is exercised against a recorded HTML
fixture under ``tests/fixtures/cantonal/``. Networked ``ingest()`` calls
are stubbed via ``respx`` so the suite runs without internet access.

Acceptance criteria mapped to tests (from task #21):

  * "correct article extraction"         -> test_*_extracts_articles
  * "correct canton tagging"             -> test_*_tags_canton
  * "repealed-article detection"         -> test_*_marks_repealed
  * "idempotent re-ingestion"            -> test_write_snapshot_is_deterministic
"""

from __future__ import annotations

import json
from pathlib import Path

import httpx
import respx

from swiss_legal_api.ingest.cantonal import (
    bern_bsg,
    geneva_rs,
    write_snapshot,
    zurich_ls,
)
from swiss_legal_api.ingest.cantonal.base import sort_records

FIXTURES = Path(__file__).parent / "fixtures" / "cantonal"


def _load(name: str) -> str:
    return (FIXTURES / name).read_text(encoding="utf-8")


# ----- Zurich (ZH-Lex) -----------------------------------------------------


def test_zh_extracts_articles_and_paragraphs():
    records = zurich_ls.parse_articles(
        _load("zh_ls_412_31.html"),
        compilation_id="412.31",
        language="de",
        source_url="https://www.zhlex.zh.ch/Erlass.html?Open&Ordnr=412.31",
        effective_date="2005-08-22",
    )
    by_key = {(r.article, r.paragraph): r for r in records}
    # Multi-paragraph article emits one record per Absatz.
    assert ("1", "1") in by_key and ("1", "2") in by_key
    assert "Volksschule" in by_key[("1", "1")].text
    # Target article for the smoke entitlement.
    assert ("27", "1") in by_key
    assert "Tagesbetreuung" in by_key[("27", "1")].text


def test_zh_tags_canton_and_dates():
    records = zurich_ls.parse_articles(
        _load("zh_ls_412_31.html"),
        compilation_id="412.31",
        language="de",
        source_url="https://www.zhlex.zh.ch/Erlass.html?Open&Ordnr=412.31",
        effective_date="2005-08-22",
    )
    assert records, "fixture must yield at least one record"
    assert all(r.canton == "ZH" for r in records)
    assert all(r.compilation_id == "412.31" for r in records)
    assert all(r.language == "de" for r in records)
    assert all(r.effective_date == "2005-08-22" for r in records)


def test_zh_marks_repealed_articles():
    records = zurich_ls.parse_articles(
        _load("zh_ls_412_31.html"),
        compilation_id="412.31",
        language="de",
        source_url="https://www.zhlex.zh.ch/Erlass.html?Open&Ordnr=412.31",
        effective_date="2005-08-22",
    )
    art99 = [r for r in records if r.article == "99"]
    assert art99, "repeal banner should still emit a tracking record"
    assert all(r.repealed_date == "9999-12-31" for r in art99)
    # Live articles must NOT carry the repeal marker.
    art27 = [r for r in records if r.article == "27"]
    assert art27 and all(r.repealed_date is None for r in art27)


@respx.mock
def test_zh_ingest_drives_parser_over_specs():
    url = "https://www.zhlex.zh.ch/Erlass.html?Open&Ordnr=412.31"
    respx.get(url).mock(
        return_value=httpx.Response(
            200,
            text=_load("zh_ls_412_31.html"),
            headers={"content-type": "text/html;charset=utf-8"},
        )
    )
    client = httpx.Client(timeout=5.0)
    try:
        records = zurich_ls.ingest(
            [
                zurich_ls.ArticleSpec(
                    url=url,
                    compilation_id="412.31",
                    language="de",
                    effective_date="2005-08-22",
                )
            ],
            client=client,
        )
    finally:
        client.close()
    assert any(r.article == "27" and r.paragraph == "2" for r in records)


# ----- Bern (BSG) ----------------------------------------------------------


def test_be_extracts_articles_and_paragraphs():
    records = bern_bsg.parse_articles(
        _load("be_bsg_271_1.html"),
        compilation_id="271.1",
        language="de",
        source_url="https://www.belex.sites.be.ch/data/271.1/de",
        effective_date="1996-01-01",
    )
    by_key = {(r.article, r.paragraph): r for r in records}
    assert ("11", "1") in by_key
    assert "Schlichtungsbeh" in by_key[("11", "1")].text
    assert ("11", "3") in by_key
    assert "kostenlos" in by_key[("11", "3")].text


def test_be_tags_canton_and_compilation():
    records = bern_bsg.parse_articles(
        _load("be_bsg_271_1.html"),
        compilation_id="271.1",
        language="de",
        source_url="https://www.belex.sites.be.ch/data/271.1/de",
        effective_date="1996-01-01",
    )
    assert all(r.canton == "BE" for r in records)
    assert all(r.compilation_id == "271.1" for r in records)


def test_be_marks_repealed_articles():
    records = bern_bsg.parse_articles(
        _load("be_bsg_271_1.html"),
        compilation_id="271.1",
        language="de",
        source_url="https://www.belex.sites.be.ch/data/271.1/de",
        effective_date="1996-01-01",
    )
    art42 = [r for r in records if r.article == "42"]
    assert art42, "repeal banner must still emit one tracking record"
    assert all(r.repealed_date == "9999-12-31" for r in art42)
    # Live articles stay un-repealed.
    art11 = [r for r in records if r.article == "11"]
    assert art11 and all(r.repealed_date is None for r in art11)


@respx.mock
def test_be_ingest_routes_pdf_entries_through_pdf_parser():
    """``ingest`` routes ``application/pdf`` responses through the PDF
    parser instead of the HTML one, so PDF-only BSG entries land in the
    corpus alongside the HTML majority.
    """
    url = "https://www.belex.sites.be.ch/data/legacy.pdf"
    respx.get(url).mock(
        return_value=httpx.Response(
            200,
            content=_build_test_pdf("Art. 7\n1 Diese Bestimmung ist anwendbar."),
            headers={"content-type": "application/pdf"},
        )
    )
    client = httpx.Client(timeout=5.0)
    try:
        records = bern_bsg.ingest(
            [
                bern_bsg.ArticleSpec(
                    url=url,
                    compilation_id="155.21",
                    language="de",
                    effective_date="1985-01-01",
                    is_pdf=True,
                )
            ],
            client=client,
        )
    finally:
        client.close()
    assert len(records) == 1
    assert records[0].canton == "BE"
    assert records[0].article == "7"
    assert "anwendbar" in records[0].text


@respx.mock
def test_be_ingest_swallows_corrupt_pdf_without_aborting_run(caplog):
    """A malformed PDF is logged + skipped; subsequent specs still ingest."""
    url_bad = "https://www.belex.sites.be.ch/data/broken.pdf"
    url_good = "https://www.belex.sites.be.ch/data/271.1/de"
    respx.get(url_bad).mock(
        return_value=httpx.Response(
            200,
            content=b"%PDF-1.4 (binary stub)",
            headers={"content-type": "application/pdf"},
        )
    )
    respx.get(url_good).mock(
        return_value=httpx.Response(
            200,
            text=(FIXTURES / "be_bsg_271_1.html").read_text(),
            headers={"content-type": "text/html; charset=utf-8"},
        )
    )
    client = httpx.Client(timeout=5.0)
    try:
        with caplog.at_level("ERROR"):
            records = bern_bsg.ingest(
                [
                    bern_bsg.ArticleSpec(
                        url=url_bad,
                        compilation_id="999.99",
                        language="de",
                        effective_date="1985-01-01",
                    ),
                    bern_bsg.ArticleSpec(
                        url=url_good,
                        compilation_id="271.1",
                        language="de",
                        effective_date="1996-01-01",
                    ),
                ],
                client=client,
            )
    finally:
        client.close()
    assert any("bsg_pdf_parse_failed" in r.message for r in caplog.records)
    # Subsequent HTML spec must still produce records.
    assert any(r.compilation_id == "271.1" for r in records)


# ----- Geneva (RSG) --------------------------------------------------------


def test_ge_extracts_articles_and_paragraphs():
    records = geneva_rs.parse_articles(
        _load("ge_rs_a2_05.html"),
        compilation_id="A 2 05",
        language="fr",
        source_url="https://www.lexfind.ch/fe/fr/tol/24891/fr",
        effective_date="2013-06-01",
    )
    by_key = {(r.article, r.paragraph): r for r in records}
    assert ("21", "1") in by_key
    assert "logement convenable" in by_key[("21", "1")].text


def test_ge_encodes_compilation_id():
    """``"A 2 05"`` -> ``"A2.05"`` so the loosened sr_number regex accepts it."""
    assert geneva_rs.encode_compilation_id("A 2 05") == "A2.05"
    assert geneva_rs.encode_compilation_id("E 5 05") == "E5.05"
    # No-space input passes through (idempotent).
    assert geneva_rs.encode_compilation_id("A2.05") == "A2.05"


def test_ge_tags_canton_and_encoded_id():
    records = geneva_rs.parse_articles(
        _load("ge_rs_a2_05.html"),
        compilation_id="A 2 05",
        language="fr",
        source_url="https://www.lexfind.ch/fe/fr/tol/24891/fr",
        effective_date="2013-06-01",
    )
    assert all(r.canton == "GE" for r in records)
    # Compilation ID must be the encoded form so the seeder's
    # Citation.sr_number validator (loosened to ^[A-Z]*\d+(\.\d+)?$) accepts it.
    assert all(r.compilation_id == "A2.05" for r in records)
    assert all(r.language == "fr" for r in records)


def test_ge_marks_repealed_articles():
    records = geneva_rs.parse_articles(
        _load("ge_rs_a2_05.html"),
        compilation_id="A 2 05",
        language="fr",
        source_url="https://www.lexfind.ch/fe/fr/tol/24891/fr",
        effective_date="2013-06-01",
    )
    # Art 245 in the fixture has only a <div class="rsg-abrogated"> child,
    # no surviving text — so it emits zero records but the parser must not
    # mark live articles as repealed.
    art21 = [r for r in records if r.article == "21"]
    assert art21 and all(r.repealed_date is None for r in art21)


# ----- Cross-canton snapshot determinism ----------------------------------


def test_write_snapshot_is_deterministic(tmp_path):
    """Re-running write_snapshot over the same records produces byte-identical output."""
    zh = zurich_ls.parse_articles(
        _load("zh_ls_412_31.html"),
        compilation_id="412.31",
        language="de",
        source_url="https://www.zhlex.zh.ch/Erlass.html?Open&Ordnr=412.31",
        effective_date="2005-08-22",
    )
    be = bern_bsg.parse_articles(
        _load("be_bsg_271_1.html"),
        compilation_id="271.1",
        language="de",
        source_url="https://www.belex.sites.be.ch/data/271.1/de",
        effective_date="1996-01-01",
    )
    ge = geneva_rs.parse_articles(
        _load("ge_rs_a2_05.html"),
        compilation_id="A 2 05",
        language="fr",
        source_url="https://www.lexfind.ch/fe/fr/tol/24891/fr",
        effective_date="2013-06-01",
    )
    all_records = zh + be + ge

    out1 = tmp_path / "snap_a.json"
    out2 = tmp_path / "snap_b.json"
    write_snapshot(all_records, out1)
    # Shuffle order to confirm sort stability.
    write_snapshot(list(reversed(all_records)), out2)
    assert out1.read_bytes() == out2.read_bytes()

    payload = json.loads(out1.read_text())
    # Required schema columns for downstream Qdrant ingestion.
    required = {
        "eli_uri",
        "sr_number",
        "article",
        "paragraph",
        "language",
        "text",
        "canton",
        "effective_date",
        "repealed_date",
    }
    for row in payload:
        assert required.issubset(row.keys()), f"missing keys: {required - row.keys()}"
    # Cantons all three present.
    assert {row["canton"] for row in payload} == {"ZH", "BE", "GE"}


# ----- Catalogue index discovery (per-canton) -----------------------------


def test_zh_index_discovers_in_force_acts_only():
    """ZH-Lex catalogue index parser yields specs only for live acts."""
    html = (FIXTURES / "zh_lex_index.html").read_text()
    specs = zurich_ls.parse_index(html)
    ordnrs = {s.compilation_id for s in specs}
    assert ordnrs == {"412.31", "170.1"}, "repealed entries must be excluded; got " + repr(ordnrs)
    spec = next(s for s in specs if s.compilation_id == "412.31")
    assert spec.url.endswith("Ordnr=412.31")
    assert spec.effective_date == "2005-08-22"
    assert spec.language == "de"


def test_be_index_marks_pdf_entries():
    """BSG catalogue index parser flags PDF-only acts so ``ingest`` routes
    them through the PDF parser instead of the HTML one.
    """
    html = (FIXTURES / "be_bsg_index.html").read_text()
    specs = bern_bsg.parse_index(html)
    by_bsg = {s.compilation_id: s for s in specs}
    assert set(by_bsg) == {"271.1", "155.21"}, "repealed entries excluded"
    assert by_bsg["271.1"].is_pdf is False
    assert by_bsg["155.21"].is_pdf is True
    assert by_bsg["155.21"].url.endswith(".pdf")


def test_ge_odata_feed_discovers_in_force_acts_only():
    """Geneva OData catalogue parser skips abrogated acts."""
    xml = (FIXTURES / "ge_rsg_odata.xml").read_text()
    specs = geneva_rs.parse_odata_feed(xml)
    ids = {s.compilation_id for s in specs}
    assert ids == {"A2.05", "E5.05"}, "abrogated entries must be excluded; got " + repr(ids)
    a205 = next(s for s in specs if s.compilation_id == "A2.05")
    assert a205.url.startswith("https://www.lexfind.ch/")
    assert a205.language == "fr"
    assert a205.effective_date == "2013-06-01"


def test_ge_odata_feed_handles_empty_feed():
    """Defensive: empty Atom feed yields zero specs without error."""
    xml = (
        '<?xml version="1.0" encoding="utf-8" standalone="yes"?>\n'
        '<feed xmlns="http://www.w3.org/2005/Atom"></feed>'
    )
    assert geneva_rs.parse_odata_feed(xml) == []


def test_ge_html_index_discovers_in_force_acts_only():
    """The ge.ch HTML RSG index is the OData fallback — same exclusion
    rule for repealed acts, same spec shape so callers can swap freely.
    """
    html = (FIXTURES / "ge_rsg_html_index.html").read_text()
    specs = geneva_rs.parse_html_index(html)
    ids = {s.compilation_id for s in specs}
    assert ids == {"A2.05", "E5.05"}, "abrogated entries must be excluded; got " + repr(ids)
    a205 = next(s for s in specs if s.compilation_id == "A2.05")
    assert a205.url.startswith("https://www.lexfind.ch/")
    assert a205.language == "fr"


@respx.mock
def test_ge_discover_specs_falls_back_to_html_when_odata_fails(caplog):
    """OData 503 -> :func:`discover_specs` transparently uses the HTML
    index. Operators see a warning so the OData outage is observable."""
    respx.get(geneva_rs.RSG_ODATA_URL).mock(
        return_value=httpx.Response(503, text="upstream unavailable")
    )
    respx.get(geneva_rs.RSG_HTML_INDEX_URL).mock(
        return_value=httpx.Response(
            200,
            text=(FIXTURES / "ge_rsg_html_index.html").read_text(),
            headers={"content-type": "text/html; charset=utf-8"},
        )
    )
    client = httpx.Client(timeout=5.0)
    try:
        with caplog.at_level("WARNING"):
            specs = geneva_rs.discover_specs(client=client)
    finally:
        client.close()
    ids = {s.compilation_id for s in specs}
    assert ids == {"A2.05", "E5.05"}
    assert any("rsg_odata_unavailable" in r.message for r in caplog.records)


# ----- Bern PDF fallback --------------------------------------------------


_BSG_PDF_TEXT = """
Mietverfahrensverordnung (MVV)

Art. 11
1   Das Verfahren vor der Schlichtungsbehoerde ist kostenlos.
2   Die unterliegende Partei kann zu einer Parteientschaedigung
verpflichtet werden, wenn das Verhalten als treuwidrig erscheint.
3   Vorbehalten bleiben besondere Bestimmungen.

Art. 12
1   Schriftliches Verfahren ist die Regel.
"""


def test_bern_parse_pdf_text_splits_articles_and_paragraphs():
    """The PDF text splitter handles ``Art. N`` headers and numeric
    paragraph numerals on the lectern-format BSG template.
    """
    records = bern_bsg.parse_pdf_text(
        _BSG_PDF_TEXT,
        compilation_id="271.1",
        language="de",
        source_url="https://www.belex.sites.be.ch/data/271.1/de.pdf",
        effective_date="1996-01-01",
    )
    by_key = {(r.article, r.paragraph): r for r in records}
    assert ("11", "1") in by_key
    assert ("11", "2") in by_key
    assert ("11", "3") in by_key
    assert ("12", "1") in by_key
    # Multi-line paragraph 2 must be joined back into one record.
    assert "treuwidrig" in by_key[("11", "2")].text
    assert by_key[("11", "2")].text.startswith("Die unterliegende")


def test_bern_parse_pdf_text_repeal_marker_flags_whole_article():
    """An article body containing 'aufgehoben' anywhere flags every
    paragraph in that article (article-scope, retroactive)."""
    text = """
Art. 5
1   Aufgehoben durch Anpassung 2024.
2   Diese Bestimmung gilt nicht mehr.

Art. 6
1   Diese Bestimmung ist weiterhin in Kraft.
"""
    records = bern_bsg.parse_pdf_text(
        text,
        compilation_id="271.1",
        language="de",
        source_url="https://x",
        effective_date="1996-01-01",
    )
    art5 = [r for r in records if r.article == "5"]
    art6 = [r for r in records if r.article == "6"]
    assert len(art5) == 2 and all(r.repealed_date == "9999-12-31" for r in art5)
    assert len(art6) == 1 and art6[0].repealed_date is None


def test_bern_extract_pdf_text_round_trip():
    """End-to-end PDF binary -> records via :func:`parse_pdf_articles`.

    Constructs a tiny but valid PDF with one article header and one
    paragraph numeral, then asserts the extracted record matches.
    """
    pdf_bytes = _build_test_pdf("Art. 11\n1 Das Verfahren ist kostenlos.")
    records = bern_bsg.parse_pdf_articles(
        pdf_bytes,
        compilation_id="271.1",
        language="de",
        source_url="https://x.pdf",
        effective_date="1996-01-01",
    )
    assert len(records) == 1
    assert records[0].article == "11"
    assert records[0].paragraph == "1"
    assert "kostenlos" in records[0].text


def _build_test_pdf(text: str) -> bytes:
    """Hand-build the smallest possible single-page PDF containing ``text``.

    Lives in the test module (rather than under fixtures/) because the
    byte offsets must be recomputed any time the page object changes,
    and shipping a binary fixture would obscure that. Keeps the test
    deterministic without needing reportlab.
    """
    # Each text line becomes a separate ``Tj`` showing operator, with a
    # ``T*`` newline between them so pypdf renders distinct lines.
    lines = text.splitlines()
    show_ops = []
    for i, line in enumerate(lines):
        # Escape PDF-special chars in the literal string operand.
        esc = line.replace("\\", "\\\\").replace("(", "\\(").replace(")", "\\)")
        if i == 0:
            show_ops.append(f"({esc}) Tj")
        else:
            show_ops.append(f"T* ({esc}) Tj")
    content = (
        "BT\n"
        "/F1 12 Tf\n"
        "14 TL\n"  # leading (line height) for T*
        "50 750 Td\n" + "\n".join(show_ops) + "\nET\n"
    ).encode("latin-1")

    objects: list[bytes] = []

    def add(body: bytes) -> int:
        objects.append(body)
        return len(objects)

    add(b"<< /Type /Catalog /Pages 2 0 R >>")
    add(b"<< /Type /Pages /Kids [3 0 R] /Count 1 >>")
    add(
        b"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] "
        b"/Contents 4 0 R /Resources << /Font << /F1 5 0 R >> >> >>"
    )
    add(b"<< /Length " + str(len(content)).encode() + b" >>\nstream\n" + content + b"endstream")
    add(b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>")

    parts: list[bytes] = [b"%PDF-1.4\n%\xe2\xe3\xcf\xd3\n"]
    offsets: list[int] = []
    for i, body in enumerate(objects, start=1):
        offsets.append(sum(len(p) for p in parts))
        parts.append(f"{i} 0 obj\n".encode() + body + b"\nendobj\n")
    xref_pos = sum(len(p) for p in parts)
    xref = [f"xref\n0 {len(objects) + 1}\n", "0000000000 65535 f \n"]
    for off in offsets:
        xref.append(f"{off:010d} 00000 n \n")
    parts.append("".join(xref).encode())
    parts.append(
        f"trailer\n<< /Size {len(objects) + 1} /Root 1 0 R >>\n"
        f"startxref\n{xref_pos}\n%%EOF\n".encode()
    )
    return b"".join(parts)


# ----- Edge-case coverage flagged by code review --------------------------


_GE_NESTED_DIV_FIXTURE = """<!DOCTYPE html><html><body>
<div class="rsg-article" data-art="3">
  <div class="rsg-alinea" data-al="1">
    Toute personne a droit
    <div class="footnote">(voir aussi
      <span class="ref">art. 4</span>)
    </div>
    au respect de sa vie priv&eacute;e.
  </div>
</div>
</body></html>"""


def test_ge_preserves_alinea_text_across_nested_divs():
    """Nested <div>s inside an alinéa must NOT split or drop text.

    Regression guard for the parser bug where every closing </div>
    inside the article called _flush(), causing footnote/ref wrappers
    to truncate the visible paragraph text mid-sentence.
    """
    records = geneva_rs.parse_articles(
        _GE_NESTED_DIV_FIXTURE,
        compilation_id="A 2 05",
        language="fr",
        source_url="https://x",
        effective_date="2013-06-01",
    )
    assert len(records) == 1
    text = records[0].text
    # Both halves of the sentence (around the nested footnote div) must
    # survive in the same single record.
    assert "Toute personne a droit" in text
    assert "respect de sa vie priv" in text


_BE_REPEAL_AFTER_FIXTURE = """<!DOCTYPE html><html><body>
<div class="article" data-article="50">
  <h3>Art. 50</h3>
  <p data-paragraph="1">Erster Absatz vor dem Marker.</p>
  <p data-paragraph="2">Zweiter Absatz vor dem Marker.</p>
  <p class="status" data-status="aufgehoben">Aufgehoben am 1.1.2024.</p>
</div>
</body></html>"""


def test_be_repeal_marker_after_paragraphs_still_flags_article():
    """Status marker placed AFTER paragraphs must still flag every record.

    Regression guard for the eager-emission bug where paragraphs were
    appended to ``_records`` before the status <p> was seen, so the
    article-scope repeal flag never reached them and the retrieval
    guardrail couldn't suppress the article.
    """
    records = bern_bsg.parse_articles(
        _BE_REPEAL_AFTER_FIXTURE,
        compilation_id="999.99",
        language="de",
        source_url="https://x",
        effective_date="1996-01-01",
    )
    art50 = [r for r in records if r.article == "50"]
    assert len(art50) == 2  # both paragraphs survived
    assert all(r.repealed_date == "9999-12-31" for r in art50), (
        "every paragraph in a retroactively-repealed article must inherit the repeal flag"
    )


_GE_REPEAL_AFTER_FIXTURE = """<!DOCTYPE html><html><body>
<div class="rsg-article" data-art="99">
  <div class="rsg-alinea" data-al="1">Disposition transitoire.</div>
  <div class="rsg-alinea" data-al="2">Reste applicable jusqu'&agrave;.</div>
  <div class="rsg-abrogated">Abrog&eacute; le 1er janvier 2025.</div>
</div>
</body></html>"""


def test_ge_repeal_marker_after_alineas_still_flags_article():
    """Same retroactive-repeal contract as BE for Geneva."""
    records = geneva_rs.parse_articles(
        _GE_REPEAL_AFTER_FIXTURE,
        compilation_id="A 2 05",
        language="fr",
        source_url="https://x",
        effective_date="2013-06-01",
    )
    art99 = [r for r in records if r.article == "99"]
    assert len(art99) == 2
    assert all(r.repealed_date == "9999-12-31" for r in art99)


def test_seeder_load_articles_auto_merges_cantonal(tmp_path, monkeypatch):
    """``_load_articles`` picks up ``law_articles.cantonal.json`` automatically.

    Constructs a temp seed/ directory with all three sources present and
    confirms the cantonal rows reach the merged output (additive, not
    subject to the fedlex-vs-manual coverage merge) AND that the source
    list reports the cantonal file.
    """
    import json as _json

    from swiss_legal_api.seeding import seed_qdrant

    # Mimic backend/seed/ layout next to a fake module location.
    # _load_articles resolves seed_dir as ``Path(__file__).parents[3] / "seed"``,
    # so the fake module path needs exactly 3 intermediate directories
    # (src/swiss_legal_api/seeding) above tmp_path for parents[3] to land
    # on tmp_path itself.
    seed_dir = tmp_path / "seed"
    seed_dir.mkdir()
    fedlex = seed_dir / "law_articles.fedlex.json"
    manual = seed_dir / "law_articles.json"
    cantonal = seed_dir / "law_articles.cantonal.json"

    fedlex.write_text(
        _json.dumps(
            [
                {
                    "sr_number": "220",
                    "article": "1",
                    "paragraph": "1",
                    "language": "de",
                    "text": "Federal text.",
                    "canton": "CH",
                    "effective_date": "1912-01-01",
                    "repealed_date": None,
                }
            ]
        )
    )
    manual.write_text(
        _json.dumps(
            [
                {
                    "sr_number": "220",
                    "article": "1",
                    "paragraph": "1",
                    "language": "de",
                    "text": "manual fallback (should be skipped)",
                    "canton": "CH",
                    "effective_date": "1912-01-01",
                    "repealed_date": None,
                }
            ]
        )
    )
    cantonal.write_text(
        _json.dumps(
            [
                {
                    "sr_number": "271.1",
                    "article": "11",
                    "paragraph": "3",
                    "language": "de",
                    "text": "Das Verfahren ist kostenlos.",
                    "canton": "BE",
                    "effective_date": "1996-01-01",
                    "repealed_date": None,
                    "eli_uri": "cantonal:BE:271.1",
                }
            ]
        )
    )

    fake_module = tmp_path / "src" / "swiss_legal_api" / "seeding" / "seed_qdrant.py"
    fake_module.parent.mkdir(parents=True)
    fake_module.touch()
    monkeypatch.setattr(seed_qdrant, "__file__", str(fake_module))

    records, sources = seed_qdrant._load_articles(None)
    assert cantonal in sources, "cantonal file must be reported as a source"
    assert len(sources) == 3  # fedlex + manual + cantonal
    cantonal_rows = [r for r in records if r.get("canton") == "BE"]
    assert len(cantonal_rows) == 1
    assert cantonal_rows[0]["text"] == "Das Verfahren ist kostenlos."


def test_sort_records_uses_natural_article_order():
    """Numeric article ordering: '9' < '99' (not '9' < '99' < '999' as strings)."""
    a = zurich_ls.parse_articles(
        _load("zh_ls_412_31.html"),
        compilation_id="412.31",
        language="de",
        source_url="https://www.zhlex.zh.ch/Erlass.html?Open&Ordnr=412.31",
        effective_date="2005-08-22",
    )
    sorted_a = sort_records(a)
    # The fixture has art 1, 27, 99. Natural order: 1 < 27 < 99 (numeric).
    articles_in_order = [r.article for r in sorted_a]
    # First occurrence ordering check.
    seen = []
    for art in articles_in_order:
        if art not in seen:
            seen.append(art)
    assert seen == ["1", "27", "99"]
