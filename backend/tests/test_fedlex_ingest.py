"""Offline tests for the Fedlex SPARQL + AN-XML ingestion pipeline.

Network calls to Fedlex are stubbed via ``respx`` so the suite can run
without internet access. Two SPARQL fixtures and two minimal Akoma Ntoso
XML fixtures live under ``tests/fixtures/fedlex/``.
"""
from __future__ import annotations

import json
from pathlib import Path

import httpx
import pytest
import respx

from swiss_legal_api.ingest import fedlex

FIXTURES = Path(__file__).parent / "fixtures" / "fedlex"


def _load_text(name: str) -> str:
    return (FIXTURES / name).read_text(encoding="utf-8")


def _load_json(name: str) -> dict:
    return json.loads(_load_text(name))


# ----- Pure parser tests (no network) --------------------------------------


def test_parse_articles_multi_paragraph():
    """A multi-paragraph article emits one record per <paragraph>."""
    records = fedlex.parse_articles(
        _load_text("sr220_de_min.xml"),
        eli_uri="https://fedlex.data.admin.ch/eli/cc/27/317_321_377/de",
        sr_number="220",
        language="de",
        effective_date="1912-01-01",
        repealed_date=None,
    )
    art1 = [r for r in records if r.article == "1"]
    assert {r.paragraph for r in art1} == {"1", "2"}
    assert "Willensäusserung" in next(r.text for r in art1 if r.paragraph == "1")
    assert next(r.text for r in art1 if r.paragraph == "2").startswith("Sie kann")


def test_parse_articles_letter_suffix_normalisation():
    """``art_6_a`` -> ``"6a"`` and ``art_257e`` -> ``"257e"``."""
    records = fedlex.parse_articles(
        _load_text("sr220_de_min.xml"),
        eli_uri="https://fedlex.data.admin.ch/eli/cc/27/317_321_377/de",
        sr_number="220",
        language="de",
        effective_date="1912-01-01",
        repealed_date=None,
    )
    article_numbers = {r.article for r in records}
    assert "6a" in article_numbers
    assert "257e" in article_numbers


def test_parse_articles_strips_authorial_note_in_num():
    """The ``<authorialNote>`` inside ``<num>`` must NOT leak into the body."""
    records = fedlex.parse_articles(
        _load_text("sr220_de_min.xml"),
        eli_uri="https://fedlex.data.admin.ch/eli/cc/27/317_321_377/de",
        sr_number="220",
        language="de",
        effective_date="1912-01-01",
        repealed_date=None,
    )
    art6a_p1 = next(r for r in records if r.article == "6a" and r.paragraph == "1")
    assert "Eingefügt" not in art6a_p1.text
    assert "unbestellten Sache" in art6a_p1.text


def test_parse_articles_solo_paragraph_article():
    """Article without ``<paragraph>`` children gets one record at paragraph=1."""
    records = fedlex.parse_articles(
        _load_text("sr220_de_min.xml"),
        eli_uri="https://fedlex.data.admin.ch/eli/cc/27/317_321_377/de",
        sr_number="220",
        language="de",
        effective_date="1912-01-01",
        repealed_date=None,
    )
    art999 = [r for r in records if r.article == "999"]
    assert len(art999) == 1
    assert art999[0].paragraph == "1"
    assert art999[0].text == "Solo-paragraph article without paragraph children."


def test_parse_articles_skips_empty_shells():
    """Header-only articles (no body text) emit no records."""
    records = fedlex.parse_articles(
        _load_text("sr220_de_min.xml"),
        eli_uri="https://fedlex.data.admin.ch/eli/cc/27/317_321_377/de",
        sr_number="220",
        language="de",
        effective_date="1912-01-01",
        repealed_date=None,
    )
    assert not any(r.article == "500" for r in records)


def test_parse_articles_skips_transitional_disp_subarticles():
    """Transitional provisions (eId='disp_u2/art_1') must not collide with
    main-body article 1 — they live under a separate structural element and
    are never cited by our entitlement catalog."""
    records = fedlex.parse_articles(
        _load_text("sr220_de_min.xml"),
        eli_uri="https://fedlex.data.admin.ch/eli/cc/27/317_321_377/de",
        sr_number="220",
        language="de",
        effective_date="1912-01-01",
        repealed_date=None,
    )
    art1 = [r for r in records if r.article == "1"]
    assert all("Transitional" not in r.text for r in art1)
    # Main-body Art. 1 has 2 paragraphs in the fixture; nothing extra leaks in.
    assert len(art1) == 2


def test_parse_articles_propagates_dates():
    records = fedlex.parse_articles(
        _load_text("sr220_de_min.xml"),
        eli_uri="https://fedlex.data.admin.ch/eli/cc/27/317_321_377/de",
        sr_number="220",
        language="de",
        effective_date="1912-01-01",
        repealed_date="2026-01-01",
    )
    assert all(r.effective_date == "1912-01-01" for r in records)
    assert all(r.repealed_date == "2026-01-01" for r in records)


