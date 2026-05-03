"""Unit tests for the Fedlex+manual seeder merge logic.

These exercise ``_load_articles`` and ``_coverage_key`` directly, without
touching Qdrant — the actual upsert path is integration-tested via the
smoke gate.
"""

from __future__ import annotations

import json
from pathlib import Path

from swiss_legal_api.seeding import seed_qdrant


def _write(path: Path, records: list[dict[str, object]]) -> None:
    path.write_text(json.dumps(records, ensure_ascii=False))


def _make(
    sr: str, art: str, lang: str = "de", para: str = "1", text: str = "x"
) -> dict[str, object]:
    return {
        "sr_number": sr,
        "article": art,
        "paragraph": para,
        "language": lang,
        "text": text,
        "effective_date": "2020-01-01",
        "eli_uri": f"https://fedlex/eli/{sr}/{lang}",
    }


def test_load_articles_explicit_source_bypasses_merge(tmp_path, monkeypatch):
    f = tmp_path / "explicit.json"
    _write(f, [_make("220", "1")])
    records, sources = seed_qdrant._load_articles(str(f))
    assert len(records) == 1
    assert sources == [f]


def test_load_articles_manual_only_when_fedlex_missing(tmp_path, monkeypatch):
    """Bootstrap mode: only the hand-pasted manual file present."""
    seed_dir = tmp_path / "seed"
    seed_dir.mkdir()
    manual = seed_dir / "law_articles.json"
    _write(manual, [_make("220", "1"), _make("220", "2")])
    monkeypatch.setattr(
        seed_qdrant,
        "__file__",
        str(seed_dir.parent / "src" / "_pkg" / "_mod" / "seed_qdrant.py"),
    )
    # _load_articles computes seed_dir from __file__'s parents[3]; emulate that.
    fake_module = seed_dir.parent / "src" / "_pkg" / "_mod" / "seed_qdrant.py"
    fake_module.parent.mkdir(parents=True, exist_ok=True)
    fake_module.touch()
    monkeypatch.setattr(seed_qdrant, "__file__", str(fake_module))
    records, sources = seed_qdrant._load_articles(None)
    assert len(records) == 2
    assert sources == [manual]


def test_load_articles_merges_fedlex_and_manual_fallback(tmp_path, monkeypatch):
    """When both files exist, manual rows survive *only* for keys Fedlex
    didn't cover. SR 141.0 has no AN-XML manifestation in Fedlex and must
    keep flowing in from the manual bootstrap."""
    seed_dir = tmp_path / "seed"
    seed_dir.mkdir()
    fedlex = seed_dir / "law_articles.fedlex.json"
    manual = seed_dir / "law_articles.json"
    _write(fedlex, [_make("220", "1", text="fedlex 220 art1")])
    _write(
        manual,
        [
            # Same key as Fedlex — must be dropped (Fedlex wins on conflict).
            _make("220", "1", text="manual 220 art1"),
            # Key Fedlex doesn't cover — must survive.
            _make("141.0", "9", text="manual 141.0 art9"),
        ],
    )
    fake_module = seed_dir.parent / "src" / "_pkg" / "_mod" / "seed_qdrant.py"
    fake_module.parent.mkdir(parents=True, exist_ok=True)
    fake_module.touch()
    monkeypatch.setattr(seed_qdrant, "__file__", str(fake_module))

    records, sources = seed_qdrant._load_articles(None)
    by_text = {r["text"] for r in records}
    assert by_text == {"fedlex 220 art1", "manual 141.0 art9"}
    assert sources == [fedlex, manual]


def test_load_articles_fedlex_only_when_manual_missing(tmp_path, monkeypatch):
    seed_dir = tmp_path / "seed"
    seed_dir.mkdir()
    fedlex = seed_dir / "law_articles.fedlex.json"
    _write(fedlex, [_make("220", "1")])
    fake_module = seed_dir.parent / "src" / "_pkg" / "_mod" / "seed_qdrant.py"
    fake_module.parent.mkdir(parents=True, exist_ok=True)
    fake_module.touch()
    monkeypatch.setattr(seed_qdrant, "__file__", str(fake_module))
    records, sources = seed_qdrant._load_articles(None)
    assert len(records) == 1
    assert sources == [fedlex]