# ----- Networked pipeline tests (respx-stubbed) ----------------------------


def _stub_filestore(
    respx_mock: respx.MockRouter,
    eli_path: str,
    snapshot_date: str,
    language: str,
    body: str,
    available_n: int = 2,
) -> None:
    """Mirror Fedlex's "highest valid N wins" behaviour.

    Returns ``application/xml`` for ``N <= available_n`` and the SPA HTML
    shell otherwise, so the client must probe correctly to find the body.
    """
    path_dashes = eli_path.replace("/", "-")
    base = (
        f"{fedlex.FILESTORE_BASE}/eli/cc/{eli_path}/{snapshot_date}/"
        f"{language}/xml/fedlex-data-admin-ch-eli-cc-{path_dashes}-"
        f"{snapshot_date}-{language}-xml-"
    )
    for n in range(1, fedlex.MAX_N_PROBE + 1):
        url = f"{base}{n}.xml"
        if n <= available_n:
            respx_mock.get(url).mock(
                return_value=httpx.Response(
                    200, text=body, headers={"content-type": "application/xml"}
                )
            )
        else:
            respx_mock.get(url).mock(
                return_value=httpx.Response(
                    200,
                    text="<!DOCTYPE html><html><body>SPA shell</body></html>",
                    headers={"content-type": "text/html;charset=UTF-8"},
                )
            )


@pytest.fixture
def fedlex_client():
    client = httpx.Client(timeout=5.0)
    yield fedlex.FedlexClient(client=client)
    client.close()


@respx.mock
def test_ingest_filters_languages_and_picks_highest_valid_n(fedlex_client):
    respx.post(fedlex.SPARQL_ENDPOINT).mock(
        return_value=httpx.Response(200, json=_load_json("sparql_sr220.json"))
    )
    _stub_filestore(
        respx,
        eli_path="27/317_321_377",
        snapshot_date="20240101",
        language="de",
        body=_load_text("sr220_de_min.xml"),
        available_n=4,
    )

    records = fedlex.ingest(
        ["220"],
        languages=("de",),
        snapshot_date="20240101",
        client=fedlex_client,
    )

    assert len(records) > 0
    assert {r.language for r in records} == {"de"}
    assert all(r.sr_number == "220" for r in records)
    # Date propagation from the SPARQL act metadata.
    assert all(r.effective_date == "1912-01-01" for r in records)
    assert all(r.repealed_date is None for r in records)
    # eli_uri is the realisation URI without the snapshot date.
    assert all(
        r.eli_uri == "https://fedlex.data.admin.ch/eli/cc/27/317_321_377/de"
        for r in records
    )


@respx.mock
def test_ingest_skips_languages_not_published(fedlex_client):
    """SR 141.0 ships only in DE/FR/IT — requesting EN must silently skip."""
    respx.post(fedlex.SPARQL_ENDPOINT).mock(
        return_value=httpx.Response(200, json=_load_json("sparql_sr14100.json"))
    )
    _stub_filestore(
        respx,
        eli_path="2016/404",
        snapshot_date="20240101",
        language="de",
        body=_load_text("sr14100_de_min.xml"),
    )

    records = fedlex.ingest(
        ["141.0"],
        languages=("de", "en"),  # EN absent from SPARQL response
        snapshot_date="20240101",
        client=fedlex_client,
    )

    assert {r.language for r in records} == {"de"}


@respx.mock
def test_ingest_snapshot_diff_repealed_propagates(fedlex_client, tmp_path):
    """A second snapshot adds dateNoLongerInForce; the diff surfaces it."""
    # First run: not repealed.
    respx.post(fedlex.SPARQL_ENDPOINT).mock(
        return_value=httpx.Response(200, json=_load_json("sparql_sr220.json"))
    )
    _stub_filestore(
        respx,
        eli_path="27/317_321_377",
        snapshot_date="20240101",
        language="de",
        body=_load_text("sr220_de_min.xml"),
    )
    records_a = fedlex.ingest(
        ["220"],
        languages=("de",),
        snapshot_date="20240101",
        client=fedlex_client,
    )

    # Second run: SPARQL now reports a dateNoLongerInForce.
    respx.post(fedlex.SPARQL_ENDPOINT).mock(
        return_value=httpx.Response(
            200, json=_load_json("sparql_sr220_repealed.json")
        )
    )
    records_b = fedlex.ingest(
        ["220"],
        languages=("de",),
        snapshot_date="20240101",
        client=fedlex_client,
    )

    assert all(r.repealed_date is None for r in records_a)
    assert all(r.repealed_date == "2026-01-01" for r in records_b)
    # Same shape, same article set — only the repealed_date column differs.
    assert {(r.article, r.paragraph) for r in records_a} == {
        (r.article, r.paragraph) for r in records_b
    }


@respx.mock
def test_write_snapshot_is_deterministic(fedlex_client, tmp_path):
    """Re-running write_snapshot() produces byte-identical output."""
    respx.post(fedlex.SPARQL_ENDPOINT).mock(
        return_value=httpx.Response(200, json=_load_json("sparql_sr220.json"))
    )
    _stub_filestore(
        respx,
        eli_path="27/317_321_377",
        snapshot_date="20240101",
        language="de",
        body=_load_text("sr220_de_min.xml"),
    )

    records = fedlex.ingest(
        ["220"],
        languages=("de",),
        snapshot_date="20240101",
        client=fedlex_client,
    )

    out1 = tmp_path / "snapshot_a.json"
    out2 = tmp_path / "snapshot_b.json"
    fedlex.write_snapshot(records, out1)
    # Shuffle order to confirm sorting is stable.
    fedlex.write_snapshot(list(reversed(records)), out2)

    assert out1.read_bytes() == out2.read_bytes()
    payload = json.loads(out1.read_text())
    # Required schema columns for downstream Qdrant ingestion.
    assert payload, "snapshot must not be empty"
    required = {
        "eli_uri", "sr_number", "article", "paragraph",
        "language", "text", "canton", "effective_date", "repealed_date",
    }
    for row in payload:
        assert required <= row.keys()
        assert row["canton"] == "CH"


@respx.mock
def test_fetch_consolidated_xml_rejects_html_shell(fedlex_client):
    """An HTML body for any N must be skipped, not parsed as XML."""
    eli_path = "27/317_321_377"
    snapshot_date = "20240101"
    language = "de"
    path_dashes = eli_path.replace("/", "-")
    base = (
        f"{fedlex.FILESTORE_BASE}/eli/cc/{eli_path}/{snapshot_date}/"
        f"{language}/xml/fedlex-data-admin-ch-eli-cc-{path_dashes}-"
        f"{snapshot_date}-{language}-xml-"
    )
    # Every N returns the SPA HTML shell -> must raise.
    for n in range(1, fedlex.MAX_N_PROBE + 1):
        respx.get(f"{base}{n}.xml").mock(
            return_value=httpx.Response(
                200,
                text="<!DOCTYPE html><html></html>",
                headers={"content-type": "text/html"},
            )
        )

    with pytest.raises(fedlex.FedlexNotFoundError):
        fedlex_client.fetch_consolidated_xml(eli_path, snapshot_date, language)


def test_normalisers():
    assert fedlex._normalise_article("art_18") == "18"
    assert fedlex._normalise_article("art_257e") == "257e"
    assert fedlex._normalise_article("art_6_a") == "6a"
    with pytest.raises(fedlex.FedlexParseError):
        fedlex._normalise_article("section_1")
    assert fedlex._normalise_paragraph("art_18/para_1") == "1"
    assert fedlex._normalise_paragraph("art_18/para_3_a") == "3a"
    with pytest.raises(fedlex.FedlexParseError):
        fedlex._normalise_paragraph("art_18/clause_1")


def test_candidate_snapshot_dates_walks_back_to_eif():
    """When the requested date has no manifestation we want to probe each
    earlier January 1st down to the act's entry-into-force year — but never
    earlier, otherwise we'd hammer the filestore for non-existent decades."""
    candidates = fedlex._candidate_snapshot_dates("20260101", "2018-01-01")
    assert candidates[0] == "20260101"
    assert candidates[-1] == "20180101"
    assert candidates == [f"{y}0101" for y in range(2026, 2017, -1)]


def test_candidate_snapshot_dates_caps_at_ten_years_when_eif_unknown():
    candidates = fedlex._candidate_snapshot_dates("20260101", None)
    assert candidates[0] == "20260101"
    assert candidates[-1] == "20160101"
    assert len(candidates) == 11


def test_candidate_snapshot_dates_clamps_when_eif_after_requested():
    """Defensive: if the act's entry-into-force is *after* the requested
    snapshot date (caller passed a stale year), still probe at least the
    requested date itself instead of returning [] and crashing ingest()."""
    candidates = fedlex._candidate_snapshot_dates("20180101", "2024-01-01")
    assert candidates == ["20180101"]
    # Equality case: floor == requested year still yields one probe.
    candidates_eq = fedlex._candidate_snapshot_dates("20240101", "2024-06-15")
    assert candidates_eq == ["20240101"]


def test_split_numeric_orders_letter_suffixes():
    # Used by _sort_records to keep "9" < "9a" < "10".
    assert fedlex._split_numeric("9") < fedlex._split_numeric("9a")
    assert fedlex._split_numeric("9a") < fedlex._split_numeric("10")
    assert fedlex._split_numeric("257e") > fedlex._split_numeric("100")