def test_load_articles_strips_placeholder_sentinels(tmp_path, monkeypatch, capsys):
    """Manual-only path: placeholder rows must be filtered before embedding
    so the literal __PENDING_FEDLEX_VERBATIM__ sentinel never enters Qdrant
    and pollutes retrieval.
    """
    seed_dir = tmp_path / "seed"
    seed_dir.mkdir()
    manual = seed_dir / "law_articles.json"
    real_row = _make("220", "1", text="Real legal text.")
    placeholder = _make("141.0", "9", text="__PENDING_FEDLEX_VERBATIM__")
    _write(manual, [real_row, placeholder])
    fake_module = seed_dir.parent / "src" / "_pkg" / "_mod" / "seed_qdrant.py"
    fake_module.parent.mkdir(parents=True, exist_ok=True)
    fake_module.touch()
    monkeypatch.setattr(seed_qdrant, "__file__", str(fake_module))

    records, _ = seed_qdrant._load_articles(None)
    assert len(records) == 1
    assert records[0]["sr_number"] == "220"
    out = capsys.readouterr().out
    assert "Skipped 1 placeholder rows" in out


def test_load_articles_strips_placeholders_from_merge_fallback(tmp_path, monkeypatch, capsys):
    """Critical correctness case: when Fedlex is missing an act and the
    manual row for that act still carries the sentinel, the merge must not
    reintroduce the placeholder into the corpus."""
    seed_dir = tmp_path / "seed"
    seed_dir.mkdir()
    fedlex = seed_dir / "law_articles.fedlex.json"
    manual = seed_dir / "law_articles.json"
    _write(fedlex, [_make("220", "1", text="fedlex 220 art1")])
    _write(
        manual,
        [
            # Same key as Fedlex - must drop regardless.
            _make("220", "1", text="manual 220 art1"),
            # Key Fedlex doesn't cover, but value is still a placeholder -
            # must NOT be reintroduced via fallback.
            _make("141.0", "9", text="__PENDING_FEDLEX_VERBATIM__"),
            # Key Fedlex doesn't cover and has real text - must survive.
            _make("141.0", "11", text="Real manual fallback text"),
        ],
    )
    fake_module = seed_dir.parent / "src" / "_pkg" / "_mod" / "seed_qdrant.py"
    fake_module.parent.mkdir(parents=True, exist_ok=True)
    fake_module.touch()
    monkeypatch.setattr(seed_qdrant, "__file__", str(fake_module))

    records, _ = seed_qdrant._load_articles(None)
    texts = {r["text"] for r in records}
    assert "__PENDING_FEDLEX_VERBATIM__" not in texts
    assert "fedlex 220 art1" in texts
    assert "Real manual fallback text" in texts
    out = capsys.readouterr().out
    assert "Skipped 1 placeholder rows" in out


def test_is_placeholder_detects_sentinel_substring():
    assert seed_qdrant._is_placeholder({"text": "__PENDING_FEDLEX_VERBATIM__"})
    # Substring match - protects against future seed templates that wrap
    # the sentinel in surrounding prose.
    assert seed_qdrant._is_placeholder(
        {"text": "TODO: __PENDING_FEDLEX_VERBATIM__ (backfill before 2026-01-01)"}
    )
    assert not seed_qdrant._is_placeholder({"text": "Real legal article text"})
    assert not seed_qdrant._is_placeholder({})
    assert not seed_qdrant._is_placeholder({"text": None})


def test_coverage_key_distinguishes_paragraph_and_language():
    """Two rows that share (sr, article) but differ in paragraph or language
    must get distinct coverage keys — otherwise the merge would silently
    drop translations or sub-paragraphs of an article Fedlex partially
    covers."""
    a = {"sr_number": "220", "article": "1", "paragraph": "1", "language": "de"}
    b = {"sr_number": "220", "article": "1", "paragraph": "2", "language": "de"}
    c = {"sr_number": "220", "article": "1", "paragraph": "1", "language": "fr"}
    assert seed_qdrant._coverage_key(a) != seed_qdrant._coverage_key(b)
    assert seed_qdrant._coverage_key(a) != seed_qdrant._coverage_key(c)
    assert seed_qdrant._coverage_key(b) != seed_qdrant._coverage_key(c)
